"""SegmentTimer 单测：关闭零开销、开启时各段耗时与 total 输出。"""

import time

from app.perf import SegmentTimer


def test_disabled_noop():
    timer = SegmentTimer(False)
    for name in ("embed", "vector_query", "bm25", "db_fetch", "rerank"):
        timer.segment(name)
    assert timer.summary_ms() == ""


def test_enabled_summary_contains_all_segments():
    timer = SegmentTimer(True)
    timer.segment("embed")
    timer.segment("bm25")
    summary = timer.summary_ms()
    assert "embed=" in summary
    assert "bm25=" in summary
    assert "total=" in summary


def test_segment_measures_elapsed_time():
    timer = SegmentTimer(True)
    timer.segment("embed")
    time.sleep(0.05)
    timer.segment("bm25")
    summary = timer.summary_ms()
    # 宽松下界防 flaky：>40ms 但远小于 sleep 时长的两倍
    import re

    match = re.search(r"bm25=(\d+\.\d+)ms", summary)
    assert match is not None
    assert float(match.group(1)) > 40.0
