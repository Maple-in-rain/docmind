import asyncio
import json

import pytest

from app.agent.tools import AgentTools
from app.agent.service import AgentService
from app.storage.db import Database


class Search:
    def __init__(self, db):
        self.db = db
        self.queries = []

    def search(self, query, strategy, top_k, rerank, cancel_event=None):
        self.queries.append(query)
        return [{**c, "title": "方案", "score": .5} for c in self.db.get_all_chunks()][:top_k]


@pytest.fixture
def tools(tmp_path):
    db = Database(tmp_path / "test.db")
    doc = db.add_document("方案甲", "a.md", "a.md", 3)
    db.add_chunks([(f"{doc}-{i}", doc, i, text) for i, text in enumerate([
        "先写数据库再删缓存。", "失败时使用重试任务。", "不保证强一致性。"
    ])])
    return AgentTools(Search(db), db)


def call(name, args, identifier="one"):
    return {"id": identifier, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


class Scripted:
    def __init__(self, responses):
        self.responses, self.messages = iter(responses), []

    async def complete(self, messages, tools=None):
        self.messages.append(json.loads(json.dumps(messages)))
        return next(self.responses)


def collect(service):
    async def run():
        return [e async for e in service.stream("对比缓存一致性方案")]
    return asyncio.run(run())


def test_tools_validate_arguments_context_and_evidence(tools):
    result = tools.execute("read_context", {"doc_id": 1, "seq": 1})
    assert len(result["sources"]) == 3
    assert [s["citation"] for s in result["sources"]] == [1, 2, 3]
    assert tools.execute("read_context", {"doc_id": 1, "seq": 99})["error"]
    assert tools.execute("read_context", {"doc_id": 1, "seq": 0, "radius": 100})["error"]
    assert tools.execute("search_documents", {"query": "x", "unexpected": 1})["error"]
    assert tools.execute("delete_document", {"doc_id": 1})["error"]
    state = tools.execute("update_task", {"steps": ["一致性", "恢复"], "completed": [0], "gaps": ["性能数据"]})
    assert state["state"]["completed"] == ["一致性"]
    assert tools.execute("update_task", {"steps": ["一致性"], "completed": [3], "gaps": []})["error"]


def test_model_observes_tool_result_and_can_search_again(tools):
    llm = Scripted([
        {"role": "assistant", "content": None, "tool_calls": [call("search_documents", {"query": "一致性"})]},
        {"role": "assistant", "content": None, "tool_calls": [call("search_documents", {"query": "失败恢复"}, "two")]},
        {"role": "assistant", "content": "对比结论：方案使用重试 [2]。待确认：恢复时限。"},
    ])
    events = collect(AgentService(llm, tools))
    assert tools.search.queries == ["一致性", "失败恢复"]
    assert llm.messages[1][-1]["role"] == "tool"
    assert llm.messages[1][-1]["tool_call_id"] == "one"
    assert "失败时使用重试" in llm.messages[1][-1]["content"]
    assert events[-1]["status"] == "completed"
    assert events[-1]["tool_calls"] == 2


def test_multicall_budget_counts_individually_and_stops(tools):
    llm = Scripted([{"role": "assistant", "content": None, "tool_calls": [
        call("list_documents", {}, str(i)) for i in range(5)
    ]}])
    events = collect(AgentService(llm, tools, max_calls=2))
    assert events[-1]["status"] == "tool_limit"
    assert events[-1]["tool_calls"] == 2
    assert len([e for e in events if e["type"] == "tool"]) == 2


def test_duplicate_calls_consume_budget_but_do_not_execute_twice(tools):
    llm = Scripted([{"role": "assistant", "tool_calls": [
        call("search_documents", {"query": "一致性"}, "1"), call("search_documents", {"query": "一致性"}, "2")
    ]}])
    events = collect(AgentService(llm, tools, max_calls=2))
    assert len(tools.search.queries) == 1
    assert events[-1]["tool_calls"] == 2


def test_invalid_json_returns_error_to_model(tools):
    bad = call("search_documents", {})
    bad["function"]["arguments"] = "not json"
    llm = Scripted([{"role": "assistant", "tool_calls": [bad]}, {"role": "assistant", "content": "资料不足"}])
    events = collect(AgentService(llm, tools))
    assert json.loads(llm.messages[1][-1]["content"])["error"]
    assert events[-1]["status"] == "no_evidence"


def test_timeout_and_invalid_citations_are_explicit(tools):
    class Slow:
        async def complete(self, messages, tools=None):
            await asyncio.sleep(1)
    events = collect(AgentService(Slow(), tools, timeout=.001))
    assert events[-1]["status"] == "timeout"
    llm = Scripted([
        {"role": "assistant", "tool_calls": [call("search_documents", {"query": "缓存"})]},
        {"role": "assistant", "content": "不实编号 [99]"},
    ])
    events = collect(AgentService(llm, AgentTools(tools.search, tools.db)))
    assert events[-1]["status"] == "invalid_citations"
    assert "[99]" not in "".join(e.get("content", "") for e in events)


def test_evidence_text_is_bounded_and_sources_are_stable(tools):
    tools.db.add_chunks([("1-3", 1, 3, "长" * 5000)])
    first = tools.execute("read_context", {"doc_id": 1, "seq": 3, "radius": 0})["sources"][0]
    second = tools.execute("read_context", {"doc_id": 1, "seq": 3, "radius": 0})["sources"][0]
    assert first["citation"] == second["citation"]
    assert len(first["text"]) == 1200
    assert len(tools.sources) == 1


def test_exact_tool_budget_still_allows_final_report_without_more_tools(tools):
    llm = Scripted([
        {"role": "assistant", "tool_calls": [call("search_documents", {"query": "缓存"})]},
        {"role": "assistant", "content": "结论见文档 [1]。待确认：恢复时限。"},
    ])
    events = collect(AgentService(llm, tools, max_calls=1))
    assert events[-1]["status"] == "completed"
    assert events[-1]["tool_calls"] == 1


def test_timeout_during_tool_cannot_add_evidence_later(tools):
    import time
    def slow(*args, **kwargs):
        time.sleep(.05)
        return [{"chunk_id": "1-0", "doc_id": 1, "seq": 0, "title": "方案", "text": "延迟证据"}]
    tools.search.search = slow
    llm = Scripted([{"role": "assistant", "tool_calls": [call("search_documents", {"query": "缓存"})]}])
    events = collect(AgentService(llm, tools, timeout=.01))
    assert events[-1]["status"] == "timeout"
    assert tools.sources == []


def test_cancelled_embedding_does_not_start_rerank(tmp_path):
    import threading
    from app.services.search_service import SearchService
    from tests.helpers import FakeVectorStore
    stop = threading.Event()
    class Embedder:
        def embed(self, texts):
            stop.set()
            return [[.1] * 8]
    class Reranker:
        def rerank_cancellable(self, *args, **kwargs):
            pytest.fail("取消后不应发起重排")
    db = Database(tmp_path / "cancel.db")
    search = SearchService(Embedder(), FakeVectorStore(), db, None, Reranker())
    with pytest.raises(RuntimeError, match="停止"):
        search.search("缓存", "hybrid", 5, True, cancel_event=stop)


def test_cancelled_reranker_does_not_retry():
    import threading
    import httpx
    from app.reranking.siliconflow_reranker import SiliconFlowRerankerProvider
    stop = threading.Event()
    calls = []
    def handler(request):
        calls.append(request)
        stop.set()
        return httpx.Response(429)
    reranker = SiliconFlowRerankerProvider(api_key="test", transport=httpx.MockTransport(handler))
    with pytest.raises(RuntimeError, match="停止"):
        reranker.rerank_cancellable("缓存", ["资料"], cancel_event=stop)
    assert len(calls) == 1


def test_task_completion_uses_bounded_step_indices(tools):
    result = tools.execute("update_task", {"steps": ["检索一致性", "检查恢复方式"], "completed": [0], "gaps": []})
    assert result["state"]["completed"] == ["检索一致性"]
    assert tools.execute("update_task", {"steps": ["检索一致性"], "completed": [1], "gaps": []})["error"]
