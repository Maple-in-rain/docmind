"""RRF（Reciprocal Rank Fusion）多路检索融合。

把每路检索的排名融合为一个排序：score(d) = Σ_i 1 / (k + rank_i(d))。
只用排名不用原始分数——不同路的分数不可比（余弦相似度 vs BM25 分），
排名才是可比的量纲；k 越大越平滑，k=60 是经典默认（Cormack et al., 2009）。
"""

RRF_K = 60


def rrf_fuse(
    ranked_lists: list[list[tuple[str, float]]],
    top_k: int,
    k: int = RRF_K,
) -> list[tuple[str, float]]:
    """ranked_lists: 各路检索结果 [(id, score)]，各自已按分数降序。
    返回融合后的 [(id, rrf_score)] 降序，最多 top_k 个。
    """
    fused: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, (doc_id, _score) in enumerate(ranked, start=1):
            fused[doc_id] = fused.get(doc_id, 0.0) + 1.0 / (k + rank)
    return sorted(fused.items(), key=lambda item: -item[1])[:top_k]
