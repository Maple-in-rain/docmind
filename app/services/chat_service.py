"""问答流水线：检索 → prompt 拼装 → LLM 流式输出。

事件流顺序：sources（引用来源，先发给前端展示）→ delta（逐段增量）→ done。
引用来源在生成前就能拿到，先发给前端可以让引用卡片立即渲染。

检索策略（第 3 周评估定稿）：hybrid + 重排。网格实验（eval/results/）证明
重排是检索质量的最大单一变量，混合检索在重排下稳定最优；默认参数
chunk 768 / 无重叠 / hybrid / rerank on 均来自评估数据而非拍脑袋。

Prompt 设计（面试可讲）：
- 系统提示 + 参考资料放在 messages 最前面——DeepSeek 对稳定前缀做
  上下文缓存，命中后输入成本大幅下降；
- 历史对话放在中间，当前问题放最后（LLM 对尾部注意力最集中）；
- 每个片段限长 + 总预算截断，防止超长文档撑爆上下文窗口。
"""

import asyncio
from collections.abc import AsyncIterator

from ..config import settings
from ..llm.base import LLMProvider
from ..perf import SegmentTimer, logger
from .search_service import SearchService

# 上下文预算：单片段最长字符数 / 全部片段总预算（中文按字符近似）
_CHUNK_MAX_CHARS = 600
_TOTAL_BUDGET_CHARS = 3200
_HISTORY_MAX_TURNS = 3  # 保留最近 3 轮对话

_SYSTEM_PROMPT = (
    "你是 DocMind 知识助手。请仅依据下方【参考资料】回答用户问题。\n"
    "要求：\n"
    "1. 回答中用 [1]、[2] 标注引用来源编号（对应参考资料的编号）；\n"
    "2. 如果资料中没有相关信息，如实回答“资料中未找到相关内容”，不要编造；\n"
    "3. 回答简洁、结构清晰。"
)


class ChatService:
    def __init__(self, search_service: SearchService, llm: LLMProvider):
        self.search_service = search_service
        self.llm = llm

    async def chat(self, messages: list[dict], top_k: int = 5) -> tuple[str, list[dict]]:
        """非流式版本：聚合成 (完整回答, 引用来源)"""
        answer_parts: list[str] = []
        sources: list[dict] = []
        async for event in self.stream_chat(messages, top_k):
            if event["type"] == "delta":
                answer_parts.append(event["content"])
            elif event["type"] == "sources":
                sources = event["sources"]
        return "".join(answer_parts), sources

    async def stream_chat(self, messages: list[dict], top_k: int = 5) -> AsyncIterator[dict]:
        """事件流：{"type": "sources"/"delta"/"done", ...}"""
        question = messages[-1]["content"].strip()
        history = messages[:-1]

        # 知识库为空：直接提示，不发请求
        if self.search_service.vector_store.count() == 0:
            yield {"type": "delta", "content": "知识库还是空的，请先在左侧上传文档。"}
            yield {"type": "done"}
            return

        # 1. 检索：hybrid + 重排（评估定稿的默认策略）；
        #    内部是同步 HTTP 调用，放进线程池避免阻塞事件循环
        pt = SegmentTimer(settings.perf_log)
        results = await asyncio.to_thread(
            self.search_service.search, question, "hybrid", top_k, True
        )
        pt.segment("retrieval")  # 含 embed/vector/bm25/db_fetch/rerank 全部

        sources = [
            {
                "text": r["text"],
                "doc_id": r["doc_id"],
                "seq": r["seq"],
                "title": r["title"],
                # 展示相关度优先用重排分（cross-encoder 与查询的真实相关性）
                "score": round(r["rerank_score"], 4) if r["rerank_score"] is not None else r["score"],
            }
            for r in results
        ]

        # 2. prompt 拼装：系统提示+资料（稳定前缀）→ 历史 → 问题
        references = self._build_references(sources)
        llm_messages = [{"role": "system", "content": _SYSTEM_PROMPT + references}]
        llm_messages.extend(self._trim_history(history))
        llm_messages.append({"role": "user", "content": question})

        # 3. 先发来源，再流式输出回答
        yield {"type": "sources", "sources": sources}
        first_delta = True
        async for delta in self.llm.chat_stream(llm_messages):
            if first_delta:
                pt.segment("llm_first_token")  # 首 token 延迟：网络 + LLM 排队
                first_delta = False
            yield {"type": "delta", "content": delta}
        pt.segment("llm_total")  # LLM 全量生成（含首 token 前的等待）
        if settings.perf_log:
            logger.info("chat 分段耗时 [%.24s...] %s", question, pt.summary_ms())
        yield {"type": "done"}

    @staticmethod
    def _build_references(sources: list[dict]) -> str:
        """组装参考资料块，编号 [1][2]...，按总预算截断"""
        if not sources:
            return "\n\n【参考资料】\n（未检索到相关内容）"
        lines = ["\n\n【参考资料】"]
        budget = _TOTAL_BUDGET_CHARS
        for i, s in enumerate(sources, start=1):
            text = s["text"].replace("\n", " ")[:_CHUNK_MAX_CHARS]
            lines.append(f"[{i}]（来源：{s['title']}）{text}")
            budget -= len(text)
            if budget <= 0:
                break
        return "\n".join(lines)

    @staticmethod
    def _trim_history(history: list[dict]) -> list[dict]:
        """只保留最近 N 轮对话，防止历史无限增长撑爆上下文"""
        return history[-_HISTORY_MAX_TURNS * 2 :]
