"""检索质量网格实验：一条命令复现全量评估数字（"数据驱动"的落点）。

用法（配置好 .env 后，在项目根目录运行）：
    python -X utf8 -m eval.evaluate                     # 全量 36 格（真实 API）
    python -X utf8 -m eval.evaluate --only chunk512_o50_hybrid_on

输出：eval/results/grid_results.csv（UTF-8-sig，Excel 可直接打开）+ 控制台汇总表。

网格设计：分块 {256,512,768} × 重叠 {0,50} × 策略 {vector,bm25,hybrid} × 重排 {关,开}
        = 36 格。每格独立数据目录（互不污染），全量测试集逐条检索后汇总指标。

效率设计：解析与向量化只做一次——同一分块配置下的分块结果与向量
在内存缓存，跨策略/重排格复用（36 格中只有 6 种分块配置）；
查询向量只算一次，跨全部格子复用。

可注入 embedder/reranker：测试离线跑通（FakeEmbedder 等），生产走真实 API。
"""

import argparse
import csv
import json
import shutil
import sys
from itertools import product
from pathlib import Path

from app.chunking.fixed_chunker import FixedChunker
from app.embeddings.siliconflow_provider import SiliconFlowEmbeddingProvider
from app.parsers.registry import get_parser
from app.reranking.siliconflow_reranker import SiliconFlowRerankerProvider
from app.retrieval.bm25_index import BM25Index
from app.retrieval.vector_store import ChromaVectorStore
from app.services.search_service import SearchService
from app.storage.db import Database

from .metrics import evaluate

CORPUS_DIR = Path(__file__).parent / "data" / "corpus"
TESTSET_PATH = Path(__file__).parent / "data" / "testset.jsonl"
RESULTS_DIR = Path(__file__).parent / "results"

CHUNK_SIZES = (256, 512, 768)
OVERLAPS = (0, 50)
STRATEGIES = ("vector", "bm25", "hybrid")
RERANK_FLAGS = (False, True)
TOP_K = 10


def build_cells() -> list[dict]:
    cells = []
    for size, overlap, strategy, rerank in product(CHUNK_SIZES, OVERLAPS, STRATEGIES, RERANK_FLAGS):
        cells.append(
            {
                "name": f"chunk{size}_o{overlap}_{strategy}_{'on' if rerank else 'off'}",
                "chunk_size": size,
                "overlap": overlap,
                "strategy": strategy,
                "rerank": rerank,
            }
        )
    return cells


def load_corpus() -> list[dict]:
    """返回 [{name, text}]，name 为文件名——测试集以此引用文档（跨重建稳定）"""
    docs = []
    for path in sorted(CORPUS_DIR.glob("*")):
        if path.suffix.lower() in (".md", ".txt"):
            parsed = get_parser(path).parse(path)
            docs.append({"name": path.name, "text": parsed.text})
    return docs


def load_testset(path: Path | None = None) -> list[dict]:
    path = path or TESTSET_PATH
    if not path.exists():
        raise FileNotFoundError(f"测试集不存在: {path}（先运行 eval/testset_builder.py 生成）")
    items = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            items.append(json.loads(line))
    return items


def prepare_chunk_cache(corpus: list[dict], embedder, chunk_sizes=CHUNK_SIZES, overlaps=OVERLAPS) -> dict:
    """分块配置下的分块与向量，只解析/向量化一次。

    返回 {(chunk_size, overlap): {doc_name: (chunks, embeddings)}}。
    chunk_sizes/overlaps 可注入（离线测试用迷你配置）。
    """
    cache = {}
    for size, overlap in product(chunk_sizes, overlaps):
        chunker = FixedChunker(size, overlap)
        cache[(size, overlap)] = {
            doc["name"]: (chunks := chunker.split(doc["text"]), embedder.embed([c.text for c in chunks]))
            for doc in corpus
        }
    return cache


def run_cell(
    cfg: dict,
    embedder,
    reranker,
    chunk_cache: dict,
    testset: list[dict],
    workdir: Path,
) -> dict:
    """单个格子：独立数据目录重建索引 → 全量测试集检索 → 指标汇总"""
    shutil.rmtree(workdir, ignore_errors=True)
    workdir.mkdir(parents=True, exist_ok=True)

    db = Database(workdir / "docmind.db")
    vector_store = ChromaVectorStore(workdir / "chroma", dim=embedder.dim)

    # 入库（复用缓存的解析/向量结果，只写存储层）
    name_to_doc_id: dict[str, int] = {}
    for doc_name, (chunks, embeddings) in chunk_cache[(cfg["chunk_size"], cfg["overlap"])].items():
        doc_id = db.add_document(doc_name, doc_name, doc_name, len(chunks))
        chunk_ids = [f"{doc_id}-{i}" for i in range(len(chunks))]
        db.add_chunks([(cid, doc_id, i, c.text) for i, (cid, c) in enumerate(zip(chunk_ids, chunks))])
        vector_store.add(
            ids=chunk_ids,
            texts=[c.text for c in chunks],
            embeddings=embeddings,
            metadatas=[{"doc_id": doc_id, "seq": i, "title": doc_name} for i in range(len(chunks))],
        )
        name_to_doc_id[doc_name] = doc_id

    bm25_index = BM25Index(db)
    search = SearchService(embedder, vector_store, db, bm25_index, reranker)

    queries = []
    for item in testset:
        doc_id = name_to_doc_id.get(item["doc"])
        if doc_id is None:
            print(f"  警告：测试集引用了语料中不存在的文档 {item['doc']}，跳过", file=sys.stderr)
            continue
        results = search.search(item["question"], cfg["strategy"], TOP_K, rerank=cfg["rerank"])
        retrieved = list(dict.fromkeys(r["doc_id"] for r in results))  # 去重保序
        queries.append(({doc_id}, retrieved))

    metrics = evaluate(queries)
    shutil.rmtree(workdir, ignore_errors=True)  # 跑完即清理，结果只在 CSV
    return {**cfg, "n_queries": len(queries), **metrics}


