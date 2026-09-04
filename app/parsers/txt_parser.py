"""纯文本解析：UTF-8 快路径 + charset-normalizer 编码探测。

中文 Windows 环境下 txt 常见 GBK 编码，直接按 UTF-8 读会乱码或报错。
cp_isolation 把探测范围限制在中英文常见编码内，避免短文本被误判为
cp949（韩文）等其他编码——这是实测踩过的坑。
"""

from charset_normalizer import from_bytes

from .base import BaseParser, ParsedDoc

# 候选编码集：覆盖中英文文档的常见编码
_ISOLATION = ["utf_8", "gb18030", "big5", "cp1252"]


class TxtParser(BaseParser):
    def parse(self, file_path) -> ParsedDoc:
        raw = file_path.read_bytes()
        # 快路径：能严格按 UTF-8 解码就直接用（大多数现代文档）
        try:
            return ParsedDoc(text=raw.decode("utf-8"), meta={"format": "txt", "encoding": "utf-8"})
        except UnicodeDecodeError:
            pass

        best = from_bytes(raw, cp_isolation=_ISOLATION).best()
        if best is None:
            raise ValueError(f"无法识别文件编码: {file_path.name}")
        return ParsedDoc(text=str(best), meta={"format": "txt", "encoding": best.encoding})
