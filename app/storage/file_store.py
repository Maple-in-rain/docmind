"""上传文件落盘。

一律用 uuid 重命名：原始文件名可能包含中文、空格甚至路径分隔符，
直接使用会造成路径注入或编码问题。原始名存 SQLite 仅用于展示。
"""

import uuid
from pathlib import Path

from ..config import settings


class FileStore:
    def __init__(self, root: Path | None = None):
        self.root = root or settings.data_dir / "uploads"
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, content: bytes, original_name: str) -> tuple[str, str]:
        """保存文件，返回 (存储名, 原始名)"""
        ext = Path(original_name).suffix.lower()
        stored_name = f"{uuid.uuid4().hex}{ext}"
        (self.root / stored_name).write_bytes(content)
        return stored_name, original_name

    def path(self, stored_name: str) -> Path:
        return self.root / stored_name

    def delete(self, stored_name: str) -> None:
        (self.root / stored_name).unlink(missing_ok=True)
