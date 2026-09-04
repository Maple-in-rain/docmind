"""入库流水线：落盘 → 解析 → 分块 → 向量化 → 双路存储。

执行顺序设计：先做无副作用的步骤（解析/分块/向量化，失败不留脏数据），
再写 SQLite 与向量库；任一步失败清理已落盘文件。
"""

from pathlib import Path

from ..chunking.base import BaseChunker
from ..embeddings.base import EmbeddingProvider
from ..parsers.registry import get_parser
from ..retrieval.vector_store import VectorStore
from ..storage.db import Database
from ..storage.file_store import FileStore


class IngestionService:
    def __init__(
        self,
        file_store: FileStore,
        chunker: BaseChunker,
        embedder: EmbeddingProvider,
        vector_store: VectorStore,
        db: Database,
    ):
        self.file_store = file_store
        self.chunker = chunker
        self.embedder = embedder
        self.vector_store = vector_store
        self.db = db

    def ingest(self, content: bytes, filename: str, title: str = "") -> dict:
        stored_name, _ = self.file_store.save(content, filename)
        try:
            file_path = self.file_store.path(stored_name)

            # ---- 无副作用阶段 ----
            parsed = get_parser(file_path).parse(file_path)
            if not parsed.text.strip():
                raise ValueError("文档解析结果为空（可能是扫描版 PDF，暂不支持 OCR）")
            chunks = self.chunker.split(parsed.text)
            if not chunks:
                raise ValueError("文档分块结果为空")
            embeddings = self.embedder.embed([c.text for c in chunks])
            assert len(embeddings) == len(chunks), "embedding 结果数量与分块不一致"

            # ---- 落库阶段（SQLite 元数据 + Chroma 向量，同一 doc_id 关联）----
            doc_title = (title or Path(filename).stem).strip() or "未命名文档"
            doc_id = self.db.add_document(doc_title, filename, stored_name, len(chunks))
            chunk_ids = [f"{doc_id}-{i}" for i in range(len(chunks))]
            self.db.add_chunks(
                [(cid, doc_id, i, c.text) for i, (cid, c) in enumerate(zip(chunk_ids, chunks))]
            )
            self.vector_store.add(
                ids=chunk_ids,
                texts=[c.text for c in chunks],
                embeddings=embeddings,
                metadatas=[{"doc_id": doc_id, "seq": i, "title": doc_title} for i in range(len(chunks))],
            )
            return {"doc_id": doc_id, "title": doc_title, "chunk_count": len(chunks)}
        except Exception:
            self.file_store.delete(stored_name)  # 失败清理落盘文件
            raise

    def delete(self, doc_id: int) -> None:
        doc = self.db.get_document(doc_id)
        if doc is None:
            raise KeyError(f"文档不存在: {doc_id}")
        self.vector_store.delete_by_doc(doc_id)  # 先删向量，再删元数据（级联删分块）
        self.db.delete_document(doc_id)
        self.file_store.delete(doc["stored_name"])
