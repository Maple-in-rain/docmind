"""固定窗口分块器单测：边界场景与重叠行为。"""

from app.chunking.fixed_chunker import FixedChunker, estimate_tokens


def test_estimate_tokens():
    assert estimate_tokens("") == 0
    assert estimate_tokens("中文") == 2          # 中文逐字计 1
    assert estimate_tokens("hello world") == 2   # 英文按单词计 1
    assert estimate_tokens("你好world。") == 4   # 汉字 + 单词 + 标点


def test_empty_text():
    assert FixedChunker().split("") == []
    assert FixedChunker().split("   \n\n  ") == []


def test_short_text_single_chunk():
    chunks = FixedChunker(chunk_size=100, overlap=10).split("只有一小段内容。")
    assert len(chunks) == 1
    assert chunks[0].text == "只有一小段内容。"


def test_invalid_params():
    import pytest

    with pytest.raises(ValueError):
        FixedChunker(chunk_size=100, overlap=100)  # overlap 必须小于 chunk_size


def test_chunk_bounds_and_overlap():
    """每段 23 token、窗口 50、重叠 10 → 每块 2 段，相邻块共享 1 段"""
    paras = [f"段落{i}" + "字" * 20 for i in range(10)]
    text = "\n\n".join(paras)
    chunks = FixedChunker(chunk_size=50, overlap=10).split(text)

    assert len(chunks) > 1
    for c in chunks:
        assert 0 < estimate_tokens(c.text) <= 50
    # 相邻块重叠：上一块的最后一段 == 下一块的第一段
    assert chunks[0].text.split("\n")[-1] == chunks[1].text.split("\n")[0]
    # 无内容丢失：每个段落至少出现在某一块中
    all_text = "\n".join(c.text for c in chunks)
    for p in paras:
        assert p in all_text


def test_long_paragraph_hard_split():
    """单段超长时按句子硬切，块大小有上界"""
    text = "这是超长内容。" * 500  # 每句 7 token，共 3500 token
    chunks = FixedChunker(chunk_size=100, overlap=0).split(text)
    assert len(chunks) > 1
    for c in chunks:
        assert 0 < estimate_tokens(c.text) <= 100
    # 切分后内容可还原（overlap=0 时无重复）
    assert "".join(c.text for c in chunks) == text
