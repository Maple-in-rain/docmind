"""固定窗口分块器：按 token 估算值切分，块间重叠 overlap。

设计要点：
1. 优先在段落边界断开（避免一句话被拦腰截断）；
2. 重叠窗口防止相邻块边界处的语义断裂；
3. 单段超长时按句子边界硬切（保证块大小有上界）。
"""

import re

from .base import BaseChunker, Chunk

_CJK = re.compile(r"[一-鿿]")
_EN_WORD = re.compile(r"[A-Za-z0-9_]+")


def estimate_tokens(text: str) -> int:
    """粗略估算 token 数：中文 1 字 ≈ 1 token，英文 1 单词 ≈ 1 token，标点 ≈ 1。

    作为分块长度的近似单位足够支撑策略对比实验（评估脚本对全部策略
    使用同一估算口径，不影响公平性）。
    """
    zh = len(_CJK.findall(text))
    en = len(_EN_WORD.findall(text))
    punct = len(re.findall(r"[^一-鿿A-Za-z0-9_\s]", text))
    return zh + en + punct


class FixedChunker(BaseChunker):
    name = "fixed"

    def __init__(self, chunk_size: int = 512, overlap: int = 50):
        if not 0 <= overlap < chunk_size:
            raise ValueError(f"overlap({overlap}) 必须满足 0 <= overlap < chunk_size({chunk_size})")
        self.chunk_size = chunk_size
        self.overlap = overlap

    def split(self, text: str) -> list[Chunk]:
        text = text.strip()
        if not text:
            return []

        paragraphs = [p.strip() for p in re.split(r"\n+", text) if p.strip()]
        chunks: list[Chunk] = []
        buf: list[str] = []
        buf_tokens = 0

        for para in paragraphs:
            para_tokens = estimate_tokens(para)
            # 单段超长：硬切（罕见的长段落，保证块大小有上界）
            if para_tokens > self.chunk_size:
                if buf:
                    chunks.append(self._make(buf))
                    buf, buf_tokens = [], 0
                chunks.extend(self._make([piece]) for piece in self._hard_split(para))
                continue

            if buf_tokens + para_tokens > self.chunk_size:
                chunks.append(self._make(buf))
                # 重叠：保留末尾约 overlap 的内容作为下一块的开头
                buf = self._tail(buf, self.overlap)
                buf_tokens = estimate_tokens("\n".join(buf))
            buf.append(para)
            buf_tokens += para_tokens

        if buf:
            chunks.append(self._make(buf))
        return chunks

    @staticmethod
    def _make(paragraphs: list[str]) -> Chunk:
        return Chunk(text="\n".join(paragraphs))

    @staticmethod
    def _tail(paragraphs: list[str], keep_tokens: int) -> list[str]:
        """从段落列表末尾截取约 keep_tokens 的内容（用于块间重叠）"""
        if keep_tokens <= 0:
            return []
        kept: list[str] = []
        tokens = 0
        for para in reversed(paragraphs):
            t = estimate_tokens(para)
            if kept and tokens + t > keep_tokens:
                break
            kept.append(para)
            tokens += t
        return kept[::-1]

    def _hard_split(self, text: str) -> list[str]:
        """超长段落硬切：按句子边界尽量均匀切开"""
        sentences = re.split(r"(?<=[。！？.!?])", text)
        pieces: list[str] = []
        buf = ""
        n = 0
        for s in sentences:
            t = estimate_tokens(s)
            if buf and n + t > self.chunk_size:
                pieces.append(buf)
                buf, n = s, t
            else:
                buf += s
                n += t
        if buf:
            pieces.append(buf)
        return pieces
