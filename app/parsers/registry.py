"""解析器注册表：按文件扩展名分发到对应解析器。"""

from pathlib import Path

from .base import BaseParser
from .docx_parser import DocxParser
from .md_parser import MarkdownParser
from .pdf_parser import PdfParser
from .txt_parser import TxtParser

_PARSERS: dict[str, BaseParser] = {
    ".pdf": PdfParser(),
    ".docx": DocxParser(),
    ".md": MarkdownParser(),
    ".markdown": MarkdownParser(),
    ".txt": TxtParser(),
}

SUPPORTED_EXTS = sorted(_PARSERS.keys())


def get_parser(file_path: Path) -> BaseParser:
    ext = file_path.suffix.lower()
    if ext not in _PARSERS:
        raise ValueError(f"不支持的文件格式: {ext}（支持: {', '.join(SUPPORTED_EXTS)}）")
    return _PARSERS[ext]
