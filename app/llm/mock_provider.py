"""Mock LLM：测试 / 压测专用，不产生 API 费用。

- 单测：chat_service 全链路离线测试
- 压测：locust 打 /api/chat 时测系统自身吞吐（排除 LLM 网络延迟）
"""

import asyncio
import json
from collections.abc import AsyncIterator

from .base import LLMProvider


class MockProvider(LLMProvider):
    name = "mock"

    def __init__(self, chunk_size: int = 5, delay: float = 0.01):
        self.chunk_size = chunk_size
        self.delay = delay

    async def complete(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        """确定性演示流程，无语义能力；不能用于证明 Agent 效果。"""
        if not tools:
            try:
                data = json.loads(messages[-1]["content"])
                return {"role": "assistant", "content": json.dumps({"query": data["question"]}, ensure_ascii=False)}
            except (ValueError, KeyError, TypeError):
                return {"role": "assistant", "content": "[mock] 请使用真实模型验证分析效果。"}
        results = [json.loads(m["content"]) for m in messages if m.get("role") == "tool"]
        count = len(results)
        steps = ["比较一致性与适用条件", "查找恢复机制"]
        if count == 0:
            name, args = "update_task", {"steps": steps, "completed": [], "gaps": []}
        elif count == 1:
            name, args = "list_documents", {}
        elif count == 2:
            name, args = "search_documents", {"query": messages[1]["content"][:2000]}
        elif count == 3 and results[-1].get("sources"):
            source = results[-1]["sources"][0]
            name, args = "read_context", {"doc_id": source["doc_id"], "seq": source["seq"], "radius": 1}
        elif count == 4:
            name, args = "update_task", {"steps": steps, "completed": [], "gaps": ["mock 不评判真实结论，请切换真实模型验证"]}
        else:
            sources = [s for result in results for s in result.get("sources", [])]
            refs = " ".join(f'[{s["citation"]}]' for s in sources[:3])
            return {"role": "assistant", "content": f"# [mock 演示报告]\n\n已演示工具调用与上下文读取。资料编号：{refs}\n\n## 待确认\nmock 没有语义分析能力，不能据此比较方案优劣。请切换真实模型核对原文。"}
        return {"role": "assistant", "content": None, "tool_calls": [{"id": f"mock-{count}", "type": "function",
            "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)}}]}

    async def chat_stream(self, messages: list[dict]) -> AsyncIterator[str]:
        question = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        answer = f"[mock 回答] 你问的是：{question[:50]}"
        for i in range(0, len(answer), self.chunk_size):
            yield answer[i : i + self.chunk_size]
            await asyncio.sleep(self.delay)
