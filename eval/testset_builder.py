"""测试集构造：用 DeepSeek 从语料反向生成 QA 对（离线开发时先跳过本脚本）。

设计（面试可讲）：
- 按「段落」而不是整篇文档生成：每条 QA 记录答案出处段落（source_passage），
  评估时做段落级相关性判定——文档级召回在 15 篇小语料上必然饱和
  （top-10 几乎总能碰到唯一的相关文档，全 1.0 的指标没有区分度，
  这是本项目第一轮网格实验实际踩到的坑）；
- 让 LLM 读段落生成"答案明确存在于该段落"的问题，比人手写快一个数量级；
- 生成后人工抽查修正约 20%（抽查记录写在 eval/data/testset.review.md）；
- 每条记录带 doc 文件名与出处段落，评估不受分块参数影响
  （分块边界随 chunk_size 变化，段落级标注才是跨配置的公平基准）。

用法（需要 .env 中已配置 DEEPSEEK_API_KEY，按量计费，约 ¥0.3）：
    python -X utf8 -m eval.testset_builder --per-passage 1

输出：eval/data/testset.jsonl，每行：
    {"id": 1, "question": "...", "answer": "...", "doc": "python-生成器与迭代器.md", "source_passage": "..."}
"""

import argparse
import json
import re
import sys
from pathlib import Path

from app.chunking.fixed_chunker import FixedChunker
from app.llm.deepseek_provider import DeepSeekProvider

from .evaluate import TESTSET_PATH, load_corpus

_PASSAGE_SIZE = 384  # 段落粒度：约 384 token 的原文切片，问答的"答案出处"

_PROMPT = (
    "你是检索测试集构造助手。请阅读下面这段从技术文档中截取的片段，生成 {n} 个中文问题，"
    "要求：\n"
    "1. 每个问题的答案都明确存在于这段片段中（读者能直接引用片段原文作答）；\n"
    "2. 问题口语化，像真实用户会问的样子，不要照抄原文句子；\n"
    "3. 只输出 JSON 数组，不要任何解释，格式：[{{\"question\": \"...\", \"answer\": \"...\"}}]。\n\n"
    "【片段】\n{passage}"
)


def _extract_json_array(text: str) -> list[dict]:
    """从 LLM 输出中提取 JSON 数组（容忍代码围栏与前后赘述）"""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end <= start:
        raise ValueError(f"输出中找不到 JSON 数组: {text[:200]}")
    return json.loads(text[start : end + 1])


async def _ask(provider, prompt: str) -> str:
    """非流式聚合（provider 只有 chat_stream，此处收集完整回答）"""
    parts = []
    async for delta in provider.chat_stream([{"role": "user", "content": prompt}]):
        parts.append(delta)
    return "".join(parts)


def build_testset(
    per_passage: int = 1,
    output_path: Path | None = None,
    provider=None,
    corpus: list[dict] | None = None,
    passage_size: int = _PASSAGE_SIZE,
) -> list[dict]:
    provider = provider or DeepSeekProvider()
    output_path = output_path or TESTSET_PATH
    corpus = corpus or load_corpus()

    import asyncio

    chunker = FixedChunker(passage_size, 0)
    items: list[dict] = []
    skipped_passages = 0
    for doc in corpus:
        passages = [c.text for c in chunker.split(doc["text"])]
        passages = [p for p in passages if len(p.strip()) >= 80]  # 过短片段问答价值低
        print(f"为 {doc['name']} 的 {len(passages)} 个段落生成 QA ...", flush=True)
        for p in passages:
            try:
                answer_text = asyncio.run(
                    _ask(provider, _PROMPT.format(n=per_passage, passage=p))
                )
                qas = _extract_json_array(answer_text)
            except Exception as e:  # 单段失败不中断整批，记入警告
                print(f"  警告：{doc['name']} 某段落生成失败（{e}），跳过", file=sys.stderr)
                skipped_passages += 1
                continue
            for qa in qas:
                if not (qa.get("question") and qa.get("answer")):
                    continue
                items.append(
                    {
                        "id": len(items) + 1,
                        "question": str(qa["question"]).strip(),
                        "answer": str(qa["answer"]).strip(),
                        "doc": doc["name"],
                        "source_passage": p,  # 答案出处段落：段落级相关性判定的金标准
                    }
                )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"\n共生成 {len(items)} 条 QA（跳过 {skipped_passages} 个段落），写入 {output_path}")
    print("下一步：人工抽查约 20%（见 eval/data/testset.review.md），")
    print("修正后运行 python -X utf8 -m eval.evaluate 复现全量评估数字。")
    return items


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="用 DeepSeek 从语料反向生成检索测试集（段落级）")
    parser.add_argument("--per-passage", type=int, default=1, help="每段生成的 QA 条数（默认 1）")
    parser.add_argument("--output", type=Path, default=None, help="输出路径（默认 eval/data/testset.jsonl）")
    args = parser.parse_args(argv)
    build_testset(per_passage=args.per_passage, output_path=args.output)


if __name__ == "__main__":
    main()
