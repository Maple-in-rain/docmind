"""压测种子数据：上传评估语料（15 篇技术文档）到运行中的 DocMind。

用法（服务已启动后，在项目根目录）：
    python -X utf8 loadtest/seed_docs.py --base http://127.0.0.1:8000

注意：种子只需灌一次。场景 2（全 mock）可直接复用场景 1 入库的向量库——
MockEmbedder.dim=1024 与 bge-m3 一致，维度校验通过，检索结果无语义但
代码路径一致，吞吐测量不受影响（系统必须非空库，否则 ChatService 的
空库快捷路径会让压测数字虚高）。
"""

import argparse
from pathlib import Path

import httpx

CORPUS_DIR = Path(__file__).resolve().parent.parent / "eval" / "data" / "corpus"


def iter_corpus_files(corpus_dir: Path = CORPUS_DIR) -> list[Path]:
    return sorted(p for p in corpus_dir.glob("*.md") if p.name != "README.md")


def upload_doc(base: str, path: Path) -> dict:
    with open(path, "rb") as f:
        resp = httpx.post(
            f"{base}/api/documents/upload",
            files={"file": (path.name, f, "text/markdown")},
            data={"title": path.stem},
            timeout=180,
        )
    resp.raise_for_status()
    return resp.json()


def main(argv=None):
    parser = argparse.ArgumentParser(description="上传评估语料到运行中的 DocMind（压测种子数据）")
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    args = parser.parse_args(argv)

    files = iter_corpus_files()
    for i, path in enumerate(files, 1):
        result = upload_doc(args.base, path)
        print(f"[{i}/{len(files)}] {path.name} -> doc_id={result['doc_id']} chunks={result['chunk_count']}", flush=True)


if __name__ == "__main__":
    main()
