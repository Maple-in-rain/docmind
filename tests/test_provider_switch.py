"""provider 开关单测：_select_xxx 分支、非法值报错、build_services 全 mock 冒烟。

设计（面试可讲）：插件无注册表/工厂，唯一组装点 build_services 按 settings
开关选择实现——mock 分支让压测场景 2 可以全离线跑（测系统自身吞吐，
排除外部 API 延迟），且不烧 API 额度。
"""

import pytest

from app.config import settings
from app.embeddings.mock_embedder import MockEmbedder
from app.llm.mock_provider import MockProvider
from app.reranking.mock_reranker import MockReranker
from app.services import _select_embedder, _select_llm, _select_reranker, build_services


def test_select_embedder_mock(monkeypatch):
    monkeypatch.setattr(settings, "embedding_provider", "mock")
    assert isinstance(_select_embedder(), MockEmbedder)


def test_select_embedder_siliconflow(monkeypatch):
    monkeypatch.setattr(settings, "embedding_provider", "siliconflow")
    embedder = _select_embedder()  # 构造器惰性：不触网
    assert embedder.dim == 1024


def test_select_reranker_mock(monkeypatch):
    monkeypatch.setattr(settings, "rerank_provider", "mock")
    assert isinstance(_select_reranker(), MockReranker)


def test_select_reranker_siliconflow(monkeypatch):
    monkeypatch.setattr(settings, "rerank_provider", "siliconflow")
    assert _select_reranker() is not None  # 构造不触网


def test_select_llm_mock(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "mock")
    assert isinstance(_select_llm(), MockProvider)


def test_select_llm_deepseek(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "deepseek")
    assert _select_llm() is not None  # 构造惰性：不触网


@pytest.mark.parametrize(
    ("field", "selector"),
    [
        ("embedding_provider", _select_embedder),
        ("rerank_provider", _select_reranker),
        ("llm_provider", _select_llm),
    ],
)
def test_unknown_provider_raises_with_choices(monkeypatch, field, selector):
    monkeypatch.setattr(settings, field, "huggingface-local")
    with pytest.raises(ValueError, match="可选"):
        selector()


def test_build_services_all_mock_smoke(tmp_path, monkeypatch):
    """全 mock 组装冒烟：真实 Chroma/SQLite 落在 tmp，顺带守护 MockEmbedder 维度约束。"""
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "embedding_provider", "mock")
    monkeypatch.setattr(settings, "rerank_provider", "mock")
    monkeypatch.setattr(settings, "llm_provider", "mock")

    services = build_services()

    assert isinstance(services["llm"], MockProvider)
    assert services["embedder"].dim == 1024  # 与真实 bge-m3 一致，复用集合不触发维度校验
    assert isinstance(services["reranker"], MockReranker)
    assert services["vector_store"].count() == 0
    assert services["db"].db_path.parent == tmp_path
