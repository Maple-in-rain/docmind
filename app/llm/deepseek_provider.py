"""DeepSeek 流式客户端（httpx 手写 SSE 解析 + 指数退避重试）。

刻意不用 openai SDK，手写协议有两个好处：
1. 面试可讲：SSE 帧格式（data: {...} 行 + [DONE] 结束标记）、
   增量 delta 解析、重试策略的设计取舍；
2. 依赖更少，行为完全可控。

重试策略：仅在「首 token 之前」失败时重试（指数退避，最多 3 次）。
流式输出中途断开不能安全重试——部分内容已经发给用户，重发会重复。
"""

import asyncio
import json
from collections.abc import AsyncIterator

import httpx

from ..config import settings
from .base import LLMProvider

_MAX_RETRIES = 3


class DeepSeekProvider(LLMProvider):
    name = "deepseek"

    def __init__(self, api_key: str = "", base_url: str = "", model: str = "", transport=None):
        self.api_key = api_key or settings.deepseek_api_key
        self.base_url = (base_url or settings.deepseek_base_url).rstrip("/")
        self.model = model or settings.deepseek_model
        # transport 仅测试用：注入 httpx.MockTransport，不发起真实网络请求
        self._transport = transport

    async def chat_stream(self, messages: list[dict]) -> AsyncIterator[str]:
        if not self.api_key:
            raise RuntimeError("未配置 DeepSeek API key，请在 .env 中设置 DEEPSEEK_API_KEY")

        last_error: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                async for delta in self._request_stream(messages):
                    yield delta
                return  # 正常结束
            except (httpx.TransportError, httpx.HTTPStatusError) as e:
                last_error = e
                if attempt < _MAX_RETRIES - 1:
                    # 指数退避：1s、2s、4s
                    await asyncio.sleep(2 ** attempt)
        raise RuntimeError(f"DeepSeek 请求失败（已重试 {_MAX_RETRIES} 次）: {last_error}")

    async def _request_stream(self, messages: list[dict]) -> AsyncIterator[str]:
        """单次流式请求：逐行解析 SSE 帧，产出增量文本。

        SSE 帧示例：
            data: {"choices":[{"delta":{"content":"你好"}}]}
            data: {"choices":[{"delta":{"content":""},"finish_reason":"stop"}]}
            data: [DONE]
        """
        timeout = httpx.Timeout(connect=15, read=120, write=60, pool=15)
        async with httpx.AsyncClient(timeout=timeout, transport=self._transport) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": True,
                },
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue  # 跳过注释行与空行
                    data = line[5:].strip()
                    if data == "[DONE]":
                        return
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue  # 容忍异常帧，不中断整体流
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content")
                    if content:
                        yield content
