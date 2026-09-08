"""压测查询池：从评估测试集抽取问题（不 import locust，可被 pytest 直接测）。"""

import json
from pathlib import Path

TESTSET_PATH = Path(__file__).resolve().parent.parent / "eval" / "data" / "testset.jsonl"


def load_queries(path: Path = TESTSET_PATH) -> list[str]:
    """从测试集抽取问题作为查询池（84 条）"""
    with open(path, encoding="utf-8") as f:
        return [json.loads(line)["question"] for line in f if line.strip()]
