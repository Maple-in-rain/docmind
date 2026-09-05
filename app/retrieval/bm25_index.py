"""BM25 关键词索引：jieba 分词 + rank-bm25（BM25Okapi）。

设计决策：
- SQLite 是持久化事实源，索引为内存态，启动与文档增删后全量重建——
  个人知识库 <100 文档时重建耗时毫秒级，简单可靠；磁盘序列化/增量合并
  是数据量增长后的扩展方向（见 README Roadmap）；
- 索引与查询共用同一个 _tokenize，杜绝"建库和查询分词不一致"这类隐性 bug。
"""

import logging

import jieba
from rank_bm25 import BM25Okapi

from ..storage.db import Database

jieba.setLogLevel(logging.WARNING)  # 屏蔽词典加载日志，保持启动输出干净


def _tokenize(text: str) -> list[str]:
    """jieba 精确模式分词，过滤空白 token。索引/查询必须共用此函数。"""
    return [w for w in jieba.lcut(text) if w.strip()]


class BM25Index:
    def __init__(self, db: Database):
        self.db = db
        self._chunk_ids: list[str] = []
        self._bm25: BM25Okapi | None = None
        self.rebuild()  # 构造即从 SQLite 全量重建（启动时恢复索引）

    def rebuild(self) -> None:
        """从 SQLite 全量重建索引（文档增删后调用）"""
        chunks = self.db.get_all_chunks()
        self._chunk_ids = [c["chunk_id"] for c in chunks]
        corpus = [_tokenize(c["text"]) for c in chunks]
        self._bm25 = BM25Okapi(corpus) if corpus else None

    def search(self, query: str, top_k: int = 10) -> list[tuple[str, float]]:
        """返回 [(chunk_id, score)] 按分数降序。

        常规语料（词表足够大）下命中即正分，0/负分视为无匹配截断；
        极小语料（1~3 个分块）时 average_idf 为负，BM25Okapi 的 epsilon
        调整后所有分数 ≤ 0——此时负分代表命中（越大越好），仍返回命中块，
        保证小知识库（刚上传第一个文档时）关键词检索可用。
        """
        if self._bm25 is None:
            return []
        scores = self._bm25.get_scores(_tokenize(query))
        order = sorted(range(len(scores)), key=lambda i: -scores[i])
        positive = any(s > 0 for s in scores)
        hits: list[tuple[str, float]] = []
        for i in order:
            score = float(scores[i])
            if len(hits) >= top_k:
                break
            if score > 0 or (score < 0 and not positive):
                hits.append((self._chunk_ids[i], score))
            else:
                break  # 已按分数降序，首个未命中分块之后不可能再有命中
        return hits
