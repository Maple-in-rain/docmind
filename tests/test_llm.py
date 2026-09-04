"""LLM provider 单测：SSE 帧解析、异常帧容错、重试策略、mock provider。

全部用 httpx.MockTransport 模拟网络，不发起真实请求。
"""

import asyncio

import httpx
import pytest

from app.llm.deepseek_provider import DeepSeekProvider
from app.llm.mock_provider import MockProvider

_FAKE_SSE = (
    'data: {"choices":[{"delta":{"content":"你好"}}]}\n\n'
    'data: {"choices":[{"delta":{"content":"世界"}}]}\n\n'
    "data: 垃圾帧（应被跳过）\n\n"
    'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
    "data: [DONE]\n\n"
)


def _mock_provider(handler) -> DeepSeekProvider:
    return DeepSeekProvider(
        api_key="test-key", base_url="http://test", model="deepseek-chat", transport=httpx.MockTransport(handler)
    )


async def _collect(agen) -> list[str]:
    return [x async for x in agen]


def test_sse_parsing():
    async def handler(request: httpx.Request) -> httpx.Response:
        # 校验请求体关键字段
        body = json_body(request)
        assert body["model"] == "deepseek-chat"
        assert body["stream"] is True
        return httpx.Response(200, content=_FAKE_SSE, request=request)

    provider = _mock_provider(handler)
    deltas = asyncio.run(_collect(provider.chat_stream([{"role": "user", "content": "hi"}])))
    assert deltas == ["你好", "世界"]  # 垃圾帧被跳过，[DONE] 正确终止


def json_body(request: httpx.Request) -> dict:
    import json

    return json.loads(request.content)


def test_retry_on_429():
    calls = {"count": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(429, content=b'{"error":"rate limited"}', request=request)
        return httpx.Response(200, content=_FAKE_SSE, request=request)

    provider = _mock_provider(handler)
    deltas = asyncio.run(_collect(provider.chat_stream([{"role": "user", "content": "hi"}])))
    assert calls["count"] == 2  # 第一次 429，重试后成功
    assert deltas == ["你好", "世界"]


def test_retry_exhausted():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, content=b"oops", request=request)

    provider = _mock_provider(handler)
    with pytest.raises(RuntimeError, match="已重试"):
        asyncio.run(_collect(provider.chat_stream([{"role": "user", "content": "hi"}])))


def test_missing_key_raises(monkeypatch):
    # 屏蔽 .env 中配置的真实 key，验证缺失时的报错路径
    monkeypatch.setattr("app.config.settings.deepseek_api_key", "")
    provider = DeepSeekProvider(api_key="")
    with pytest.raises(RuntimeError, match="DEEPSEEK_API_KEY"):
        asyncio.run(_collect(provider.chat_stream([{"role": "user", "content": "hi"}])))


def test_mock_provider():
    provider = MockProvider(chunk_size=5, delay=0)
    deltas = asyncio.run(_collect(provider.chat_stream([{"role": "user", "content": "测试问题"}])))
    assert "".join(deltas).startswith("[mock 回答]")
    assert all(len(d) <= 5 for d in deltas)
