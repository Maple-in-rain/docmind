"""测试共享工具：确定性假 embedding / 假重排（离线测试用）。

真实 embedding/rerank 走网络 API，测试中用确定性假实现替代——
这正是 EmbeddingProvider / RerankerProvider 抽象的价值：测试不依赖外部服务。
"""

import hashlib

from app.embeddings.base import EmbeddingProvider
from app.reranking.base import RerankerProvider


class FakeEmbedder(EmbeddingProvider):
    """确定性假 embedding：md5 哈希前 8 字节归一化，8 维"""

    name = "fake-md5"
    dim = 8

    def embed(self, texts):
        out = []
        for t in texts:
            digest = hashlib.md5(t.encode("utf-8")).digest()[: self.dim]
            out.append([b / 255.0 for b in digest])
        return out


class FakeReranker(RerankerProvider):
    """确定性假重排：按文档与查询的共有字符数打分（仅验证链路，无语义）"""

    name = "fake-char-overlap"

    def rerank(self, query, documents, top_n=None):
        qset = set(query)
        scored = [(i, sum(1 for ch in doc if ch in qset)) for i, doc in enumerate(documents)]
        scored.sort(key=lambda kv: (-kv[1], kv[0]))  # 分数相同按下标稳定排序
        return scored[:top_n] if top_n else scored
