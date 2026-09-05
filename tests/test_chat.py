"""问答流水线离线集成测试：假 embedding + 假重排 + 假向量库 + mock LLM。

ChatService 第 3 周起复用 SearchService（hybrid + 重排），测试用全假栈
离线跑通"检索 → prompt 拼装 → 流式输出"链路。
"""

import asyncio

from app.llm.mock_provider import MockProvider
from app.retrieval.bm25_index import BM25Index
from app.services.chat_service import ChatService
from app.services.search_service import SearchService
from app.storage.db import Database
from tests.helpers import FakeEmbedder, FakeReranker, FakeVectorStore


async def _collect(agen) -> list[dict]:
    return [e async for e in agen]


def _build_service(tmp_path) -> tuple[ChatService, FakeVectorStore, Database, BM25Index]:
    db = Database(tmp_path / "test.db")
    embedder = FakeEmbedder()
    vs = FakeVectorStore()
    bm25 = BM25Index(db)
    search = SearchService(embedder, vs, db, bm25, FakeReranker())
    return ChatService(search, MockProvider(delay=0)), vs, db, bm25


def _seed_chunk(vs, db, bm25, text, doc_id, seq=0, title="文档"):
    """同时写入假向量库与 SQLite（SearchService 从两边取数据），并重建 BM25"""
    if db.get_document(doc_id) is None:
        db.add_document(title, title, title, 1)  # chunks.doc_id 有外键约束
    cid = f"{doc_id}-{seq}"
    db.add_chunks([(cid, doc_id, seq, text)])
    vs.add(ids=[cid], texts=[text], embeddings=[[0.1] * 8],
           metadatas=[{"doc_id": doc_id, "seq": seq, "title": title}])
    bm25.rebuild()


def test_stream_chat_event_order(tmp_path):
    service, vs, db, bm25 = _build_service(tmp_path)
    _seed_chunk(vs, db, bm25, "RAG 是检索增强生成的缩写。", 1, 0, "RAG简介")
    _seed_chunk(vs, db, bm25, "线性代数中奇异值分解用于降维。", 2, 0, "线代笔记")

    events = asyncio.run(
        _collect(service.stream_chat([{"role": "user", "content": "什么是 RAG"}]))
    )

    # 事件顺序：sources → delta... → done
    assert events[0]["type"] == "sources"
    assert len(events[0]["sources"]) == 2
    assert events[-1]["type"] == "done"
    answer = "".join(e["content"] for e in events if e["type"] == "delta")
    assert "[mock 回答]" in answer


def test_stream_chat_rerank_score_in_sources(tmp_path):
    """来源的相关度字段优先取重排分（评估定稿：重排是最优链路）"""
    service, vs, db, bm25 = _build_service(tmp_path)
    _seed_chunk(vs, db, bm25, "RAG 是检索增强生成的缩写。", 1, 0, "RAG简介")
    _seed_chunk(vs, db, bm25, "线性代数中奇异值分解用于降维。", 2, 0, "线代笔记")

    events = asyncio.run(
        _collect(service.stream_chat([{"role": "user", "content": "什么是 RAG"}]))
    )
    sources = events[0]["sources"]
    assert all(s["score"] is not None for s in sources)
    # FakeReranker 按共有字符数打分：含 RAG 的片段相关度更高
    assert sources[0]["title"] == "RAG简介"


def test_empty_knowledge_base(tmp_path):
    service, _, _, _ = _build_service(tmp_path)
    events = asyncio.run(
        _collect(service.stream_chat([{"role": "user", "content": "什么是 RAG"}]))
    )
    assert events[0]["type"] == "delta"
    assert "知识库还是空的" in events[0]["content"]
    assert events[-1]["type"] == "done"


def test_build_references_truncates(tmp_path):
    service, _, _, _ = _build_service(tmp_path)
    long_text = "字" * 5000
    refs = service._build_references(
        [{"text": long_text, "doc_id": 1, "seq": 0, "title": "长文档", "score": 0.9}]
    )
    assert "[1]（来源：长文档）" in refs
    assert len(refs) < 1000  # 单片段被截断到 600 字符预算内


def test_trim_history():
    history = [{"role": "user" if i % 2 == 0 else "assistant", "content": f"msg{i}"} for i in range(10)]
    trimmed = ChatService._trim_history(history)
    assert len(trimmed) == 6  # 最近 3 轮 = 6 条消息
    assert trimmed[0]["content"] == "msg4"


def test_non_stream_chat_aggregates(tmp_path):
    service, vs, db, bm25 = _build_service(tmp_path)
    _seed_chunk(vs, db, bm25, "内容片段", 1, 0, "t")
    answer, sources = asyncio.run(
        service.chat([{"role": "user", "content": "问题"}])
    )
    assert "[mock 回答]" in answer
    assert len(sources) == 1
