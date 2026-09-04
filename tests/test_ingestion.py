"""入库流水线集成测试：用假 embedding 离线跑通完整链路。

真实 embedding 走网络 API，测试中用 tests/helpers.py 的确定性假实现替代——
这正是 EmbeddingProvider 抽象的价值：测试不依赖外部服务。
"""

from app.chunking.fixed_chunker import FixedChunker
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
    ingestion = IngestionService(store, chunker, embedder, vector_store, db)
    search = SearchService(embedder, vector_store, db)
    return ingestion, search, db, vector_store


def test_ingest_search_delete_roundtrip(tmp_path):
    ingestion, search, db, vector_store = _build_services(tmp_path)

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

    # 删除后向量与元数据同步清理
    ingestion.delete(result["doc_id"])
    assert db.doc_count() == 0
    assert vector_store.count() == 0


def test_ingest_unsupported_format_cleans_up(tmp_path):
    ingestion, _, db, _ = _build_services(tmp_path)
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

    ingestion, _, db, _ = _build_services(tmp_path)
    with __import__("pytest").raises(ValueError, match="解析结果为空"):
        ingestion.ingest(pdf_bytes, "scan.pdf")
    assert db.doc_count() == 0
