"""同题记录普通 RAG 和 Agent，保留人工评分空栏；不自动宣称语义效果。

先上传 scripts/sample_data/comparison 下的三份文档，再启动本脚本。
--dry-run 只检查案例，不调用服务。正式执行会使用服务器配置的模型额度。
"""

import argparse
import json
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def parse_events(lines):
    events = []
    for line in lines:
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload == "[DONE]":
            return events
        events.append(json.loads(payload))
    raise ValueError("服务流缺少结束标记，结果不完整")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--cases", type=Path, default=ROOT / "eval/data/upgrade_cases.json")
    parser.add_argument("--output", type=Path, default=ROOT / "eval/results/upgrade_comparison.jsonl")
    parser.add_argument("--limit", type=int, default=0, help="只执行前N条，0表示全部")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    if args.limit:
        cases = cases[:args.limit]
    if args.dry_run:
        print(json.dumps({"case_count": len(cases), "reviewed": sum(c["reviewed"] for c in cases),
                          "network_calls": 0}, ensure_ascii=False))
        return
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=150) as client, args.output.open("a", encoding="utf-8") as output:
        for case in cases:
            for mode in ("rag", "agent"):
                started = time.monotonic()
                history = case.get("history", [])
                task = case["question"]
                if history:
                    task = "以下是对话上下文：\n" + json.dumps(history, ensure_ascii=False) + "\n当前问题：" + task
                body = {"task": task} if mode == "agent" else {
                    "messages": history + [{"role": "user", "content": case["question"]}], "stream": True}
                record = {"case_id": case["id"], "mode": mode, "case_reviewed": case["reviewed"],
                          "manual_review": {"supported": None, "complete": None, "appropriate_refusal": None, "notes": ""}}
                try:
                    endpoint = "/api/agent" if mode == "agent" else "/api/chat"
                    with client.stream("POST", args.base.rstrip("/") + endpoint, json=body) as response:
                        response.raise_for_status()
                        events = parse_events(response.iter_lines())
                    answer = "".join(e["content"] for e in events if e["type"] == "delta")
                    record.update(answer=answer, events=events, mock_output="[mock" in answer.lower())
                except (httpx.HTTPError, ValueError) as exc:
                    record["error"] = str(exc)
                record["elapsed_ms"] = round((time.monotonic() - started) * 1000)
                output.write(json.dumps(record, ensure_ascii=False) + "\n")
                output.flush()
                print(case["id"], mode, record["elapsed_ms"], "error" if "error" in record else "recorded")


if __name__ == "__main__":
    main()
