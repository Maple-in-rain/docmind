"""测试集构造：用 DeepSeek 从语料反向生成 QA 对（离线开发时先跳过本脚本）。

设计（面试可讲）：
- 让 LLM 读语料生成"答案明确存在于原文"的问题，比人手写快一个数量级；
- 生成后人工抽查修正约 20%（抽查记录写在 eval/data/testset.review.md），
  这是"AI 生成 + 人工校验"的标准数据工程流程；
- 每条记录带 source 文档文件名——评估时按文档判定相关性，
  不受分块参数影响（分块边界随 chunk_size 变化，文档级标注才是公平基准）。

用法（需要 .env 中已配置 DEEPSEEK_API_KEY，按量计费，约 ¥0.2）：
    python -X utf8 -m eval.testset_builder --per-doc 6

输出：eval/data/testset.jsonl，每行：
    {"id": 1, "question": "...", "answer": "...", "doc": "python-生成器与迭代器.md"}
"""

import argparse
import json
import re
import sys
from pathlib import Path

from app.llm.deepseek_provider import DeepSeekProvider

from .evaluate import TESTSET_PATH, load_corpus

_PROMPT = (
    "你是检索测试集构造助手。请阅读下面的技术文档，生成 {n} 个中文问题，"
    "要求：\n"
    "1. 每个问题的答案都明确存在于原文中（读者能直接引用原文作答）；\n"
    "2. 问题覆盖文档的不同部分，口语化，像真实用户会问的样子；\n"
    "3. 只输出 JSON 数组，不要任何解释，格式：[{{\"question\": \"...\", \"answer\": \"...\"}}]。\n\n"
    "【文档】\n{doc_text}"
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
    per_doc: int = 6,
    output_path: Path | None = None,
    provider=None,
    corpus: list[dict] | None = None,
) -> list[dict]:
    provider = provider or DeepSeekProvider()
    output_path = output_path or TESTSET_PATH
    corpus = corpus or load_corpus()

    import asyncio

    items: list[dict] = []
    for doc in corpus:
        print(f"为 {doc['name']} 生成 {per_doc} 条 QA ...", flush=True)
        try:
            answer_text = asyncio.run(
                _ask(provider, _PROMPT.format(n=per_doc, doc_text=doc["text"][:6000]))
            )
            qas = _extract_json_array(answer_text)
        except Exception as e:  # 单篇失败不中断整批，记入警告
            print(f"  警告：{doc['name']} 生成失败（{e}），跳过", file=sys.stderr)
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
                }
            )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"\n共生成 {len(items)} 条 QA，写入 {output_path}")
    print("下一步：人工抽查约 20%（见 tests/E2E_CHECKLIST.md 或 eval/data/testset.review.md），")
    print("修正后运行 python -X utf8 eval/evaluate.py 复现全量评估数字。")
    return items


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="用 DeepSeek 从语料反向生成检索测试集")
    parser.add_argument("--per-doc", type=int, default=6, help="每篇文档生成的 QA 条数（默认 6）")
    parser.add_argument("--output", type=Path, default=None, help="输出路径（默认 eval/data/testset.jsonl）")
    args = parser.parse_args(argv)
    build_testset(per_doc=args.per_doc, output_path=args.output)


if __name__ == "__main__":
    main()
