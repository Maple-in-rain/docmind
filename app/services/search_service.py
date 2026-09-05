"""检索编排：vector / bm25 / hybrid 三策略 + RRF 融合。

设计（面试可讲）：
- 两路检索只在需要时计算：纯 bm25 不调 embedding API（未配 key 也可用）；
- hybrid 用 RRF 融合排名而非分数——余弦相似度与 BM25 分不同量纲不可比，
  排名才是可比量纲；
- 排名信息随结果返回（rank_vector / rank_bm25），检索调试面板据此
  可视化"混合检索为什么更好"。
"""

from ..embeddings.base import EmbeddingProvider
from ..retrieval.bm25_index import BM25Index
from ..retrieval.hybrid import rrf_fuse
from ..retrieval.vector_store import VectorStore
from ..storage.db import Database


class SearchService:
    def __init__(
        self,
        embedder: EmbeddingProvider,
        vector_store: VectorStore,
        db: Database,
        bm25_index: BM25Index,
    ):
        self.embedder = embedder
        self.vector_store = vector_store
        self.db = db
        self.bm25_index = bm25_index

    def search(self, query: str, strategy: str = "vector", top_k: int = 10, rerank: bool = False) -> list[dict]:
        if rerank:
            raise ValueError("重排尚未实现（接入 bge-reranker 后开放）")

        vector_hits: list[tuple[str, float]] = []
        bm25_hits: list[tuple[str, float]] = []

        # 两路检索只在需要时计算
        if strategy in ("vector", "hybrid"):
            query_embedding = self.embedder.embed([query])[0]
            vector_hits = [
                (chunk_id, score)
                for chunk_id, _text, score, _meta in self.vector_store.query(query_embedding, top_k)
            ]
        if strategy in ("bm25", "hybrid"):
            bm25_hits = self.bm25_index.search(query, top_k)

        if strategy == "vector":
            merged = vector_hits
        elif strategy == "bm25":
            merged = bm25_hits
        elif strategy == "hybrid":
            merged = rrf_fuse([vector_hits, bm25_hits], top_k)
        else:
            raise ValueError(f"未知检索策略: {strategy}")

        rank_vector = {cid: i for i, (cid, _s) in enumerate(vector_hits, start=1)}
        rank_bm25 = {cid: i for i, (cid, _s) in enumerate(bm25_hits, start=1)}

        chunks = {c["chunk_id"]: c for c in self.db.get_chunks_by_ids([cid for cid, _s in merged])}
        return [
            {
                "text": chunks[cid]["text"],
                "chunk_id": cid,
                "doc_id": chunks[cid]["doc_id"],
                "seq": chunks[cid]["seq"],
                "title": chunks[cid]["title"],
                "score": round(score, 6),
                "rank_vector": rank_vector.get(cid),
                "rank_bm25": rank_bm25.get(cid),
            }
            for cid, score in merged
            if cid in chunks  # 防御：陈旧索引里已删除的 chunk 直接丢弃
        ]
