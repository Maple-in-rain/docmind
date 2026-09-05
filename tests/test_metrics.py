"""评估指标手写实现的单元测试（手工小例验证公式正确性）。"""

from eval.metrics import evaluate, mrr_at_k, recall_at_k


def test_recall_at_k_hand_example():
    relevant = {"a", "b", "c"}
    retrieved = ["a", "x", "b", "y"]
    assert recall_at_k(relevant, retrieved, k=3) == 2 / 3
    assert recall_at_k(relevant, retrieved, k=1) == 1 / 3
    assert recall_at_k(relevant, retrieved, k=10) == 2 / 3  # k 超出结果数时取全部


def test_recall_at_k_empty_relevant():
    assert recall_at_k(set(), ["a"], 5) == 0.0


def test_recall_at_k_duplicates_do_not_double_count():
    # 相关集合是 set，重复出现在结果中只计一次命中
    assert recall_at_k({"a"}, ["a", "a", "a"], 3) == 1.0


def test_mrr_at_k_hand_example():
    assert mrr_at_k({"a"}, ["x", "a", "b"], 5) == 0.5
    assert mrr_at_k({"a"}, ["a"], 5) == 1.0
    assert mrr_at_k({"a"}, ["x", "y"], 2) == 0.0  # k 名内无命中
    assert mrr_at_k({"a"}, ["x", "a"], 1) == 0.0  # 命中在第 2 名，k=1 不计


def test_evaluate_averages():
    queries = [({"a"}, ["a"]), ({"a"}, ["x", "a"])]
    out = evaluate(queries, k_values=(5,))
    assert out["recall@5"] == 1.0
    assert out["mrr@5"] == (1.0 + 0.5) / 2


def test_evaluate_empty():
    assert evaluate([]) == {}
