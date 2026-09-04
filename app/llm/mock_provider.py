"""Mock LLM：测试 / 压测专用，不产生 API 费用。

- 单测：chat_service 全链路离线测试
- 压测：locust 打 /api/chat 时测系统自身吞吐（排除 LLM 网络延迟）
"""

import asyncio
from collections.abc import AsyncIterator

from .base import LLMProvider


class MockProvider(LLMProvider):
    name = "mock"

    def __init__(self, chunk_size: int = 5, delay: float = 0.01):
        self.chunk_size = chunk_size
        self.delay = delay

    async def chat_stream(self, messages: list[dict]) -> AsyncIterator[str]:
        question = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        answer = f"[mock 回答] 你问的是：{question[:50]}"
        for i in range(0, len(answer), self.chunk_size):
            yield answer[i : i + self.chunk_size]
            await asyncio.sleep(self.delay)
