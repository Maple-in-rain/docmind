"""文档管理：上传（入库）、列表、删除"""

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from ..config import settings
from ..schemas import DocumentInfo, UploadResult

router = APIRouter(prefix="/api/documents", tags=["文档管理"])


@router.post("/upload", response_model=UploadResult)
def upload_document(request: Request, file: UploadFile = File(...), title: str = Form("")):
    """上传文档并同步完成入库。

    同步处理的取舍：MVP 阶段文档规模小、链路简单；大文件异步入库列入 Roadmap。
    """
    content = file.file.read()
    if not content:
        raise HTTPException(status_code=400, detail="空文件")
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"文件超过 {settings.max_upload_mb}MB 限制")

    try:
        return request.app.state.services["ingestion"].ingest(content, file.filename, title)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        # 服务未配置（如缺少 API key）
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"入库失败: {e}")


@router.get("", response_model=list[DocumentInfo])
def list_documents(request: Request):
    return request.app.state.services["db"].list_documents()


@router.delete("/{doc_id}")
def delete_document(request: Request, doc_id: int):
    try:
        request.app.state.services["ingestion"].delete(doc_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"deleted": True}
