import asyncio
import json

import httpx
import pytest

from app.llm.deepseek_provider import DeepSeekProvider


def test_complete_preserves_tool_calls_and_sends_tools():
    message = {"role": "assistant", "content": None, "tool_calls": [
        {"id": "call-1", "type": "function", "function": {"name": "search_documents", "arguments": '{"query":"缓存"}'}}
    ]}

    def handler(request):
        body = json.loads(request.content)
        assert body["stream"] is False
        assert body["tools"][0]["function"]["name"] == "search_documents"
        assert body["max_tokens"] == 2048
        return httpx.Response(200, json={"choices": [{"message": message, "finish_reason": "tool_calls"}]})

    provider = DeepSeekProvider(api_key="test", transport=httpx.MockTransport(handler))
    result = asyncio.run(provider.complete([{"role": "user", "content": "test"}], tools=[
        {"type": "function", "function": {"name": "search_documents"}}
    ]))
    assert result == message


def test_complete_rejects_truncated_response():
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={"choices": [
        {"message": {"content": "partial"}, "finish_reason": "length"}
    ]}))
    with pytest.raises(RuntimeError, match="截断"):
        asyncio.run(DeepSeekProvider(api_key="test", transport=transport).complete([]))
