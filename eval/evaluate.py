"""检索质量网格实验：一条命令复现全量评估数字（"数据驱动"的落点）。

用法（配置好 .env 后，在项目根目录运行）：
    python -X utf8 -m eval.evaluate                     # 全量 36 格（真实 API）
    python -X utf8 -m eval.evaluate --only chunk512_o50_hybrid_on

评估口径（重要，面试可讲）：
- 相关性判定是**段落级**：测试集每条 QA 记录答案出处段落（source_passage），
  检索块与出处段落的余弦相似度 ≥ 阈值才算相关（近似段落级 qrels）；
- 为什么不用文档级：15 篇语料上文档级 top-10 召回必然饱和（全 1.0），
  指标失去区分度——这是本项目第一轮网格实验实测发现的，收紧到段落级后
  才能真实区分分块/策略/重排的优劣。

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

import numpy as np

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

# 段落级相关性阈值：检索块与答案出处段落的余弦相似度达到该值才算命中。
# bge-m3 对近同源文本相似度约 0.85+，同主题不同段落约 0.5~0.7。
_PASSAGE_SIM_THRESHOLD = 0.8


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


def _normalize_rows(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return matrix / np.maximum(norms, 1e-12)


def prepare_qrels(
    chunk_cache: dict,
    corpus: list[dict],
    embedder,
    testset: list[dict],
    passage_threshold: float = _PASSAGE_SIM_THRESHOLD,
) -> dict:
    """预计算每种分块配置的段落级 qrels。

    返回 {(chunk_size, overlap): {query_id: {相关块的语料全局下标}}}。
    全局下标按「语料文档顺序 × 块顺序」展平，与 run_cell 的入库顺序一致。
    """
    qrels = {}
    for (size, overlap), per_doc in chunk_cache.items():
        # 展平成全局块向量矩阵（顺序必须与 run_cell 的入库顺序一致）
        all_embeddings = []
        for doc in corpus:
            _chunks, embs = per_doc[doc["name"]]
            all_embeddings.extend(embs)
        emb_matrix = _normalize_rows(np.asarray(all_embeddings, dtype=np.float64))

        per_config: dict[int, set[int]] = {}
        for item in testset:
            if not item.get("source_passage"):
                continue
            gold = _normalize_rows(np.asarray([embedder.embed([item["source_passage"]])[0]], dtype=np.float64))[0]
            sims = emb_matrix @ gold
            per_config[item["id"]] = {int(i) for i in np.where(sims >= passage_threshold)[0]}
        qrels[(size, overlap)] = per_config
    return qrels


def common_queries(qrels: dict, testset: list[dict]) -> list[dict]:
    """统一评估子集：只保留在全部相关分块配置下都可判定的查询。

    出处段落在小分块下可能被切散（无块达到相似度阈值），若各配置各跑各的
    查询子集，跨配置指标对比就不公平——取交集后所有格子跑同一批查询。
    """
    configs = list(qrels.values())
    if not configs:
        return []
    ids = [item["id"] for item in testset if all(item["id"] in cfg and cfg[item["id"]] for cfg in configs)]
    return [t for t in testset if t["id"] in ids]


def run_cell(
    cfg: dict,
    embedder,
    reranker,
    chunk_cache: dict,
    testset: list[dict],
    qrels_for_config: dict[int, set[int]],
    workdir: Path,
) -> dict:
    """单个格子：独立数据目录重建索引 → 段落级 qrels → 指标汇总。

    qrels_for_config：{query_id: {相关块的语料全局下标}}（prepare_qrels 预计算），
    全局下标与入库顺序一致，run_cell 内映射回 chunk_id。
    """
    shutil.rmtree(workdir, ignore_errors=True)
    workdir.mkdir(parents=True, exist_ok=True)

    db = Database(workdir / "docmind.db")
    vector_store = ChromaVectorStore(workdir / "chroma", dim=embedder.dim)

    # 入库（复用缓存的解析/向量结果，只写存储层），同时记录全局下标 → chunk_id 映射
    name_to_doc_id: dict[str, int] = {}
    global_id_order: list[str] = []  # 下标 i 对应入库顺序的第 i 个块
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
        global_id_order.extend(chunk_ids)

    bm25_index = BM25Index(db)
    search = SearchService(embedder, vector_store, db, bm25_index, reranker)

    queries = []
    skipped = 0
    for item in testset:
        if item.get("doc") not in name_to_doc_id or item["id"] not in qrels_for_config:
            skipped += 1
            continue
        relevant = {global_id_order[i] for i in qrels_for_config[item["id"]]}
        if not relevant:
            skipped += 1
            continue
        results = search.search(item["question"], cfg["strategy"], TOP_K, rerank=cfg["rerank"])
        retrieved = list(dict.fromkeys(r["chunk_id"] for r in results))  # 去重保序
        queries.append((relevant, retrieved))

    metrics = evaluate(queries)
    shutil.rmtree(workdir, ignore_errors=True)  # 跑完即清理，结果只在 CSV
    return {**cfg, "n_queries": len(queries), "n_skipped": skipped, **metrics}


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
    passage_threshold: float = _PASSAGE_SIM_THRESHOLD,
) -> list[dict]:
    embedder = _MemoizedEmbedder(embedder)  # 分块/查询向量全部按文本缓存复用
    # 缓存配置从本次要跑的格子推导（只向量化这些格子用到的分块配置）
    chunk_sizes = tuple(sorted({c["chunk_size"] for c in cells}))
    overlaps = tuple(sorted({c["overlap"] for c in cells}))
    chunk_cache = prepare_chunk_cache(corpus, embedder, chunk_sizes, overlaps)

    # 段落级 qrels 预计算 + 统一评估子集（跨配置只比同一批查询）
    qrels = prepare_qrels(chunk_cache, corpus, embedder, testset, passage_threshold)
    testset = common_queries(qrels, testset)
    if not testset:
        raise RuntimeError(
            f"统一评估子集为空：所有查询在至少一种分块配置下都无相关块，"
            f"请检查 source_passage 与 passage_threshold（当前 {passage_threshold}）"
        )
    print(f"统一评估子集：{len(testset)} 条查询（全部分块配置下均可判定）", flush=True)

    # 断点续跑：CSV 中已完成的格子跳过（重跑命令只补缺）
    done_names = {r["name"] for r in load_csv_rows(output_csv)}

    rows = []
    for cfg in cells:
        if cfg["name"] in done_names:
            print(f"[{cfg['name']}] 已完成（CSV 命中），跳过", flush=True)
            continue
        print(f"[{cfg['name']}] 运行中 ...", flush=True)
        try:
            row = run_cell(
                cfg, embedder, reranker, chunk_cache, testset,
                qrels[(cfg["chunk_size"], cfg["overlap"])],
                workdir_root / cfg["name"],
            )
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
