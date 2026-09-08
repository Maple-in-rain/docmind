"""服务层：依赖组装工厂。

所有服务通过构造函数注入依赖（依赖抽象接口，不依赖具体实现），
测试时可以用 mock 实现替换任意组件。
"""

from ..chunking.fixed_chunker import FixedChunker
from ..config import settings
from ..embeddings.mock_embedder import MockEmbedder
from ..embeddings.siliconflow_provider import SiliconFlowEmbeddingProvider
from ..llm.deepseek_provider import DeepSeekProvider
from ..llm.mock_provider import MockProvider
from ..reranking.mock_reranker import MockReranker
from ..reranking.siliconflow_reranker import SiliconFlowRerankerProvider
from ..retrieval.bm25_index import BM25Index
from ..retrieval.vector_store import ChromaVectorStore
from ..storage.db import Database
from ..storage.file_store import FileStore
from .chat_service import ChatService
from .ingestion_service import IngestionService
from .search_service import SearchService


def _select_embedder():
    if settings.embedding_provider == "siliconflow":
        return SiliconFlowEmbeddingProvider()
    if settings.embedding_provider == "mock":
        return MockEmbedder()
    raise ValueError(f"未知 embedding_provider: {settings.embedding_provider}（可选: siliconflow | mock）")


def _select_reranker():
    if settings.rerank_provider == "siliconflow":
        return SiliconFlowRerankerProvider()
    if settings.rerank_provider == "mock":
        return MockReranker()
    raise ValueError(f"未知 rerank_provider: {settings.rerank_provider}（可选: siliconflow | mock）")


def _select_llm():
    if settings.llm_provider == "deepseek":
        return DeepSeekProvider()
    if settings.llm_provider == "mock":
        return MockProvider()
    raise ValueError(f"未知 llm_provider: {settings.llm_provider}（可选: deepseek | mock）")


def build_services() -> dict:
    settings.data_dir.mkdir(parents=True, exist_ok=True)

    embedder = _select_embedder()
    vector_store = ChromaVectorStore(dim=embedder.dim)  # 维度以 provider 为准，单一事实来源
    db = Database()
    file_store = FileStore()
    chunker = FixedChunker(settings.chunk_size, settings.chunk_overlap)
    bm25_index = BM25Index(db)  # 构造即从 SQLite 全量重建（启动时恢复关键词索引）
    reranker = _select_reranker()
    llm = _select_llm()

    search_service = SearchService(embedder, vector_store, db, bm25_index, reranker)
    return {
        "embedder": embedder,
        "vector_store": vector_store,
        "db": db,
        "file_store": file_store,
        "chunker": chunker,
        "bm25_index": bm25_index,
        "reranker": reranker,
        "llm": llm,
        "ingestion": IngestionService(file_store, chunker, embedder, vector_store, db, bm25_index),
        "search": search_service,
        "chat": ChatService(search_service, llm),  # 问答复用检索服务：hybrid + 重排
    }
