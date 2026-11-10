"""LLM 抽象。

只定义一个核心能力：流式对话。换供应商（DeepSeek → 通义/智谱）只需
新增实现类，chat_service 完全不用改。
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator


class LLMProvider(ABC):
    name: str = "base"

    async def complete(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        """非流式回复，可返回原始 assistant tool_calls；旧 Provider 可不实现。"""
        raise NotImplementedError("当前 Provider 不支持工具调用")

    @abstractmethod
    def chat_stream(self, messages: list[dict]) -> AsyncIterator[str]:
        """流式对话，逐段产出增量文本。

        messages: [{"role": "user"|"assistant"|"system", "content": str}, ...]
        """
