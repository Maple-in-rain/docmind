"""健康检查 + 统计信息"""

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/health", tags=["健康检查"])


@router.get("")
def health(request: Request):
    services = request.app.state.services
    return {
        "status": "ok",
        "doc_count": services["db"].doc_count(),
        "chunk_count": services["vector_store"].count(),
    }
