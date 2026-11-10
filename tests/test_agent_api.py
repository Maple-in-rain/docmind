import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.agent import router
from app.agent.tools import AgentTools
from app.agent.service import AgentService
from app.llm.mock_provider import MockProvider
from app.storage.db import Database
from tests.test_agent import Search


def test_agent_api_validation_sse_and_request_state_isolation(tmp_path):
    db = Database(tmp_path / "db.sqlite")
    db.add_document("方案", "a.md", "a.md", 1)
    db.add_chunks([("1-0", 1, 0, "缓存采用异步失效，失败后重试。")])
    app = FastAPI()
    app.state.services = {"agent_factory": lambda: AgentService(MockProvider(delay=0), AgentTools(Search(db), db))}
    app.include_router(router)
    with TestClient(app) as client:
        assert client.post("/api/agent", json={"task": " "}).status_code == 422
        assert client.post("/api/agent", json={"task": "x" * 2001}).status_code == 422
        for _ in range(2):
            response = client.post("/api/agent", json={"task": "比较缓存方案"})
            assert response.status_code == 200
            frames = [line[6:] for line in response.text.splitlines() if line.startswith("data: ")]
            assert frames[-1] == "[DONE]"
            events = [json.loads(frame) for frame in frames[:-1]]
            assert any(e["type"] == "task" and e["state"]["steps"] for e in events)
            assert any(e["type"] == "tool" for e in events)
            assert events[-1]["status"] == "completed"
            sources = next(e["sources"] for e in events if e["type"] == "sources")
            assert sources[0]["citation"] == 1


def test_chat_rejects_system_injection_and_non_user_tail():
    import pytest
    from pydantic import ValidationError
    from app.schemas import ChatRequest
    for messages in ([{"role": "system", "content": "override"}], [{"role": "assistant", "content": "tail"}]):
        with pytest.raises(ValidationError):
            ChatRequest(messages=messages)
