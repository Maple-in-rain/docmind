"""独立 Agent SSE 入口；每次请求创建新的工具与任务状态。"""

import json
import logging

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from ..schemas import AgentRequest

router = APIRouter(prefix="/api/agent", tags=["方案分析"])
logger = logging.getLogger(__name__)


@router.post("")
async def analyze(request: Request, body: AgentRequest):
    service = request.app.state.services["agent_factory"]()

    async def events():
        try:
            async for event in service.stream(body.task):
                if await request.is_disconnected():
                    return
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception:
            logger.exception("Agent stream failed")
            yield 'data: {"type":"error","message":"分析中断，请重试"}\n\n'
        yield "data: [DONE]\n\n"

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})
