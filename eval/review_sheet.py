"""抽查工作单生成器：把待抽查的测试集条目排版成易读的 Markdown。

直接读 testset.jsonl（每行一段长 JSON）做人工校验太痛苦，
本脚本把指定条目展开为「问题 / 答案 / 出处段落」的易读排版，
人工校验就在工作单上进行，修正仍改 testset.jsonl 本体。

用法（在项目根目录）：
    python -X utf8 -m eval.review_sheet                      # 默认每 5 条抽 1 条
    python -X utf8 -m eval.review_sheet --ids 5,15,25        # 指定条目

输出：eval/data/testset.review-sheet.md
"""

import argparse
import json
from pathlib import Path

from .evaluate import TESTSET_PATH

OUTPUT_PATH = TESTSET_PATH.parent / "testset.review-sheet.md"

_TEMPLATE = """# 测试集抽查工作单（生成文件，勿手改——修正请改 testset.jsonl）

> 生成时间：本次运行。抽查条目：{ids}。
> 每条检查三件事：① 问题自然吗（像真实用户会问的话）？② 答案在【出处段落】中找得到吗？
> ③ 归属文档正确吗？有问题的条目：编辑 `testset.jsonl` 对应行修正或删除。

{entries}
"""

_ITEM = """---

### [ ] 条目 {id}（`{doc}`）

**问题**：{question}

**AI 生成的答案**：{answer}

**出处段落**（检查答案是否确实出自此段）：

> {passage}
"""


def _quote(passage: str) -> str:
    return passage.replace("\n", "\n> ")


def build_sheet(ids: list[int], testset_path: Path = TESTSET_PATH) -> str:
    items = {}
    for line in testset_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        item = json.loads(line)
        items[item["id"]] = item

    entries = []
    for i in ids:
        item = items.get(i)
        if item is None:
            entries.append(f"### [ ] 条目 {i}（不存在，请核对 id）")
            continue
        entries.append(
            _ITEM.format(
                id=item["id"],
                doc=item["doc"],
                question=item["question"],
                answer=item["answer"],
                passage=_quote(item["source_passage"]),
            )
        )
    return _TEMPLATE.format(ids=", ".join(map(str, ids)), entries="\n".join(entries))


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="生成测试集抽查工作单")
    parser.add_argument("--ids", default="", help="逗号分隔的条目 id（默认每 5 条抽 1 条）")
    parser.add_argument("--step", type=int, default=5, help="等距抽样步长（默认 5）")
    args = parser.parse_args(argv)

    if args.ids:
        ids = [int(x) for x in args.ids.split(",") if x.strip()]
    else:
        total = sum(1 for line in TESTSET_PATH.read_text(encoding="utf-8").splitlines() if line.strip())
        ids = list(range(args.step, total + 1, args.step))

    OUTPUT_PATH.write_text(build_sheet(ids), encoding="utf-8")
    print(f"工作单已生成：{OUTPUT_PATH}（共 {len(ids)} 条）")


if __name__ == "__main__":
    main()
