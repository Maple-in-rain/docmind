"""向量存储抽象 + Chroma 实现。

当前实现为 Chroma（单机嵌入式，零运维，支持 metadata 过滤）；
若数据量增长到百万级 chunk，可新增 Milvus 实现类，上层服务无需改动
——这就是抽象的价值。
"""

from abc import ABC, abstractmethod
from pathlib import Path

import chromadb

from ..config import settings


class VectorStore(ABC):
    @abstractmethod
    def add(self, ids, texts, embeddings, metadatas) -> None:
        """批量写入向量"""

    @abstractmethod
    def query(self, query_embedding, top_k):
        """查询，返回 [(chunk_id, text, similarity, metadata)]，按相似度降序"""

    @abstractmethod
    def delete_by_doc(self, doc_id: int) -> None:
        """删除某文档的全部向量"""

    @abstractmethod
    def count(self) -> int:
        """向量总数"""


class ChromaVectorStore(VectorStore):
    def __init__(self, persist_dir: Path | None = None, dim: int = 1024):
        self.persist_dir = persist_dir or settings.data_dir / "chroma"
        self.client = chromadb.PersistentClient(path=str(self.persist_dir))
        self.collection = self._get_or_create_collection(settings.collection_name, dim)

    def _get_or_create_collection(self, name: str, dim: int):
        if name in [c.name for c in self.client.list_collections()]:
            col = self.client.get_collection(name)
            stored_dim = int(col.metadata.get("dim", 0))
            if stored_dim and stored_dim != dim:
                raise RuntimeError(
                    f"向量维度不一致：库中 {stored_dim} 维，当前 embedding 模型 {dim} 维。"
                    f"更换 embedding 模型后必须重建向量库，请删除 {self.persist_dir} 后重启。"
                )
            return col
        return self.client.create_collection(
            name, metadata={"hnsw:space": "cosine", "dim": dim}
        )

    def add(self, ids, texts, embeddings, metadatas) -> None:
        if ids:
            self.collection.add(
                ids=ids, documents=texts, embeddings=embeddings, metadatas=metadatas
            )

    def query(self, query_embedding, top_k):
        res = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )
        out = []
        for chunk_id, text, distance, meta in zip(
            res["ids"][0], res["documents"][0], res["distances"][0], res["metadatas"][0]
        ):
            out.append((chunk_id, text, 1 - distance, meta))  # cosine 距离 → 相似度
        return out

    def delete_by_doc(self, doc_id: int) -> None:
        self.collection.delete(where={"doc_id": doc_id})

    def count(self) -> int:
        return self.collection.count()
