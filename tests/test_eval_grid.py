"""网格实验离线冒烟：FakeEmbedder + FakeReranker + 迷你语料/测试集。

验证评估框架的组装正确性（不验证检索质量本身——那需要真实 embedding）。
段落级 qrels：FakeEmbedder 对相同文本给相同向量（相似度 1.0），
不同文本的 md5 向量相似度远低于 1.0，因此阈值 0.99 时只有与出处段落
完全相同的块算相关。
"""

from app.chunking.fixed_chunker import FixedChunker

from eval.evaluate import prepare_chunk_cache, prepare_qrels, run_cell, run_grid
from tests.helpers import FakeEmbedder, FakeReranker

MINI_CORPUS = [
    {"name": "doc-a.md", "text": "# 快速排序\n\n快速排序是一种分治算法。平均时间复杂度 O(n log n)。\n\n" * 8},
    {"name": "doc-b.md", "text": "# 哈希表\n\n哈希表用哈希函数映射键。哈希冲突用链地址法解决。\n\n" * 8},
]


def _mini_testset():
    """出处段落取每篇文档的第 1 个分块（chunk_size=64, overlap=0），
    与测试格子用同一分块参数，保证存在完全相同文本的块。"""
    testset = []
    for i, doc in enumerate(MINI_CORPUS):
        chunks = FixedChunker(64, 0).split(doc["text"])
        testset.append(
            {
                "id": i + 1,
                "question": f"问题{i + 1}",
                "answer": "答案",
                "doc": doc["name"],
                "source_passage": chunks[0].text,
            }
        )
    return testset


def _qrels_for(chunk_cache, embedder, testset, threshold=0.99):
    return prepare_qrels(chunk_cache, MINI_CORPUS, embedder, testset, threshold)


def test_run_cell_offline(tmp_path):
    cfg = {"name": "t", "chunk_size": 64, "overlap": 0, "strategy": "hybrid", "rerank": True}
    embedder = FakeEmbedder()
    testset = _mini_testset()
    chunk_cache = prepare_chunk_cache(MINI_CORPUS, embedder, chunk_sizes=(64,), overlaps=(0,))
    qrels = _qrels_for(chunk_cache, embedder, testset)
    row = run_cell(cfg, embedder, FakeReranker(), chunk_cache, testset,
                   qrels[(64, 0)], tmp_path / "work")

    assert row["n_queries"] == 2
    assert row["n_skipped"] == 0
    for metric in ("recall@3", "recall@5", "recall@10", "mrr@3", "mrr@5", "mrr@10"):
        assert 0 <= row[metric] <= 1, f"{metric} 越界: {row[metric]}"


def test_run_cell_skips_unknown_doc(tmp_path):
    testset = _mini_testset() + [
        {"id": 9, "question": "x", "answer": "y", "doc": "不存在的文档.md", "source_passage": "文本"}
    ]
    cfg = {"name": "t", "chunk_size": 64, "overlap": 0, "strategy": "vector", "rerank": False}
    embedder = FakeEmbedder()
    chunk_cache = prepare_chunk_cache(MINI_CORPUS, embedder, chunk_sizes=(64,), overlaps=(0,))
    qrels = _qrels_for(chunk_cache, embedder, testset)
    row = run_cell(cfg, embedder, FakeReranker(), chunk_cache, testset,
                   qrels[(64, 0)], tmp_path / "work")
    assert row["n_queries"] == 2
    assert row["n_skipped"] == 1  # 未知文档的测试项被跳过，不炸


def test_run_grid_writes_csv(tmp_path):
    cells = [
        {"name": "c1", "chunk_size": 64, "overlap": 0, "strategy": "hybrid", "rerank": False},
        {"name": "c2", "chunk_size": 64, "overlap": 0, "strategy": "hybrid", "rerank": True},
    ]
    rows = run_grid(
        cells,
        FakeEmbedder(),
        FakeReranker(),
        MINI_CORPUS,
        _mini_testset(),
        output_csv=tmp_path / "out.csv",
        workdir_root=tmp_path / "workdirs",
        passage_threshold=0.99,
    )
    assert len(rows) == 2
    assert (tmp_path / "out.csv").exists()
    content = (tmp_path / "out.csv").read_text(encoding="utf-8-sig")
    assert "c1" in content and "recall@10" in content


def test_run_grid_resumes_from_csv(tmp_path):
    """断点续跑：CSV 中已完成的格子跳过，只补缺"""
    from eval.evaluate import _append_csv_row, load_csv_rows

    csv_path = tmp_path / "out.csv"
    _append_csv_row(
        csv_path,
        {"name": "c1", "chunk_size": 64, "overlap": 0, "strategy": "hybrid", "rerank": False,
         "n_queries": 2, "n_skipped": 0, "recall@3": 1.0, "recall@5": 1.0, "recall@10": 1.0,
         "mrr@3": 1.0, "mrr@5": 1.0, "mrr@10": 1.0},
    )
    cells = [
        {"name": "c1", "chunk_size": 64, "overlap": 0, "strategy": "hybrid", "rerank": False},
        {"name": "c2", "chunk_size": 64, "overlap": 0, "strategy": "hybrid", "rerank": True},
    ]
    rows = run_grid(
        cells,
        FakeEmbedder(),
        FakeReranker(),
        MINI_CORPUS,
        _mini_testset(),
        output_csv=csv_path,
        workdir_root=tmp_path / "workdirs",
        passage_threshold=0.99,
    )
    assert [r["name"] for r in rows] == ["c2"]  # c1 已存在被跳过
    assert {r["name"] for r in load_csv_rows(csv_path)} == {"c1", "c2"}
