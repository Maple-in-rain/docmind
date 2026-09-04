"""解析器抽象定义。

每种文件格式一个实现类，按扩展名经 registry 分发。
新增格式只需：写一个 BaseParser 子类 + 在 registry 注册一行。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ParsedDoc:
    """文档解析结果。

    - text: 清洗后的纯文本
    - headings: (层级, 标题) 列表，Markdown 解析器填充，供结构化分块使用
    - meta: 解析器附加信息（格式、编码等）
    """

    text: str
    headings: list[tuple[int, str]] = field(default_factory=list)
    meta: dict = field(default_factory=dict)


class BaseParser(ABC):
    """解析器抽象基类"""

    @abstractmethod
    def parse(self, file_path: Path) -> ParsedDoc:
        """解析文件为纯文本，失败抛异常（由上层决定如何反馈给用户）"""
