"""第 3 周：SearchService 三策略集成（假 embedder + 假向量库 + 真实 SQLite，全离线）。"""

import pytest

from app.retrieval.bm25_index import BM25Index
from app.services.search_service import SearchService
from app.storage.db import Database
from tests.helpers import FakeEmbedder, FakeReranker


class FakeVectorStore:
    """内存向量库：存 embedding，按余弦相似度降序返回，接口同 ChromaVectorStore"""

    def __init__(self):
        self._data = {}  # chunk_id -> (text, embedding, meta)

    def add(self, ids, texts, embeddings, metadatas):
        for cid, text, emb, meta in zip(ids, texts, embeddings, metadatas):
            self._data[cid] = (text, emb, meta)

    def query(self, query_embedding, top_k):
        def cosine(emb):
            dot = sum(a * b for a, b in zip(query_embedding, emb))
            n1 = sum(a * a for a in query_embedding) ** 0.5
            n2 = sum(b * b for b in emb) ** 0.5
            return dot / (n1 * n2) if n1 and n2 else 0.0

        ranked = sorted(self._data.items(), key=lambda kv: -cosine(kv[1][1]))
        return [(cid, text, cosine(emb), meta) for cid, (text, emb, meta) in ranked[:top_k]]

    def delete_by_doc(self, doc_id):
        self._data = {k: v for k, v in self._data.items() if v[2]["doc_id"] != doc_id}

    def count(self):
        return len(self._data)


class ExplodingEmbedder(FakeEmbedder):
    """一旦被调用就抛错——用于证明纯 bm25 策略不需要 embedding"""

    def embed(self, texts):
        raise AssertionError("bm25 策略不应调用 embedding")


def _seed(tmp_path):
    """种子数据：两个文档各两块，返回服务组装所需的全部组件"""
    db = Database(tmp_path / "test.db")
    embedder = FakeEmbedder()
    vector_store = FakeVectorStore()
    bm25_index = BM25Index(db)

    doc1 = db.add_document("快速排序", "qs.md", "qs-stored.md", 2)
    doc2 = db.add_document("哈希表", "hash.md", "hash-stored.md", 2)
    db.add_chunks(
        [
            (f"{doc1}-0", doc1, 0, "快速排序是一种分治算法"),
            (f"{doc1}-1", doc1, 1, "平均时间复杂度 O(n log n)"),
            (f"{doc2}-0", doc2, 0, "哈希表通过哈希函数映射键到桶"),
            (f"{doc2}-1", doc2, 1, "哈希冲突用链地址法解决"),
        ]
    )
    texts = [
        "快速排序是一种分治算法",
        "平均时间复杂度 O(n log n)",
        "哈希表通过哈希函数映射键到桶",
        "哈希冲突用链地址法解决",
    ]
    embeddings = embedder.embed(texts)
    vector_store.add(
        ids=[f"{doc1}-0", f"{doc1}-1", f"{doc2}-0", f"{doc2}-1"],
        texts=texts,
        embeddings=embeddings,
        metadatas=[
            {"doc_id": doc1, "seq": 0, "title": "快速排序"},
            {"doc_id": doc1, "seq": 1, "title": "快速排序"},
            {"doc_id": doc2, "seq": 0, "title": "哈希表"},
            {"doc_id": doc2, "seq": 1, "title": "哈希表"},
        ],
    )
    bm25_index.rebuild()
    return db, embedder, vector_store, bm25_index


@pytest.fixture
def search_service(tmp_path):
    db, embedder, vector_store, bm25_index = _seed(tmp_path)
    return SearchService(embedder, vector_store, db, bm25_index)


def test_vector_strategy(search_service):
    results = search_service.search("快速排序", "vector", top_k=10)
    assert results, "向量检索无结果"
    # 全部 4 块都在 top_k 内，排名字段完整；bm25 路未参与
    assert [r["rank_vector"] for r in results] == [1, 2, 3, 4]
    assert all(r["rank_bm25"] is None for r in results)
    assert all(0 <= r["score"] <= 1 for r in results), "向量分数应为余弦相似度"


