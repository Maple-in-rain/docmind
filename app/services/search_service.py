"""检索编排。

第 1 周仅向量检索；第 3 周接入 BM25 索引与 RRF 混合融合，
strategy 参数即为扩展点。
"""

from ..embeddings.base import EmbeddingProvider
from ..retrieval.vector_store import VectorStore
from ..storage.db import Database


class SearchService:
    def __init__(self, embedder: EmbeddingProvider, vector_store: VectorStore, db: Database):
        self.embedder = embedder
        self.vector_store = vector_store
        self.db = db

    def search(self, query: str, strategy: str = "vector", top_k: int = 10, rerank: bool = False) -> list[dict]:
        if strategy != "vector":
            raise ValueError(f"检索策略 {strategy} 尚未实现（第 3 周接入 BM25 / 混合检索）")

        query_embedding = self.embedder.embed([query])[0]
        results = self.vector_store.query(query_embedding, top_k)
        return [
            {
                "text": text,
                "chunk_id": chunk_id,
                "doc_id": meta["doc_id"],
                "seq": meta.get("seq"),
                "title": meta.get("title", ""),
                "score": round(score, 4),
                "rank_vector": rank,
                "rank_bm25": None,
            }
            for rank, (chunk_id, text, score, meta) in enumerate(results, start=1)
        ]
