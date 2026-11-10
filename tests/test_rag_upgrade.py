import asyncio
import json

from app.services.query_rewriter import QueryRewriter
from app.services.chat_service import ChatService


class Completion:
    def __init__(self, content=None, error=False):
        self.content, self.error, self.calls = content, error, 0

    async def complete(self, messages, tools=None):
        self.calls += 1
        if self.error:
            raise RuntimeError("offline")
        return {"role": "assistant", "content": self.content}


def test_rewrite_skips_single_turn_and_restores_failure():
    llm = Completion(error=True)
    rewriter = QueryRewriter(llm)
    assert asyncio.run(rewriter.rewrite("什么是 Redis", [])) == "什么是 Redis"
    assert llm.calls == 0
    assert asyncio.run(rewriter.rewrite("那怎么解决", [{"role": "user", "content": "缓存穿透"}])) == "那怎么解决"


def test_rewrite_uses_valid_query_and_rejects_invalid_output():
    llm = Completion(json.dumps({"query": "Redis 缓存穿透怎么解决"}))
    rewriter = QueryRewriter(llm)
    history = [{"role": "user", "content": "缓存穿透是什么"}]
    assert asyncio.run(rewriter.rewrite("那怎么解决", history)) == "Redis 缓存穿透怎么解决"
    for invalid in ('{"query":""}', '{"query":123}', 'not json', '{"query":"' + '字' * 2001 + '"}'):
        llm.content = invalid
        assert asyncio.run(rewriter.rewrite("原问题", history)) == "原问题"


def test_rewrite_timeout_falls_back():
    class Slow:
        async def complete(self, messages, tools=None):
            await asyncio.sleep(1)
    assert asyncio.run(QueryRewriter(Slow(), timeout=0.001).rewrite("原问题", [{"role": "user", "content": "主题"}])) == "原问题"


def test_evidence_sources_match_exact_prompt_budget():
    sources = [{"text": "字" * 1000, "doc_id": 1, "seq": i, "title": "标题", "chunk_id": f"1-{i}"} for i in range(20)]
    selected = ChatService._select_sources(sources)
    assert sum(len(s["text"]) for s in selected) <= 3200
    assert all(len(s["text"]) <= 600 for s in selected)
    references = ChatService._build_references(selected)
    assert all(f'[{i}]' in references for i in range(1, len(selected) + 1))
    assert selected[-1]["text"] in references
    assert len(selected) < len(sources)


def test_rewrite_diagnostics_report_original_actual_and_fallback(monkeypatch, caplog):
    import logging
    from app.config import settings
    monkeypatch.setattr(settings, "perf_log", True)
    with caplog.at_level(logging.INFO, logger="docmind.perf"):
        asyncio.run(QueryRewriter(Completion(error=True)).rewrite("那怎么解决", [{"role": "user", "content": "缓存穿透"}]))
    assert "query_rewrite" in caplog.text
    assert "fallback" in caplog.text
    assert "那怎么解决" in caplog.text
    assert "elapsed_ms=" in caplog.text


def test_chat_rewrite_reaches_search_but_preserves_generation_question(monkeypatch):
    from types import SimpleNamespace
    from app.config import settings
    class LLM(Completion):
        async def chat_stream(self, messages):
            self.generation = messages
            yield "回答 [1]"
    class Search:
        vector_store = SimpleNamespace(count=lambda: 1)
        def search(self, query, *args):
            self.query = query
            return [{"text": "证" * 1000, "chunk_id": "1-0", "doc_id": 1,
                     "seq": 0, "title": "方案", "rerank_score": .9, "score": .8}]
    llm = LLM('{"query":"缓存穿透怎么解决"}')
    search = Search()
    chat = ChatService(search, llm)
    history = [{"role": "user", "content": "缓存穿透是什么"}, {"role": "assistant", "content": "说明"}]
    messages = history + [{"role": "user", "content": "那怎么解决"}]
    async def run():
        return [e async for e in chat.stream_chat(messages)]
    monkeypatch.setattr(settings, "query_rewrite_enabled", True)
    events = asyncio.run(run())
    assert search.query == "缓存穿透怎么解决"
    assert llm.generation[-1] == messages[-1]
    assert llm.generation[1:3] == history
    source = next(e["sources"][0] for e in events if e["type"] == "sources")
    assert source["text"] in llm.generation[0]["content"]
    assert len(source["text"]) == 600
    llm.calls = 0
    monkeypatch.setattr(settings, "query_rewrite_enabled", False)
    asyncio.run(run())
    assert search.query == "那怎么解决"
    assert llm.calls == 0
