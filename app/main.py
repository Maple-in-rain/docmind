"""FastAPI 应用入口。

启动方式（在项目根目录、conda 激活 docmind 环境后）：
    uvicorn app.main:app --reload
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

from .api import agent, chat, documents, health, search
from .services import build_services

app = FastAPI(
    title="DocMind",
    description="基于 RAG 的 AI 知识库问答系统",
    version="0.1.0",
)

# 开发期放开跨域，方便前端单独调试；部署上线前收紧为具体域名
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 组装服务并挂到 app.state（替代全局单例，测试时可整体替换）
app.state.services = build_services()

# 先注册 API 路由，最后挂载前端静态文件——Starlette 按注册顺序匹配路由
app.include_router(health.router)
app.include_router(documents.router)
app.include_router(search.router)
app.include_router(chat.router)
app.include_router(agent.router)

_frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/", StaticFiles(directory=str(_frontend_dir), html=True), name="frontend")

# 两个入口共用同一服务实例；Mount 负责传递 root_path，API 文档也能使用前缀。
_docmind_app = app
app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None)
app.state = _docmind_app.state


@app.get("/docmind", include_in_schema=False)
async def docmind_entry():
    return RedirectResponse("/docmind/", status_code=307)


app.mount("/docmind", _docmind_app, name="docmind")
app.mount("/", _docmind_app, name="root")
