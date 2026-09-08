"""Mock 重排：压测场景 2 专用，确定性字符重叠打分，零网络开销。

与 MockEmbedder/MockProvider 相同定位：让压测测的是系统自身吞吐
（FastAPI + Chroma + SQLite + BM25 + 编排代码），排除外部 API 延迟。
"""

from .base import RerankerProvider


class MockReranker(RerankerProvider):
    name = "mock-char-overlap"

    def rerank(self, query: str, documents: list[str], top_n: int | None = None) -> list[tuple[int, float]]:
        qset = set(query)
        scored = [(i, float(sum(1 for ch in doc if ch in qset))) for i, doc in enumerate(documents)]
        scored.sort(key=lambda kv: (-kv[1], kv[0]))  # 同分按下标稳定
        return scored[:top_n] if top_n else scored
