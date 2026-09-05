"""重排 provider 单测：httpx.MockTransport 注入，不发真实网络请求。"""

import json

import httpx
import pytest

from app.config import settings
from app.reranking.siliconflow_reranker import SiliconFlowRerankerProvider


def _provider(response_factory):
    """构造带 mock transport 的 provider：response_factory(payload_dict) -> response_json"""
    def handler(request):
        body = json.loads(request.content)
        return httpx.Response(200, json=response_factory(body))

    return SiliconFlowRerankerProvider(transport=httpx.MockTransport(handler))


def test_rerank_basic_and_payload():
    seen = {}

    def factory(body):
        seen.update(body)
        return {
            "results": [
                {"index": 1, "relevance_score": 0.9},
                {"index": 0, "relevance_score": 0.5},
            ]
        }

    p = _provider(factory)
    out = p.rerank("什么是 RAG", ["文档A", "文档B"], top_n=2)

    assert out == [(1, 0.9), (0, 0.5)]  # 按分数降序
    assert seen["model"] == settings.rerank_model
    assert seen["query"] == "什么是 RAG"
    assert seen["documents"] == ["文档A", "文档B"]
    assert seen["top_n"] == 2


def test_rerank_resorts_unsorted_api_response():
    """API 返回顺序乱时，provider 仍按分数降序返回（防御性排序）"""
    def factory(body):
        return {"results": [{"index": 0, "relevance_score": 0.1},
                            {"index": 1, "relevance_score": 0.9},
                            {"index": 2, "relevance_score": 0.5}]}

    out = _provider(factory).rerank("q", ["a", "b", "c"])
    assert out == [(1, 0.9), (2, 0.5), (0, 0.1)]


def test_rerank_empty_documents_no_network():
    def boom(request):
        raise AssertionError("空文档列表不应发起请求")

    p = SiliconFlowRerankerProvider(transport=httpx.MockTransport(boom))
    assert p.rerank("q", []) == []


def test_rerank_400_raises_immediately():
    """4xx（除 429）是请求本身的问题，不重试直接抛"""
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(400, json={"error": "bad request"})

    p = SiliconFlowRerankerProvider(transport=httpx.MockTransport(handler))
    with pytest.raises(httpx.HTTPStatusError):
        p.rerank("q", ["a"])
    assert calls["n"] == 1


def test_rerank_retries_on_429_then_succeeds():
    """限流 429 指数退避重试，Retry-After 头控制等待（测试用 0.01s）"""
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(429, json={"error": "rate limited"}, headers={"Retry-After": "0.01"})
        return httpx.Response(200, json={"results": [{"index": 0, "relevance_score": 0.8}]})

    p = SiliconFlowRerankerProvider(transport=httpx.MockTransport(handler))
    assert p.rerank("q", ["a"]) == [(0, 0.8)]
    assert calls["n"] == 3


def test_rerank_429_exhausts_retries():
    def handler(request):
        return httpx.Response(429, json={}, headers={"Retry-After": "0.01"})

    p = SiliconFlowRerankerProvider(transport=httpx.MockTransport(handler))
    with pytest.raises(RuntimeError, match="已重试"):
        p.rerank("q", ["a"])


def test_rerank_missing_key(monkeypatch):
    monkeypatch.setattr(settings, "siliconflow_api_key", "")
    p = SiliconFlowRerankerProvider()
    with pytest.raises(RuntimeError, match="未配置硅基流动 API key"):
        p.rerank("q", ["a"])
