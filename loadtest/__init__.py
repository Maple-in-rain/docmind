"""压测包：locust 脚本 + 种子数据工具。

设计约束：本包不 import app.*——locust 进程不需要加载 Chroma 等重依赖，
查询池直接读 eval/data/testset.jsonl，与评估体系同源。
"""
