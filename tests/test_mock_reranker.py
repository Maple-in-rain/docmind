"""MockReranker 单测：下标契约、排序稳定性、top_n 截断、确定性。"""

from app.reranking.mock_reranker import MockReranker


def test_returns_original_indices():
    ranked = MockReranker().rerank("检索增强生成", ["生成器与迭代器", "检索增强生成（RAG）", "快速排序"])
    assert all(isinstance(i, int) and 0 <= i < 3 for i, _ in ranked)
    assert sorted(i for i, _ in ranked) == [0, 1, 2]  # 下标完整无重复


def test_sorted_by_overlap_descending():
    ranked = MockReranker().rerank("检索增强生成", ["快速排序", "检索增强生成（RAG）", "检索与排序"])
    assert ranked[0][0] == 1  # 完全包含查询词的那条排第一


def test_tie_break_stable_by_index():
    reranker = MockReranker()
    docs = ["苹果", "香蕉", "苹果"]
    ranked = reranker.rerank("苹果", docs)
    assert [i for i, _ in ranked] == [0, 2, 1]  # 同分按下标升序


def test_top_n_truncates():
    ranked = MockReranker().rerank("abc", ["a", "ab", "abc", "abcd"], top_n=2)
    assert len(ranked) == 2
    assert [i for i, _ in ranked] == [2, 3]  # 重叠最多的两条（3 分同分，下标升序）


def test_empty_documents():
    assert MockReranker().rerank("query", []) == []


def test_deterministic():
    reranker = MockReranker()
    docs = ["aa", "bb", "ab"]
    assert reranker.rerank("ab", docs) == reranker.rerank("ab", docs)
