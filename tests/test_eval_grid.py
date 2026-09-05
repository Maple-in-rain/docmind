"""网格实验离线冒烟：FakeEmbedder + FakeReranker + 迷你语料/测试集。

验证评估框架的组装正确性（不验证检索质量本身——那需要真实 embedding）。
"""

from eval.evaluate import prepare_chunk_cache, run_cell, run_grid
from tests.helpers import FakeEmbedder, FakeReranker

MINI_CORPUS = [
    {"name": "doc-a.md", "text": "# 快速排序\n\n快速排序是一种分治算法。平均时间复杂度 O(n log n)。\n\n" * 8},
    {"name": "doc-b.md", "text": "# 哈希表\n\n哈希表用哈希函数映射键。哈希冲突用链地址法解决。\n\n" * 8},
]
MINI_TESTSET = [
    {"id": 1, "question": "快速排序的时间复杂度是多少", "answer": "O(n log n)", "doc": "doc-a.md"},
    {"id": 2, "question": "哈希冲突怎么解决", "answer": "链地址法", "doc": "doc-b.md"},
]


def test_run_cell_offline(tmp_path):
    cfg = {"name": "t", "chunk_size": 64, "overlap": 10, "strategy": "hybrid", "rerank": True}
    embedder = FakeEmbedder()
    chunk_cache = prepare_chunk_cache(MINI_CORPUS, embedder, chunk_sizes=(64,), overlaps=(10,))
    row = run_cell(cfg, embedder, FakeReranker(), chunk_cache, MINI_TESTSET, tmp_path / "work")

    assert row["n_queries"] == 2
    for metric in ("recall@3", "recall@5", "recall@10", "mrr@3", "mrr@5", "mrr@10"):
        assert 0 <= row[metric] <= 1, f"{metric} 越界: {row[metric]}"


def test_run_cell_skips_unknown_doc(tmp_path):
    testset = MINI_TESTSET + [{"id": 9, "question": "x", "answer": "y", "doc": "不存在的文档.md"}]
    cfg = {"name": "t", "chunk_size": 64, "overlap": 10, "strategy": "vector", "rerank": False}
    embedder = FakeEmbedder()
    chunk_cache = prepare_chunk_cache(MINI_CORPUS, embedder, chunk_sizes=(64,), overlaps=(10,))
    row = run_cell(cfg, embedder, FakeReranker(), chunk_cache, testset, tmp_path / "work")
    assert row["n_queries"] == 2  # 未知文档的测试项被跳过，不炸


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
        MINI_TESTSET,
        output_csv=tmp_path / "out.csv",
        workdir_root=tmp_path / "workdirs",
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
         "n_queries": 2, "recall@3": 1.0, "recall@5": 1.0, "recall@10": 1.0,
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
        MINI_TESTSET,
        output_csv=csv_path,
        workdir_root=tmp_path / "workdirs",
    )
    assert [r["name"] for r in rows] == ["c2"]  # c1 已存在被跳过
    assert {r["name"] for r in load_csv_rows(csv_path)} == {"c1", "c2"}
