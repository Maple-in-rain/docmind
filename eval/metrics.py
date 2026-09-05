"""检索质量评估指标：recall@k / MRR@k（手写实现）。

为什么不调 ragas/trec_eval 而是手写？求职者视角的答案：
指标定义只有几行公式，手写实现 + 手工小例单测，
证明的是"理解指标在测什么"而不只是"会调库"。

口径：
- 相关单位是「文档」（doc_id），不是分块——分块边界随 chunk_size 变化，
  用文档级指标才能在网格实验中公平比较不同分块配置；
- recall@k = 前 k 个结果命中的相关文档数 / 相关文档总数（衡量"找没找全"）；
- MRR@k = 1 / 首个相关文档的排名，k 名内无命中记 0（衡量"找得快不快"）。
"""


def recall_at_k(relevant_ids: set[str], retrieved_ids: list[str], k: int) -> float:
    if not relevant_ids:
        return 0.0
    hits = set(retrieved_ids[:k]) & set(relevant_ids)
    return len(hits) / len(relevant_ids)


def mrr_at_k(relevant_ids: set[str], retrieved_ids: list[str], k: int) -> float:
    for rank, doc_id in enumerate(retrieved_ids[:k], start=1):
        if doc_id in set(relevant_ids):
            return 1.0 / rank
    return 0.0


def evaluate(
    queries: list[tuple[set[str], list[str]]],
    k_values: tuple[int, ...] = (3, 5, 10),
) -> dict[str, float]:
    """批量评估。

    queries: [(相关文档集合, 检索返回的文档序列), ...]（检索序列须已去重）
    返回各指标的平均值，如 {"recall@5": 0.87, "mrr@10": 0.62}。
    """
    if not queries:
        return {}
    out: dict[str, float] = {}
    for k in k_values:
        out[f"recall@{k}"] = sum(recall_at_k(r, s, k) for r, s in queries) / len(queries)
        out[f"mrr@{k}"] = sum(mrr_at_k(r, s, k) for r, s in queries) / len(queries)
    return out
