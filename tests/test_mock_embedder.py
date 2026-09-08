"""MockEmbedder 单测：确定性、维度约束（与 bge-m3 一致才能复用真实向量库）。"""

from app.embeddings.mock_embedder import MockEmbedder


def test_dim_matches_bge_m3():
    assert MockEmbedder.dim == 1024


def test_embed_is_deterministic():
    embedder = MockEmbedder()
    texts = ["什么是RAG", "奇异值分解", "python 生成器"]
    assert embedder.embed(texts) == embedder.embed(texts)


def test_embed_shape():
    embedder = MockEmbedder()
    vectors = embedder.embed(["a", "bb", "ccc"])
    assert len(vectors) == 3
    assert all(len(v) == 1024 for v in vectors)


def test_different_texts_different_vectors():
    embedder = MockEmbedder()
    v1, v2 = embedder.embed(["同一个文本", "另一个文本"])
    assert v1 != v2


def test_empty_input():
    assert MockEmbedder().embed([]) == []
