"""Embedding 抽象。

注意：不同模型的向量维度不同。维度已写入向量库元数据并在启动时校验，
换 provider 后维度变化必须重建向量库，否则检索结果全部错误。
"""

from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    name: str = "base"
    dim: int = 0  # 向量维度，向量库据此初始化并校验

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """批量向量化，返回与输入等长的向量列表（同步实现，调用方自行决定线程模型）"""
