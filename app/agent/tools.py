"""工具边界：校验模型参数，限制正文大小，统一证据编号。"""

import logging
import threading

from pydantic import BaseModel, ConfigDict, Field, model_validator

logger = logging.getLogger(__name__)


class Arguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ListArguments(Arguments):
    offset: int = Field(default=0, ge=0, le=100000)


class SearchArguments(Arguments):
    query: str = Field(min_length=1, max_length=2000)


class ReadArguments(Arguments):
    doc_id: int = Field(ge=1)
    seq: int = Field(ge=0)
    radius: int = Field(default=1, ge=0, le=1)


class TaskArguments(Arguments):
    steps: list[str] = Field(min_length=1, max_length=6, description="本次任务的步骤列表，最多6条，数组下标从0开始。")
    completed: list[int] = Field(default_factory=list, max_length=6,
        description="已完成步骤的整数下标，从0开始。例如steps有3条时，[0,2]表示第1和第3条已完成。不要填写步骤文本。")
    gaps: list[str] = Field(default_factory=list, max_length=6)

    @model_validator(mode="after")
    def check_items(self):
        if any(not s.strip() or len(s) > 160 for s in self.steps + self.gaps):
            raise ValueError("任务条目必须为 1 至 160 字符")
        if (len(set(self.steps)) != len(self.steps) or len(set(self.completed)) != len(self.completed)
                or any(i < 0 or i >= len(self.steps) for i in self.completed)):
            raise ValueError("已完成条目必须来自不重复的任务清单")
        return self


_TOOLS = {
    "list_documents": (ListArguments, "列出文档编号和标题，每页20条，可用offset翻页。"),
    "search_documents": (SearchArguments, "在知识库混合检索并重排，返回最多5条带证据编号的片段。可换关键词补充搜索。"),
    "read_context": (ReadArguments, "读取指定文档片段及相邻片段；seq从0开始，radius最大1。补充证据的条件与上下文。"),
    "update_task": (TaskArguments, "维护当前请求的比较维度steps、已完成条目completed和证据缺口gaps；先制定计划，查到证据后更新。"),
}


class AgentTools:
    def __init__(self, search, db):
        self.search, self.db = search, db
        self.sources: list[dict] = []
        self.state = {"steps": [], "completed": [], "gaps": []}
        self._source_ids: dict[str, dict] = {}
        self._remaining_chars = 12000
        self._cancelled = threading.Event()
        self._lock = threading.Lock()

    def cancel(self):
        with self._lock:
            self._cancelled.set()

    @property
    def schemas(self):
        return [{"type": "function", "function": {"name": name, "description": description,
                "parameters": model.model_json_schema()}}
                for name, (model, description) in _TOOLS.items()]

    def execute(self, name: str, arguments: dict) -> dict:
        if self._cancelled.is_set():
            return {"error": "任务已停止"}
        if name not in _TOOLS:
            return {"error": "未知工具，只能调用已登记的文档工具"}
        try:
            args = _TOOLS[name][0].model_validate(arguments)
        except ValueError:
            return {"error": "工具参数不合法，请按工具定义修正参数"}
        try:
            if name == "update_task":
                with self._lock:
                    if self._cancelled.is_set():
                        return {"error": "任务已停止"}
                    self.state = {"steps": args.steps, "completed": [args.steps[i] for i in args.completed], "gaps": args.gaps}
                    return {"state": self.state}
            if name == "list_documents":
                documents = self.db.list_documents()
                page = documents[args.offset:args.offset + 20]
                return {"documents": [{"doc_id": d["doc_id"], "title": d["title"][:200],
                    "chunk_count": d["chunk_count"]} for d in page],
                    "next_offset": args.offset + 20 if len(documents) > args.offset + 20 else None}
            if name == "search_documents":
                if not args.query.strip():
                    return {"error": "检索问题不能为空"}
                hits = self.search.search(args.query, "hybrid", 5, True, cancel_event=self._cancelled)
                return {"sources": self._evidence(hits[:5])}
            document = self.db.get_document(args.doc_id)
            if document is None:
                return {"error": "文档不存在"}
            chunks = self.db.get_chunks(args.doc_id)
            if not any(c["seq"] == args.seq for c in chunks):
                return {"error": "片段不存在"}
            selected = [{**c, "title": document["title"]} for c in chunks
                        if abs(c["seq"] - args.seq) <= args.radius]
            return {"sources": self._evidence(selected)}
        except Exception:
            logger.exception("Agent tool failed: %s", name)
            return {"error": "工具执行失败，可尝试其他查找方式或说明证据不足"}

    def _evidence(self, chunks):
        with self._lock:
            if self._cancelled.is_set():
                return []
            return self._store_evidence(chunks)

    def _store_evidence(self, chunks):
        result = []
        for chunk in chunks:
            cid = chunk["chunk_id"]
            if cid in self._source_ids:
                result.append(self._source_ids[cid])
                continue
            text = chunk["text"][:min(1200, self._remaining_chars)]
            if not text.strip():
                continue
            source = {"citation": len(self.sources) + 1, "chunk_id": cid,
                      "doc_id": chunk["doc_id"], "seq": chunk["seq"],
                      "title": chunk.get("title", "")[:200], "text": text}
            self._remaining_chars -= len(text)
            self.sources.append(source)
            self._source_ids[cid] = source
            result.append(source)
        return result
