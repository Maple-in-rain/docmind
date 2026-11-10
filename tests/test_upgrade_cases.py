import json
from pathlib import Path

import pytest

from scripts.compare_modes import parse_events


def test_sse_parser_requires_terminal_and_preserves_events():
    assert parse_events(['data: {"type":"delta","content":"回答"}', '', 'data: [DONE]'])[0]["content"] == "回答"
    with pytest.raises(ValueError, match="结束"):
        parse_events(['data: {"type":"delta","content":"partial"}'])


def test_all_gold_passages_exist_and_review_is_not_fabricated():
    root = Path(__file__).resolve().parents[1]
    cases = json.loads((root / "eval/data/upgrade_cases.json").read_text(encoding="utf-8"))
    assert len(cases) >= 20
    assert len({c["id"] for c in cases}) == len(cases)
    for case in cases:
        assert case["reviewed"] is False
        assert case["question"].strip()
        for gold in case["gold_evidence"]:
            assert gold["passage"] in (root / "scripts/sample_data/comparison" / gold["file"]).read_text(encoding="utf-8")
