"""问答流水线离线集成测试：假 embedding + mock LLM。"""

import asyncio

from app.llm.mock_provider import MockProvider
from app.retrieval.vector_store import ChromaVectorStore
from app.services.chat_service import ChatService
from tests.helpers import FakeEmbedder


async def _collect(agen) -> list[dict]:
    return [e async for e in agen]


def _build_service(tmp_path) -> tuple[ChatService, ChromaVectorStore]:
    embedder = FakeEmbedder()
    vs = ChromaVectorStore(tmp_path / "chroma", dim=embedder.dim)
    service = ChatService(embedder, vs, MockProvider(delay=0))
    return service, vs


def test_stream_chat_event_order(tmp_path):
    service, vs = _build_service(tmp_path)
    vs.add(
        ids=["1-0", "1-1"],
        texts=["RAG 是检索增强生成的缩写。", "线性代数中奇异值分解用于降维。"],
        embeddings=[[0.1] * 8, [0.2] * 8],
        metadatas=[
            {"doc_id": 1, "seq": 0, "title": "RAG简介"},
            {"doc_id": 2, "seq": 0, "title": "线代笔记"},
        ],
    )

    events = asyncio.run(
        _collect(service.stream_chat([{"role": "user", "content": "什么是 RAG"}]))
    )

    # 事件顺序：sources → delta... → done
    assert events[0]["type"] == "sources"
    assert len(events[0]["sources"]) == 2
    assert events[-1]["type"] == "done"
    answer = "".join(e["content"] for e in events if e["type"] == "delta")
    assert "[mock 回答]" in answer


def test_empty_knowledge_base(tmp_path):
    service, _ = _build_service(tmp_path)
    events = asyncio.run(
        _collect(service.stream_chat([{"role": "user", "content": "什么是 RAG"}]))
    )
    assert events[0]["type"] == "delta"
    assert "知识库还是空的" in events[0]["content"]
    assert events[-1]["type"] == "done"


def test_build_references_truncates(tmp_path):
    service, _ = _build_service(tmp_path)
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
    service, vs = _build_service(tmp_path)
    vs.add(
        ids=["1-0"],
        texts=["内容片段"],
        embeddings=[[0.1] * 8],
        metadatas=[{"doc_id": 1, "seq": 0, "title": "t"}],
    )
    answer, sources = asyncio.run(
        service.chat([{"role": "user", "content": "问题"}])
    )
    assert "[mock 回答]" in answer
    assert len(sources) == 1
