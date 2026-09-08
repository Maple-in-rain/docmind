"""SearchService 分段计时日志：开启时各段齐全、策略差异反映、关闭时静默。"""

import logging

from app.config import settings
from app.retrieval.bm25_index import BM25Index
from app.services.search_service import SearchService
from app.storage.db import Database
from tests.helpers import FakeEmbedder, FakeReranker, FakeVectorStore
from tests.test_search import _seed


def _build_service(tmp_path, perf_log):
    db, embedder, vector_store, bm25_index = _seed(tmp_path)
    return SearchService(embedder, vector_store, db, bm25_index, FakeReranker())


def test_perf_log_hybrid_rerank_segments(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(settings, "perf_log", True)
    service = _build_service(tmp_path, True)

    with caplog.at_level(logging.INFO, logger="docmind.perf"):
        service.search("快速排序", "hybrid", top_k=3, rerank=True)

    logs = [r.message for r in caplog.records if r.name == "docmind.perf"]
    assert logs, "perf_log 开启时应有分段日志"
    line = logs[0]
    for seg in ("embed", "vector_query", "bm25", "db_fetch", "rerank", "total="):
        assert seg in line, f"日志缺分段 {seg}: {line}"
    assert "strategy=hybrid" in line and "rerank=True" in line


def test_perf_log_off_silent(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(settings, "perf_log", False)
    service = _build_service(tmp_path, False)

    with caplog.at_level(logging.INFO):
        service.search("快速排序", "hybrid", top_k=3, rerank=True)

    assert not any(r.name == "docmind.perf" for r in caplog.records)


def test_bm25_strategy_has_no_embed_segment(tmp_path, monkeypatch, caplog):
    """纯 bm25 不调 embedding——分段日志也应如实反映（embed 段不出现）"""
    monkeypatch.setattr(settings, "perf_log", True)
    db, _embedder, vector_store, bm25_index = _seed(tmp_path)
    service = SearchService(FakeEmbedder(), vector_store, db, bm25_index)

    with caplog.at_level(logging.INFO, logger="docmind.perf"):
        service.search("快速排序", "bm25", top_k=3)

    logs = [r.message for r in caplog.records if r.name == "docmind.perf"]
    assert logs
    assert "embed" not in logs[0]
    assert "bm25=" in logs[0]
