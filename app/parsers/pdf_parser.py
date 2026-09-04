"""PDF 解析：PyMuPDF 逐页提取文本。

已知局限：扫描版 PDF 没有文本层，解析结果为空（OCR 列入 Roadmap）。
"""

import pymupdf

from .base import BaseParser, ParsedDoc


class PdfParser(BaseParser):
    def parse(self, file_path) -> ParsedDoc:
        pages = []
        with pymupdf.open(file_path) as doc:
            for page in doc:
                pages.append(page.get_text("text"))
        return ParsedDoc(text="\n\n".join(pages), meta={"format": "pdf"})
