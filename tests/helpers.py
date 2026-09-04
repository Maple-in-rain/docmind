"""测试共享工具：确定性假 embedding（离线测试用）。

真实 embedding 走网络 API，测试中用 md5 哈希生成的确定性向量替代——
这正是 EmbeddingProvider 抽象的价值：测试不依赖外部服务。
"""

import hashlib

from app.embeddings.base import EmbeddingProvider


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
