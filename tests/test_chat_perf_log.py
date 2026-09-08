"""ChatService 分段计时日志：retrieval / llm_first_token / llm_total 三段齐全。"""

import asyncio
import logging

from app.config import settings
from app.llm.mock_provider import MockProvider
from app.retrieval.bm25_index import BM25Index
from app.services.chat_service import ChatService
from app.services.search_service import SearchService
from app.storage.db import Database
from tests.helpers import FakeEmbedder, FakeReranker, FakeVectorStore
from tests.test_search import _seed


def _run_stream(service, messages):
    async def collect():
        return [e async for e in service.stream_chat(messages)]

    return asyncio.run(collect())


def test_chat_perf_log_segments(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(settings, "perf_log", True)
    db, embedder, vector_store, bm25_index = _seed(tmp_path)
    search = SearchService(embedder, vector_store, db, bm25_index, FakeReranker())
    chat = ChatService(search, MockProvider(delay=0))

    with caplog.at_level(logging.INFO, logger="docmind.perf"):
        events = _run_stream(chat, [{"role": "user", "content": "快速排序是什么"}])

    assert events[-1]["type"] == "done"
    chat_logs = [r.message for r in caplog.records if r.name == "docmind.perf" and r.message.startswith("chat")]
    assert chat_logs, "chat 分段日志应存在"
    for seg in ("retrieval=", "llm_first_token=", "llm_total=", "total="):
        assert seg in chat_logs[0], f"日志缺分段 {seg}: {chat_logs[0]}"


def test_chat_perf_log_off_silent(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(settings, "perf_log", False)
    db, embedder, vector_store, bm25_index = _seed(tmp_path)
    search = SearchService(embedder, vector_store, db, bm25_index, FakeReranker())
    chat = ChatService(search, MockProvider(delay=0))

    with caplog.at_level(logging.INFO):
        _run_stream(chat, [{"role": "user", "content": "快速排序是什么"}])

    assert not any(r.name == "docmind.perf" for r in caplog.records)


def test_chat_empty_library_no_perf_log(tmp_path, monkeypatch, caplog):
    """空库快捷路径：不做检索、不发 LLM，也不打任何 perf 日志"""
    monkeypatch.setattr(settings, "perf_log", True)
    db = Database(tmp_path / "test.db")
    search = SearchService(FakeEmbedder(), FakeVectorStore(), db, BM25Index(db), FakeReranker())
    chat = ChatService(search, MockProvider(delay=0))

    with caplog.at_level(logging.INFO, logger="docmind.perf"):
        events = _run_stream(chat, [{"role": "user", "content": "随便问问"}])

    assert [e["type"] for e in events] == ["delta", "done"]
    assert not any(r.name == "docmind.perf" for r in caplog.records)
