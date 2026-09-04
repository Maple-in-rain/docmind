"""SQLite 元数据存储：documents 表 + chunks 表。

- 用标准库 sqlite3，零额外依赖，单机场景足够
- 分块正文存在这里：BM25 索引重建（第 3 周）与检索评估都依赖它
- 每次操作独立建连并随上下文自动提交/回滚，线程安全
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from ..config import settings


class Database:
    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or settings.data_dir / "docmind.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            with conn:  # 事务上下文：正常提交，异常回滚
                yield conn
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    doc_id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    title         TEXT NOT NULL,
                    original_name TEXT NOT NULL,
                    stored_name   TEXT NOT NULL,
                    chunk_count   INTEGER NOT NULL DEFAULT 0,
                    created_at    TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
                );
                CREATE TABLE IF NOT EXISTS chunks (
                    chunk_id TEXT PRIMARY KEY,
                    doc_id   INTEGER NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
                    seq      INTEGER NOT NULL,
                    text     TEXT NOT NULL
                );
                """
            )

    # ---- 文档 ----

    def add_document(self, title: str, original_name: str, stored_name: str, chunk_count: int) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO documents (title, original_name, stored_name, chunk_count) VALUES (?, ?, ?, ?)",
                (title, original_name, stored_name, chunk_count),
            )
            return cur.lastrowid

    def get_document(self, doc_id: int) -> dict | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM documents WHERE doc_id = ?", (doc_id,)).fetchone()
            return dict(row) if row else None

    def list_documents(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM documents ORDER BY doc_id DESC").fetchall()
            return [dict(r) for r in rows]

    def delete_document(self, doc_id: int) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM documents WHERE doc_id = ?", (doc_id,))  # 级联删 chunks

    def doc_count(self) -> int:
        with self._conn() as conn:
            return conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]

    # ---- 分块 ----

    def add_chunks(self, chunks: list[tuple[str, int, int, str]]) -> None:
        """chunks: [(chunk_id, doc_id, seq, text)]"""
        with self._conn() as conn:
            conn.executemany(
                "INSERT INTO chunks (chunk_id, doc_id, seq, text) VALUES (?, ?, ?, ?)", chunks
            )

    def get_chunks(self, doc_id: int) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM chunks WHERE doc_id = ? ORDER BY seq", (doc_id,)
            ).fetchall()
            return [dict(r) for r in rows]
