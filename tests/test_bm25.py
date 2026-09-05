"""第 3 周：MyBM25 对拍 + RRF 融合 + BM25Index 集成（全离线）。

对拍思路：同一份预分词语料/查询分别喂给自写 MyBM25 与 rank-bm25，
逐分比较。分词器不参与对拍（两实现共用输入），验证的是打分数学。
"""

import random

import pytest
from rank_bm25 import BM25Okapi

from app.retrieval.bm25_index import BM25Index, _tokenize
from app.retrieval.hybrid import rrf_fuse
from app.retrieval.my_bm25 import MyBM25
from app.storage.db import Database

# 词汇表故意包含高频词（"的"等在多篇文档出现 → 负 idf → epsilon 调整路径）
_VOCAB = ["检索", "增强", "生成", "向量", "模型", "数据库", "文档", "分词", "的", "与"]


def _random_corpus(seed: int, n_docs: int = 8, vocab: list[str] | None = None) -> list[list[str]]:
    rng = random.Random(seed)
    vocab = vocab or _VOCAB
    return [[rng.choice(vocab) for _ in range(rng.randint(2, 20))] for _ in range(n_docs)]


def _random_query(seed: int, vocab: list[str] | None = None) -> list[str]:
    rng = random.Random(seed)
    vocab = vocab or _VOCAB
    return [rng.choice(vocab) for _ in range(rng.randint(1, 5))]


# ---- MyBM25 对拍 ----

@pytest.mark.parametrize("seed", [0, 1, 42, 2026])
def test_my_bm25_matches_rank_bm25(seed):
    corpus = _random_corpus(seed)
    query = _random_query(seed + 100)
    mine = MyBM25(corpus).get_scores(query)
    theirs = BM25Okapi(corpus).get_scores(query)
    assert len(mine) == len(theirs) == len(corpus)
    for a, b in zip(mine, theirs):
        assert abs(a - b) < 1e-6, f"seed={seed}: {a} vs {b}"


def test_my_bm25_matches_with_repeated_query_terms():
    """查询词重复时逐词累加，同样必须一致"""
    corpus = _random_corpus(7)
    query = ["检索", "检索", "模型", "的"]
    mine = MyBM25(corpus).get_scores(query)
    theirs = BM25Okapi(corpus).get_scores(query)
    for a, b in zip(mine, theirs):
        assert abs(a - b) < 1e-6


def test_negative_idf_epsilon_case():
    """高 df 词（出现在全部文档）产生负 idf → epsilon 调整，分数可为负。

    手推（N=2, corpus=[["a","b"], ["a"]]，query=["a","b"]）：
      idf_a = ln(0.5) - ln(2.5) ≈ -1.609（负），idf_b = ln(1.5) - ln(1.5) = 0
      avg_idf = (-1.609 + 0) / 2 ≈ -0.805 → eps = 0.25 × avg ≈ -0.201
      doc0: tf_a=1, dl=2, 分母 = 1 + 1.5(1-0.75+0.75×2/1.5) = 2.875 → -0.175
      doc1: tf_a=1, dl=1, 分母 = 1 + 1.5(0.25+0.5) = 2.125 → -0.237
    两篇分数都为负——负 eps 保持负值（rank-bm25 的 `or 0` 语义）。
    """
    corpus = [["a", "b"], ["a"]]
    query = ["a", "b"]
    mine = MyBM25(corpus).get_scores(query)
    theirs = BM25Okapi(corpus).get_scores(query)
    assert all(s < 0 for s in mine), "全包含词应产生负分"
    for a, b in zip(mine, theirs):
        assert abs(a - b) < 1e-6


def test_my_bm25_empty_corpus_raises():
    with pytest.raises(ValueError):
        MyBM25([])


# ---- RRF 融合 ----

def test_rrf_fuse_basic_order():
    # b 在两条路都出现（第 1、2 名），a 只在 A 路第 1，c 只在 B 路第 2
    a_list = [("a", 1.0), ("b", 0.5)]
    b_list = [("b", 1.0), ("c", 0.9)]
    fused = rrf_fuse([a_list, b_list], top_k=10)
    assert [doc_id for doc_id, _ in fused] == ["b", "a", "c"]
    # 分数 = Σ 1/(k+rank)：b = 1/61 + 1/62 > a = 1/61 > c = 1/62
    scores = dict(fused)
    assert abs(scores["b"] - (1 / 61 + 1 / 62)) < 1e-12
    assert abs(scores["a"] - 1 / 61) < 1e-12
    assert abs(scores["c"] - 1 / 62) < 1e-12


def test_rrf_fuse_empty_and_top_k():
    assert rrf_fuse([], top_k=5) == []
    assert rrf_fuse([[("x", 1.0)]], top_k=0) == []


def test_rrf_fuse_uses_rank_not_score():
    """RRF 只用排名：原始分数不同但排名相同 → 融合分数相同"""
    x = rrf_fuse([[("a", 0.99)]], top_k=5)[0][1]
    y = rrf_fuse([[("a", 0.01)]], top_k=5)[0][1]
    assert x == y


# ---- BM25Index 集成（真实 SQLite）----

def _seed_db(tmp_path) -> Database:
    """3 文档 4 分块：语料足够大（N=4），df=1 的词 idf 为正，命中即正分"""
    db = Database(tmp_path / "test.db")
    docs = [
        ("检索笔记", ["向量检索依赖 embedding 的语义相似度", "BM25 是经典的关键词检索算法"]),
        ("排序算法", ["快速排序是一种分治算法"]),
        ("图论入门", ["图的深度优先遍历用栈实现"]),
    ]
    for title, texts in docs:
        doc_id = db.add_document(title, f"{title}.md", f"stored-{title}.md", len(texts))
        db.add_chunks([(f"{doc_id}-{i}", doc_id, i, text) for i, text in enumerate(texts)])
    return db


def test_bm25_index_rebuild_and_search(tmp_path):
    db = _seed_db(tmp_path)
    index = BM25Index(db)  # 构造即从 SQLite 全量重建
    hits = index.search("BM25", top_k=10)
    assert hits and hits[0][0].endswith("-1"), "应命中包含 BM25 关键词的分块"
    assert all(s > 0 for _cid, s in hits)


def test_bm25_index_after_delete(tmp_path):
    db = _seed_db(tmp_path)
    index = BM25Index(db)
    doc = next(d for d in db.list_documents() if d["title"] == "检索笔记")
    db.delete_document(doc["doc_id"])
    index.rebuild()
    assert index.search("BM25", top_k=10) == []


def test_bm25_index_empty_db(tmp_path):
    db = Database(tmp_path / "empty.db")
    assert BM25Index(db).search("任何词") == []


def test_bm25_index_tiny_corpus_still_hits(tmp_path):
    """退化场景：单分块语料 average_idf 为负，BM25Okapi 分数全为负——
    索引仍应返回命中块（负分越大越好），保证小知识库关键词检索可用。"""
    db = Database(tmp_path / "tiny.db")
    doc_id = db.add_document("笔记", "n.md", "n-stored.md", 1)
    db.add_chunks([(f"{doc_id}-0", doc_id, 0, "快速排序是一种分治算法")])
    index = BM25Index(db)
    hits = index.search("快速排序", top_k=10)
    assert hits and hits[0][0] == f"{doc_id}-0"
    assert hits[0][1] < 0  # 退化场景分数为负，但相对排序仍有效


def test_tokenize_filters_blank():
    tokens = _tokenize("  BM25  算法 ")
    assert tokens and all(t == t.strip() and t for t in tokens)
    assert _tokenize("   ") == []
    assert _tokenize("") == []
