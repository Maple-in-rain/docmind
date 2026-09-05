"""服务层：依赖组装工厂。

所有服务通过构造函数注入依赖（依赖抽象接口，不依赖具体实现），
测试时可以用 mock 实现替换任意组件。
"""

from ..chunking.fixed_chunker import FixedChunker
from ..config import settings
from ..embeddings.siliconflow_provider import SiliconFlowEmbeddingProvider
from ..llm.deepseek_provider import DeepSeekProvider
from ..retrieval.bm25_index import BM25Index
from ..retrieval.vector_store import ChromaVectorStore
from ..storage.db import Database
from ..storage.file_store import FileStore
from .chat_service import ChatService
from .ingestion_service import IngestionService
from .search_service import SearchService


def build_services() -> dict:
    settings.data_dir.mkdir(parents=True, exist_ok=True)

    embedder = SiliconFlowEmbeddingProvider()
    vector_store = ChromaVectorStore(dim=embedder.dim)  # 维度以 provider 为准，单一事实来源
    db = Database()
    file_store = FileStore()
    chunker = FixedChunker(settings.chunk_size, settings.chunk_overlap)
    bm25_index = BM25Index(db)  # 构造即从 SQLite 全量重建（启动时恢复关键词索引）
    llm = DeepSeekProvider()

    return {
        "embedder": embedder,
        "vector_store": vector_store,
        "db": db,
        "file_store": file_store,
        "chunker": chunker,
        "bm25_index": bm25_index,
        "llm": llm,
        "ingestion": IngestionService(file_store, chunker, embedder, vector_store, db, bm25_index),
        "search": SearchService(embedder, vector_store, db, bm25_index),
        "chat": ChatService(embedder, vector_store, llm),
    }
