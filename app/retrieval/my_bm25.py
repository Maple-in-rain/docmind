"""自写 BM25（教学与对拍用）。

生产索引走 rank-bm25（BM25Okapi），本模块用纯手写实现复刻其全部语义，
用于逐分对拍验证（tests/test_bm25.py，误差要求 < 1e-6）——
面试可讲："我手推过 BM25 公式，并用对拍证明了实现正确性"。

与 rank-bm25 BM25Okapi 的语义对齐点（逐行核对过其源码）：
1. idf = ln(N - df + 0.5) - ln(df + 0.5)，df 为包含该词的文档数；
2. 负 idf 统一替换为 epsilon * average_idf，其中 average_idf 基于
   替换前的全部原始 idf 计算（epsilon 默认 0.25）；
3. 打分：Σ_q (idf(q) or 0) × tf(k1+1) / (tf + k1(1 - b + b·dl/avgdl))
   ——注意 `or 0` 语义：idf 为 0.0 或词不在索引中时该项为 0；
   负 eps 保持负值，因此分数可能为负（高 df 词场景）。
"""

import math
from collections import Counter


class MyBM25:
    def __init__(self, corpus: list[list[str]], k1: float = 1.5, b: float = 0.75, epsilon: float = 0.25):
        if not corpus:
            raise ValueError("BM25 语料不能为空")
        self.k1 = k1
        self.b = b
        self.epsilon = epsilon

        self.corpus_size = len(corpus)
        self.doc_len = [len(doc) for doc in corpus]
        self.avgdl = sum(self.doc_len) / self.corpus_size
        self.doc_freqs = [Counter(doc) for doc in corpus]
        self._build_idf()

    def _build_idf(self) -> None:
        # df: 每个词出现在多少个文档中
        df: Counter = Counter()
        for freqs in self.doc_freqs:
            df.update(freqs.keys())

        idf_raw: dict[str, float] = {}
        idf_sum = 0.0
        for word, count in df.items():
            v = math.log(self.corpus_size - count + 0.5) - math.log(count + 0.5)
            idf_raw[word] = v
            idf_sum += v

        # 平均 idf 在负值替换之前计算（与 rank-bm25 一致）
        avg_idf = idf_sum / len(idf_raw)
        eps = self.epsilon * avg_idf
        self.idf = {w: (eps if v < 0 else v) for w, v in idf_raw.items()}

    def get_scores(self, query: list[str]) -> list[float]:
        """返回每个文档对 query 的 BM25 分数（顺序同语料）"""
        scores = [0.0] * self.corpus_size
        for term in query:
            idf = self.idf.get(term) or 0  # 与 rank-bm25 的 (idf or 0) 语义一致
            if idf == 0.0:
                continue
            for i, doc_len in enumerate(self.doc_len):
                tf = self.doc_freqs[i].get(term, 0)
                if tf == 0:
                    continue
                scores[i] += idf * (
                    tf * (self.k1 + 1)
                    / (tf + self.k1 * (1 - self.b + self.b * doc_len / self.avgdl))
                )
        return scores
