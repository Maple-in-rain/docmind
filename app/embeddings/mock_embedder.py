"""Mock embedding：压测场景 2 专用，确定性哈希向量，不产生 API 费用。

关键约束：dim 必须 = 1024（与 bge-m3 一致）——ChromaVectorStore 启动时
校验集合元数据维度，dim 一致才能直接复用场景 1 已入库的真实向量集合，
省去重建语料。检索结果无语义（哈希向量），但代码路径与真实链路完全一致，
吞吐测量不受影响。
"""

import hashlib

from .base import EmbeddingProvider


class MockEmbedder(EmbeddingProvider):
    name = "mock-md5"
    dim = 1024  # 与 BAAI/bge-m3 一致，复用现有 Chroma 集合不触发维度校验报错

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for t in texts:
            digest = hashlib.sha256(t.encode("utf-8")).digest()  # 32 字节
            out.append([digest[i % 32] / 255.0 for i in range(self.dim)])  # 循环拉伸到 1024 维
        return out
