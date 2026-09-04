"""分块策略抽象。

分块是 RAG 质量的关键变量之一：太碎则语义不完整，太大则召回精度下降。
不同策略（固定窗口 / 标题结构）通过评估实验对比，见 eval/evaluate.py。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class Chunk:
    text: str
    meta: dict = field(default_factory=dict)  # 策略附加信息（如所属标题）


class BaseChunker(ABC):
    name: str = "base"

    @abstractmethod
    def split(self, text: str) -> list[Chunk]:
        """把整篇文档切分为若干块。空文本返回空列表。"""
