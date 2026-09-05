"""入库流水线集成测试：用假 embedding 离线跑通完整链路。

真实 embedding 走网络 API，测试中用 tests/helpers.py 的确定性假实现替代——
这正是 EmbeddingProvider 抽象的价值：测试不依赖外部服务。
"""

from app.chunking.fixed_chunker import FixedChunker
from app.retrieval.bm25_index import BM25Index
from app.retrieval.vector_store import ChromaVectorStore
from app.services.ingestion_service import IngestionService
from app.services.search_service import SearchService
from app.storage.db import Database
from app.storage.file_store import FileStore
from tests.helpers import FakeEmbedder


def _build_services(tmp_path):
    db = Database(tmp_path / "test.db")
    store = FileStore(tmp_path / "uploads")
    embedder = FakeEmbedder()
    vector_store = ChromaVectorStore(tmp_path / "chroma", dim=embedder.dim)
    chunker = FixedChunker(chunk_size=100, overlap=20)
    bm25_index = BM25Index(db)
    ingestion = IngestionService(store, chunker, embedder, vector_store, db, bm25_index)
    search = SearchService(embedder, vector_store, db, bm25_index)
    return ingestion, search, db, vector_store, bm25_index


def test_ingest_search_delete_roundtrip(tmp_path):
    ingestion, search, db, vector_store, bm25_index = _build_services(tmp_path)

    content = "# 快速排序\n\n快速排序是一种分治算法。\n\n它平均时间复杂度为 O(n log n)。".encode("utf-8")
    result = ingestion.ingest(content, "算法笔记.md", title="算法笔记")
    assert result["chunk_count"] >= 1
    assert result["title"] == "算法笔记"

    # 元数据已入库
    assert db.doc_count() == 1
    assert vector_store.count() == result["chunk_count"]

    # 检索能召回内容（假 embedding 无语义，仅验证链路通畅）
    results = search.search("快速排序的时间复杂度", "vector", top_k=3)
    assert results, "检索无结果"
    assert all(r["doc_id"] == result["doc_id"] for r in results)

    # BM25 双路同步：入库后关键词检索可命中
    bm25_hits = bm25_index.search("快速排序", top_k=3)
    assert bm25_hits, "BM25 索引未同步新入库文档"

    # 删除后向量、元数据、BM25 索引同步清理
    ingestion.delete(result["doc_id"])
    assert db.doc_count() == 0
    assert vector_store.count() == 0
    assert bm25_index.search("快速排序", top_k=3) == []


def test_ingest_unsupported_format_cleans_up(tmp_path):
    ingestion, _, db, _, _ = _build_services(tmp_path)
    with __import__("pytest").raises(ValueError):
        ingestion.ingest(b"x", "evil.xyz")
    assert db.doc_count() == 0  # 失败不留脏数据


def test_ingest_empty_scan_pdf_cleans_up(tmp_path):
    """解析结果为空（模拟扫描版 PDF）时拒绝入库并清理文件"""
    import pymupdf

    pdf = pymupdf.open()
    pdf.new_page()  # 空页面，无文本层
    pdf_bytes = pdf.tobytes()
    pdf.close()

    ingestion, _, db, _, _ = _build_services(tmp_path)
    with __import__("pytest").raises(ValueError, match="解析结果为空"):
        ingestion.ingest(pdf_bytes, "scan.pdf")
    assert db.doc_count() == 0
