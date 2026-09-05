"""硅基流动 BAAI/bge-reranker-v2-m3 重排。

选择理由（与 embedding 相同）：API 免费额度、学生机跑不动本地重排模型、
torch 安装坑。协议：POST /v1/rerank（Jina 风格），
返回 {"results": [{"index": i, "relevance_score": s}, ...]}。

重试策略：429（限流，免费额度常见）与 5xx 指数退避重试（最多 3 次），
尊重响应头 Retry-After（秒）；4xx 其余错误是请求本身的问题，立即抛出。
"""

import time

import httpx

from ..config import settings
from .base import RerankerProvider

_MAX_RETRIES = 3
_RETRY_STATUSES = frozenset({429})  # 429 必重试；5xx 动态判定见 _post


class SiliconFlowRerankerProvider(RerankerProvider):
    name = "siliconflow-bge-reranker-v2-m3"

    def __init__(self, api_key: str = "", base_url: str = "", model: str = "", transport=None):
        self.api_key = api_key or settings.siliconflow_api_key
        self.base_url = (base_url or settings.siliconflow_base_url).rstrip("/")
        self.model = model or settings.rerank_model
        self.transport = transport  # 测试注入用，生产为 None（真实网络）

    def rerank(self, query: str, documents: list[str], top_n: int | None = None) -> list[tuple[int, float]]:
        if not documents:
            return []
        if not self.api_key:
            raise RuntimeError("未配置硅基流动 API key，请在 .env 中设置 SILICONFLOW_API_KEY")

        payload: dict = {"model": self.model, "query": query, "documents": documents}
        if top_n is not None:
            payload["top_n"] = min(top_n, len(documents))
        data = self._post(payload)

        results = data.get("results", [])
        # 防御性重排序：不信任 API 返回顺序，按相关性分数降序重排
        scored = sorted(
            ((int(r["index"]), float(r["relevance_score"])) for r in results),
            key=lambda kv: -kv[1],
        )
        return scored[:top_n] if top_n else scored

    def _post(self, payload: dict) -> dict:
        """单次请求 + 重试：429/5xx 指数退避，尊重 Retry-After 头"""
        last_error: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                with httpx.Client(timeout=60, transport=self.transport) as client:
                    resp = client.post(
                        f"{self.base_url}/rerank",
                        headers={"Authorization": f"Bearer {self.api_key}"},
                        json=payload,
                    )
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as e:
                last_error = e
                status = e.response.status_code
                if status not in _RETRY_STATUSES and status < 500:
                    raise  # 4xx（除 429）：请求本身的问题，重试无意义
                retry_after = float(e.response.headers.get("Retry-After", "") or 0)
                time.sleep(retry_after if retry_after > 0 else 2 ** attempt)  # 1s、2s、4s
        raise RuntimeError(f"重排请求失败（已重试 {_MAX_RETRIES} 次）: {last_error}")

