"""Markdown 解析：剥离格式符号，保留标题层级（供结构化分块使用）。

代码块内容原样保留——技术文档中的代码往往是问答的关键依据。
"""

from pathlib import Path

from .base import BaseParser, ParsedDoc


class MarkdownParser(BaseParser):
    def parse(self, file_path: Path) -> ParsedDoc:
        text = file_path.read_text(encoding="utf-8")
        lines: list[str] = []
        headings: list[tuple[int, str]] = []
        in_code = False

        for raw in text.splitlines():
            line = raw.rstrip()
            if line.strip().startswith("```"):
                in_code = not in_code
                continue
            if in_code:
                lines.append(line)
                continue

            stripped = line.strip()
            if stripped.startswith("#"):
                level = len(stripped) - len(stripped.lstrip("#"))
                title = stripped.lstrip("#").strip()
                headings.append((level, title))
                lines.append(title)
            elif stripped.startswith(("- ", "* ", "> ")):
                lines.append(stripped[2:])
            else:
                # 去掉行内格式符号（加粗/行内代码等）
                lines.append(stripped.replace("**", "").replace("`", ""))

        return ParsedDoc(
            text="\n".join(lines),
            headings=headings,
            meta={"format": "markdown"},
        )