def test_bm25_strategy_no_embedding_call(tmp_path):
    """纯 bm25：不调 embedding → 未配置 key 也能检索"""
    db = Database(tmp_path / "test.db")
    # 3 文档语料：N=3 时 df=1 的词 idf 为正，命中即正分（避开极小语料退化场景）
    doc_id = db.add_document("快速排序", "qs.md", "qs-stored.md", 1)
    db.add_chunks([(f"{doc_id}-0", doc_id, 0, "快速排序是一种分治算法")])
    other1 = db.add_document("哈希表", "h.md", "h-stored.md", 1)
    db.add_chunks([(f"{other1}-0", other1, 0, "哈希表用哈希函数映射键到桶")])
    other2 = db.add_document("图论", "g.md", "g-stored.md", 1)
    db.add_chunks([(f"{other2}-0", other2, 0, "图的深度优先遍历用栈实现")])
    bm25_index = BM25Index(db)
    service = SearchService(ExplodingEmbedder(), FakeVectorStore(), db, bm25_index)

    results = service.search("快速排序", "bm25", top_k=10)
    assert results and results[0]["doc_id"] == doc_id
    assert results[0]["rank_bm25"] == 1
    assert results[0]["rank_vector"] is None
    assert results[0]["score"] > 0


def test_hybrid_order_matches_rrf(search_service):
    """融合顺序与手工计算的 RRF 分数一致（不依赖 rrf_fuse 内部实现）"""
    vector = search_service.search("快速排序", "vector", top_k=10)
    bm25 = search_service.search("快速排序", "bm25", top_k=10)
    hybrid = search_service.search("快速排序", "hybrid", top_k=10)

    expected: dict[str, float] = {}
    for rank, r in enumerate(vector, start=1):
        expected[r["chunk_id"]] = expected.get(r["chunk_id"], 0.0) + 1 / (60 + rank)
    for rank, r in enumerate(bm25, start=1):
        expected[r["chunk_id"]] = expected.get(r["chunk_id"], 0.0) + 1 / (60 + rank)
    expected_ids = [cid for cid, _ in sorted(expected.items(), key=lambda kv: -kv[1])]

    assert [r["chunk_id"] for r in hybrid] == expected_ids
    bm25_matched = {b["chunk_id"] for b in bm25}
    for r in hybrid:
        assert abs(r["score"] - expected[r["chunk_id"]]) < 1e-6  # 服务层 score 保留 6 位小数
        assert r["rank_vector"] is not None  # 全部 4 块都在向量路 top_k 内
        # bm25 路只有真正命中关键词的块才有排名，其余为 None
        if r["chunk_id"] in bm25_matched:
            assert r["rank_bm25"] is not None
        else:
            assert r["rank_bm25"] is None


def test_rerank_without_reranker_raises(search_service):
    with pytest.raises(RuntimeError, match="重排未配置"):
        search_service.search("快速排序", "vector", rerank=True)


def test_rerank_reorders_and_adds_score(tmp_path):
    """FakeReranker 按查询共有字符数打分：含'快速排序'的分块应被重排到首位"""
    db, embedder, vector_store, bm25_index = _seed(tmp_path)
    service = SearchService(embedder, vector_store, db, bm25_index, FakeReranker())

    results = service.search("快速排序", "vector", top_k=10, rerank=True)
    assert results, "重排后无结果"
    assert results[0]["text"] == "快速排序是一种分治算法"
    assert results[0]["rerank_score"] == 4  # 与查询共有 4 个字符
    assert all(r["rerank_score"] is not None for r in results)
    assert all(r["rank_vector"] is not None for r in results), "检索排名应保留（重排前的名次）"


def test_rerank_truncates_to_top_k(tmp_path):
    db, embedder, vector_store, bm25_index = _seed(tmp_path)
    service = SearchService(embedder, vector_store, db, bm25_index, FakeReranker())

    results = service.search("快速排序", "vector", top_k=2, rerank=True)
    assert len(results) == 2


def test_unknown_strategy(search_service):
    with pytest.raises(ValueError):
        search_service.search("快速排序", "quantum")
