"""loadtest 包纯函数测试：查询池加载、语料枚举、locustfile 子进程验证。

注意：locustfile 不能在 pytest 进程里 import——locust 的 import 会做 gevent
全局 monkey-patch（socket/thread），毒化同进程后续用例的 asyncio.to_thread
（test_chat 会死锁）。因此 locustfile 的验证放在子进程里做。
"""

import json
import subprocess
import sys

from loadtest.queries import load_queries
from loadtest.seed_docs import CORPUS_DIR, iter_corpus_files


def test_load_queries_from_default_testset():
    queries = load_queries()
    assert len(queries) == 84
    assert all(isinstance(q, str) and q.strip() for q in queries)
    assert any("一" <= q[0] <= "鿿" for q in queries), "查询池应为中文问题"


def test_load_queries_custom_path(tmp_path):
    testset = tmp_path / "t.jsonl"
    testset.write_text(
        json.dumps({"id": 1, "question": "问题一"}) + "\n\n"
        + json.dumps({"id": 2, "question": "问题二"}) + "\n",
        encoding="utf-8",
    )
    assert load_queries(testset) == ["问题一", "问题二"]


def test_locustfile_loads_in_subprocess():
    """locustfile 语法正确、查询池加载成功、两个任务齐全（隔离子进程防 gevent 污染）"""
    script = (
        "from loadtest.locustfile import DocMindUser, QUERIES\n"
        "assert len(QUERIES) == 84, QUERIES\n"
        "names = [t.__name__ for t in DocMindUser.tasks]\n"
        "assert names.count('search') == 2 and names.count('chat_stream') == 1, names\n"
        "print('locustfile OK')\n"
    )
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", "-c", script],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert proc.returncode == 0, f"stdout={proc.stdout}\nstderr={proc.stderr}"


def test_iter_corpus_files():
    files = iter_corpus_files()
    assert len(files) == 15
    assert all(f.suffix == ".md" for f in files)
    assert files == sorted(files)
    assert all("README" not in f.name for f in files)
    assert CORPUS_DIR.is_dir()
