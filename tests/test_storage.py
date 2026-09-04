"""SQLite 存储层单测：文档/分块增删与级联。"""

from app.storage.db import Database


def test_document_crud(tmp_path):
    db = Database(tmp_path / "test.db")
    assert db.doc_count() == 0

    doc_id = db.add_document("标题", "原始名.md", "stored.md", 2)
    db.add_chunks([(f"{doc_id}-0", doc_id, 0, "第一块"), (f"{doc_id}-1", doc_id, 1, "第二块")])

    doc = db.get_document(doc_id)
    assert doc["title"] == "标题"
    assert doc["chunk_count"] == 2
    assert len(db.list_documents()) == 1

    chunks = db.get_chunks(doc_id)
    assert [c["text"] for c in chunks] == ["第一块", "第二块"]

    db.delete_document(doc_id)
    assert db.get_document(doc_id) is None
    assert db.get_chunks(doc_id) == []  # 级联删除分块


def test_file_store_uuid_rename(tmp_path):
    from app.storage.file_store import FileStore

    store = FileStore(tmp_path)
    stored, original = store.save("内容".encode("utf-8"), "中文 名字.txt")
    assert original == "中文 名字.txt"
    assert stored != "中文 名字.txt"          # 落盘名不含原始名
    assert stored.endswith(".txt")
    assert store.path(stored).read_bytes() == "内容".encode("utf-8")

    store.delete(stored)
    assert not store.path(stored).exists()
