"""聊天端点：默认 SSE 流式，stream=false 时返回完整 JSON。

SSE 事件格式（每帧一行 data:，帧间空行分隔）：
    data: {"type": "sources", "sources": [...]}
    data: {"type": "delta", "content": "回答增量"}
    data: {"type": "done"}
    data: [DONE]          ← 流结束标记
出错时：
    data: {"type": "error", "message": "..."}
"""

import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from ..schemas import ChatRequest, ChatResponse

router = APIRouter(prefix="/api/chat", tags=["聊天"])


@router.post("")
async def chat(request: Request, req: ChatRequest):
    service = request.app.state.services["chat"]
    messages = [m.model_dump() for m in req.messages]

    if not req.stream:
        answer, sources = await service.chat(messages, req.top_k)
        return ChatResponse(answer=answer, sources=sources)

    async def event_stream():
        try:
            async for event in service.stream_chat(messages, req.top_k):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            # 流已开始后的错误也走事件帧，前端可以展示部分内容 + 错误提示
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
