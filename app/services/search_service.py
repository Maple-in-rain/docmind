"""检索编排：vector / bm25 / hybrid 三策略 + RRF 融合 + 可选重排。

设计（面试可讲）：
- 两路检索只在需要时计算：纯 bm25 不调 embedding API（未配 key 也可用）；
- hybrid 用 RRF 融合排名而非分数——余弦相似度与 BM25 分不同量纲不可比，
  排名才是可比量纲；
- 重排采用「宽召回 + 精排」：先多路检索取 top_k × 3 的候选池，
  再让 cross-encoder（bge-reranker）对候选做精排截断到 top_k。
  cross-encoder 在 1024 维向量之外完整看过查询与文档的交互，
  排序质量优于双塔，但开销大——所以只对候选池做，不对全库做；
- 排名信息随结果返回（rank_vector / rank_bm25 为重排前的检索排名），
  检索调试面板据此可视化"混合检索/重排为什么更好"。
"""

from ..embeddings.base import EmbeddingProvider
from ..reranking.base import RerankerProvider
from ..retrieval.bm25_index import BM25Index
from ..retrieval.hybrid import rrf_fuse
from ..retrieval.vector_store import VectorStore
from ..storage.db import Database

_RERANK_CANDIDATE_MULTIPLIER = 3  # 重排候选池 = top_k × 3（宽召回，精排截断）
_MIN_CANDIDATES = 10


class SearchService:
    def __init__(
        self,
        embedder: EmbeddingProvider,
        vector_store: VectorStore,
        db: Database,
        bm25_index: BM25Index,
        reranker: RerankerProvider | None = None,
    ):
        self.embedder = embedder
        self.vector_store = vector_store
        self.db = db
        self.bm25_index = bm25_index
        self.reranker = reranker

    def search(self, query: str, strategy: str = "vector", top_k: int = 10, rerank: bool = False) -> list[dict]:
        if rerank and self.reranker is None:
            raise RuntimeError("重排未配置（缺少 RerankerProvider）")

        # 重排模式用更大的候选池，精排后截断到 top_k
        candidate_k = max(top_k * _RERANK_CANDIDATE_MULTIPLIER, _MIN_CANDIDATES) if rerank else top_k

        vector_hits: list[tuple[str, float]] = []
        bm25_hits: list[tuple[str, float]] = []

        # 两路检索只在需要时计算
        if strategy in ("vector", "hybrid"):
            query_embedding = self.embedder.embed([query])[0]
            vector_hits = [
                (chunk_id, score)
                for chunk_id, _text, score, _meta in self.vector_store.query(query_embedding, candidate_k)
            ]
        if strategy in ("bm25", "hybrid"):
            bm25_hits = self.bm25_index.search(query, candidate_k)

        if strategy == "vector":
            merged = vector_hits
        elif strategy == "bm25":
            merged = bm25_hits
        elif strategy == "hybrid":
            merged = rrf_fuse([vector_hits, bm25_hits], candidate_k)
        else:
            raise ValueError(f"未知检索策略: {strategy}")

        # 重排前的检索排名（结果中始终保留，供调试面板对比）
        rank_vector = {cid: i for i, (cid, _s) in enumerate(vector_hits, start=1)}
        rank_bm25 = {cid: i for i, (cid, _s) in enumerate(bm25_hits, start=1)}

        chunks = {c["chunk_id"]: c for c in self.db.get_chunks_by_ids([cid for cid, _s in merged])}
        merged = [(cid, s) for cid, s in merged if cid in chunks]  # 防御：陈旧索引残留丢弃

        # 精排：候选池文本送 cross-encoder，按下标重排并截断
        rerank_scores: dict[str, float] = {}
        if rerank and merged:
            ranked = self.reranker.rerank(
                query,
                [chunks[cid]["text"] for cid, _s in merged],
                top_n=top_k,
            )
            rerank_scores = {merged[i][0]: score for i, score in ranked}
            merged = [(merged[i][0], merged[i][1]) for i, _score in ranked]

        return [
            {
                "text": chunks[cid]["text"],
                "chunk_id": cid,
                "doc_id": chunks[cid]["doc_id"],
                "seq": chunks[cid]["seq"],
                "title": chunks[cid]["title"],
                "score": round(score, 6),
                "rerank_score": round(rerank_scores[cid], 6) if cid in rerank_scores else None,
                "rank_vector": rank_vector.get(cid),
                "rank_bm25": rank_bm25.get(cid),
            }
            for cid, score in merged
        ]
