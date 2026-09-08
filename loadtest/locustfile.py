"""Locust 压测脚本（第 4 周，两个场景见 README「性能压测报告」）。

- 场景 1 端到端延迟：真实 provider（默认），低并发（-u 3），观察外部 API 延迟占比；
- 场景 2 系统吞吐：全 mock（LLM_PROVIDER=mock 等），高并发（-u 50），测系统自身极限。

查询池来自 eval/data/testset.jsonl——与检索评估同源，保证查询分布真实。
本文件不 import app.*，与服务器代码零耦合。

注意：import locust 会触发 gevent 全局 monkey-patch（socket/thread），
会毒化同进程内的 asyncio/chromadb——因此查询池逻辑放在 loadtest/queries.py
（不 import locust），pytest 直接测 queries 模块，本文件只在 locust 进程里加载。
"""

import json
import os
import random
import time

from locust import HttpUser, between, task

from loadtest.queries import load_queries  # 绝对导入：locust 按文件名导入本模块，不能用相对导入

QUERIES = load_queries()

# 思考时间：场景 1 用默认 1~3s（模拟真实用户节奏）；场景 2 设 0/0.1 消除思考时间
_WAIT_MIN = float(os.environ.get("DOCMIND_WAIT_MIN", "1"))
_WAIT_MAX = float(os.environ.get("DOCMIND_WAIT_MAX", "3"))


class DocMindUser(HttpUser):
    wait_time = between(_WAIT_MIN, _WAIT_MAX)

    @task(2)
    def search(self):
        query = random.choice(QUERIES)
        self.client.post(
            "/api/search",
            json={"query": query, "strategy": "hybrid", "top_k": 5, "rerank": True},
            name="/api/search (hybrid+rerank)",
            timeout=30,
        )

    @task(1)
    def chat_stream(self):
        """SSE 流式问答。

        计时口径：uvicorn 先发响应头再流式吐帧，locust 对 stream=True 的
        内建计时 = 收到响应头的时间（毫秒级，无意义）——因此真正的
        「首 token 延迟」与「完整回答时长」都用手动事件上报：
        - /api/chat (first-token)：解析到第一条 delta 帧
        - /api/chat (full-answer)：收到 [DONE] 结束标记
        """
        query = random.choice(QUERIES)
        start = time.perf_counter()
        with self.client.post(
            "/api/chat",
            json={"messages": [{"role": "user", "content": query}], "top_k": 5, "stream": True},
            name="/api/chat (headers)",
            catch_response=True,
            stream=True,
            timeout=120,
        ) as resp:
            try:
                resp.raise_for_status()
                first_delta = True
                done = False
                for line in resp.iter_lines(decode_unicode=True):
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        done = True
                        break
                    event = json.loads(payload)
                    if event.get("type") == "error":
                        resp.failure(f"服务端错误: {event.get('message')}")
                        return
                    if first_delta and event.get("type") == "delta":
                        first_delta = False
                        self.environment.events.request.fire(
                            request_type="POST",
                            name="/api/chat (first-token)",
                            response_time=(time.perf_counter() - start) * 1000,
                            response_length=0,
                            exception=None,
                            context={},
                        )
                if not done:
                    resp.failure("未收到 [DONE] 结束标记")
                    return
                self.environment.events.request.fire(
                    request_type="POST",
                    name="/api/chat (full-answer)",
                    response_time=(time.perf_counter() - start) * 1000,
                    response_length=0,
                    exception=None,
                    context={},
                )
            except Exception as e:
                resp.failure(str(e))
