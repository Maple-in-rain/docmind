"""分段计时：PERF_LOG=1 时打点输出，定位延迟瓶颈（面试问题"延迟大头在哪"）。

零侵入设计：settings.perf_log 默认 False，调用方只有一次布尔判断，
不调用 perf_counter（Windows 上为 syscall）、不分配对象——压测高频路径无额外开销。
聚合统计（P50/P95/P99）交给 locust，这里只做单请求归因。

logger 必须自挂 handler：root logger 默认 WARNING 级别会把 INFO 行静默吞掉。
"""

import logging
import time

logger = logging.getLogger("docmind.perf")
if not logger.handlers:  # 不干扰 root/uvicorn 配置；无 handler 时 INFO 会被丢弃
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(message)s", datefmt="%H:%M:%S"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


class SegmentTimer:
    __slots__ = ("_enabled", "_t0", "_last", "_segments")

    def __init__(self, enabled: bool):
        self._enabled = enabled
        self._t0 = time.perf_counter() if enabled else 0.0
        self._last = self._t0
        self._segments: dict[str, float] = {}

    def segment(self, name: str) -> None:
        """记录上一个分段点到此刻的耗时；关闭时退化为单布尔判断"""
        if not self._enabled:
            return
        now = time.perf_counter()
        self._segments[name] = (now - self._last) * 1000.0
        self._last = now

    def summary_ms(self) -> str:
        if not self._enabled:
            return ""
        total = (time.perf_counter() - self._t0) * 1000.0
        parts = " ".join(f"{k}={v:.1f}ms" for k, v in self._segments.items())
        return f"{parts} total={total:.1f}ms"
