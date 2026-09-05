"""API 请求/响应模型（Pydantic v2）。

- 路由层只做参数校验，业务逻辑在 services 层
- 请求体字段带约束（长度/范围），非法输入在进入服务前就被拦截
"""

from typing import Literal

from pydantic import BaseModel, Field


# ---- 文档管理 ----

class DocumentInfo(BaseModel):
    doc_id: int
    title: str
    original_name: str
    chunk_count: int
    created_at: str


class UploadResult(BaseModel):
    doc_id: int
    title: str
    chunk_count: int


# ---- 检索调试 ----

class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    # 第 1 周仅 vector；bm25 / hybrid 第 3 周接入
    strategy: Literal["vector", "bm25", "hybrid"] = "vector"
    top_k: int = Field(default=10, ge=1, le=50)
    rerank: bool = False


class SearchResult(BaseModel):
    text: str
    chunk_id: str
    doc_id: int
    seq: int | None = None
    title: str = ""
    score: float | None = None          # 检索分数：vector=余弦相似度 / bm25=BM25 分 / hybrid=RRF 分
    rank_vector: int | None = None      # 向量路排名（未参与该路的策略为 None）
    rank_bm25: int | None = None        # BM25 路排名（未参与该路的策略为 None）


# ---- 聊天（第 2 周启用）----

class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=20)
    top_k: int = Field(default=5, ge=1, le=20)
    stream: bool = True


class Source(BaseModel):
    text: str
    doc_id: int
    seq: int | None = None
    title: str = ""
    score: float | None = None


class ChatResponse(BaseModel):
    answer: str
    sources: list[Source]
