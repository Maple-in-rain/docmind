"""服务层：依赖组装工厂。

所有服务通过构造函数注入依赖（依赖抽象接口，不依赖具体实现），
测试时可以用 mock 实现替换任意组件。
"""

from ..chunking.fixed_chunker import FixedChunker
from ..config import settings
from ..embeddings.siliconflow_provider import SiliconFlowEmbeddingProvider
from ..retrieval.vector_store import ChromaVectorStore
from ..storage.db import Database
from ..storage.file_store import FileStore
from .ingestion_service import IngestionService
from .search_service import SearchService


def build_services() -> dict:
    settings.data_dir.mkdir(parents=True, exist_ok=True)

    embedder = SiliconFlowEmbeddingProvider()
    vector_store = ChromaVectorStore(dim=embedder.dim)  # 维度以 provider 为准，单一事实来源
    db = Database()
    file_store = FileStore()
    chunker = FixedChunker(settings.chunk_size, settings.chunk_overlap)

    return {
        "embedder": embedder,
        "vector_store": vector_store,
        "db": db,
        "file_store": file_store,
        "chunker": chunker,
        "ingestion": IngestionService(file_store, chunker, embedder, vector_store, db),
        "search": SearchService(embedder, vector_store, db),
    }
