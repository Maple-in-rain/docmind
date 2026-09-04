"""检索调试端点：独立暴露检索层，面试演示"混合检索为什么更好"的利器"""

from fastapi import APIRouter, HTTPException, Request

from ..schemas import SearchRequest, SearchResult

router = APIRouter(prefix="/api/search", tags=["检索调试"])


@router.post("", response_model=list[SearchResult])
def search(request: Request, req: SearchRequest):
    try:
        return request.app.state.services["search"].search(
            req.query, req.strategy, req.top_k, req.rerank
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        # 服务未配置（如缺少 API key），属于部署问题而非客户端错误
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"检索失败: {e}")