class _MemoizedEmbedder:
    """按文本缓存 embed() 结果：查询向量跨全部格子只算一次。"""

    def __init__(self, base):
        self._base = base
        self._cache: dict[str, list[float]] = {}

    @property
    def dim(self):
        return self._base.dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        missing = [t for t in texts if t not in self._cache]
        if missing:
            for t, v in zip(missing, self._base.embed(missing)):
                self._cache[t] = v
        return [self._cache[t] for t in texts]


def _append_csv_row(output_csv: Path, row: dict) -> None:
    """逐格追加落盘：崩溃/限流中断不丢已完成格子的结果"""
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    exists = output_csv.exists()
    with open(output_csv, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(row.keys()))
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def load_csv_rows(output_csv: Path) -> list[dict]:
    if not output_csv.exists():
        return []
    with open(output_csv, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def run_grid(
    cells: list[dict],
    embedder,
    reranker,
    corpus: list[dict],
    testset: list[dict],
    output_csv: Path,
    workdir_root: Path,
) -> list[dict]:
    embedder = _MemoizedEmbedder(embedder)  # 分块/查询向量全部按文本缓存复用
    # 缓存配置从本次要跑的格子推导（只向量化这些格子用到的分块配置）
    chunk_sizes = tuple(sorted({c["chunk_size"] for c in cells}))
    overlaps = tuple(sorted({c["overlap"] for c in cells}))
    chunk_cache = prepare_chunk_cache(corpus, embedder, chunk_sizes, overlaps)

    # 断点续跑：CSV 中已完成的格子跳过（重跑命令只补缺）
    done_names = {r["name"] for r in load_csv_rows(output_csv)}

    rows = []
    for cfg in cells:
        if cfg["name"] in done_names:
            print(f"[{cfg['name']}] 已完成（CSV 命中），跳过", flush=True)
            continue
        print(f"[{cfg['name']}] 运行中 ...", flush=True)
        try:
            row = run_cell(cfg, embedder, reranker, chunk_cache, testset, workdir_root / cfg["name"])
        except Exception as e:
            # 单格失败不中断整批（限流等瞬时错误），重跑本命令即可续跑
            print(f"[{cfg['name']}] 失败：{e}（重跑本命令可续跑剩余格子）", file=sys.stderr, flush=True)
            continue
        rows.append(row)
        _append_csv_row(output_csv, row)

    return rows


def print_summary(rows: list[dict]) -> None:
    """控制台汇总表。rows 可能来自内存（float）或 CSV（str），统一转 float。"""
    print("\n按 recall@10 降序：")
    print("| 配置 | recall@3 | recall@5 | recall@10 | mrr@10 |")
    print("|------|----------|----------|-----------|--------|")
    for r in sorted(rows, key=lambda x: -float(x["recall@10"])):
        print(
            f"| {r['name']} | {float(r['recall@3']):.4f} | {float(r['recall@5']):.4f} "
            f"| {float(r['recall@10']):.4f} | {float(r['mrr@10']):.4f} |"
        )


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="检索质量网格实验")
    parser.add_argument("--only", help="只跑一个格子，如 chunk512_o50_hybrid_on")
    args = parser.parse_args(argv)

    cells = build_cells()
    if args.only:
        cells = [c for c in cells if c["name"] == args.only]
        if not cells:
            sys.exit(f"未找到格子: {args.only}")

    run_grid(
        cells,
        embedder=SiliconFlowEmbeddingProvider(),
        reranker=SiliconFlowRerankerProvider(),
        corpus=load_corpus(),
        testset=load_testset(),
        output_csv=RESULTS_DIR / "grid_results.csv",
        workdir_root=RESULTS_DIR / "_workdir",
    )
    print_summary(load_csv_rows(RESULTS_DIR / "grid_results.csv"))
    print(f"\n结果已写入 {RESULTS_DIR / 'grid_results.csv'}（续跑：重复执行本命令只补缺）")


if __name__ == "__main__":
    main()
