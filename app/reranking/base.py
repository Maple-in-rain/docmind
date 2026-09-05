"""重排插件抽象。"""

from abc import ABC, abstractmethod


class RerankerProvider(ABC):
    """把检索候选按「查询-文档相关性」精排。

    与 EmbeddingProvider 相同的插件哲学：换重排模型只需新增实现类。
    """

    @abstractmethod
    def rerank(self, query: str, documents: list[str], top_n: int | None = None) -> list[tuple[int, float]]:
        """返回 [(原文档下标, 相关性分数)]，按分数降序；top_n 限制返回数量。

        注意返回的是 documents 的下标而非文本，调用方按下标取回原文，
        避免长文本在结果中重复传递。
        """
