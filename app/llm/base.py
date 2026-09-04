"""LLM 抽象。

只定义一个核心能力：流式对话。换供应商（DeepSeek → 通义/智谱）只需
新增实现类，chat_service 完全不用改。
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator


class LLMProvider(ABC):
    name: str = "base"

    @abstractmethod
    def chat_stream(self, messages: list[dict]) -> AsyncIterator[str]:
        """流式对话，逐段产出增量文本。

        messages: [{"role": "user"|"assistant"|"system", "content": str}, ...]
        """
