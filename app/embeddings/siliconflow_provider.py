"""硅基流动 BAAI/bge-m3 向量化（OpenAI 兼容协议）。

选 API 而非本地模型的原因（面试常问）：
1. 免费额度足够个人项目使用；
2. 学生机 2G 内存跑不动本地 embedding 模型；
3. 避开 torch 在部分 Python 版本的安装问题。
"""

import httpx

from ..config import settings
from .base import EmbeddingProvider

_BATCH_SIZE = 32  # 单次 API 请求的最大文本条数，超长输入分批


class SiliconFlowEmbeddingProvider(EmbeddingProvider):
    name = "siliconflow-bge-m3"
    dim = 1024

    def __init__(self, api_key: str = "", base_url: str = "", model: str = ""):
        self.api_key = api_key or settings.siliconflow_api_key
        self.base_url = (base_url or settings.siliconflow_base_url).rstrip("/")
        self.model = model or settings.embedding_model

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if not self.api_key:
            raise RuntimeError("未配置硅基流动 API key，请在 .env 中设置 SILICONFLOW_API_KEY")

        all_embeddings: list[list[float]] = []
        for i in range(0, len(texts), _BATCH_SIZE):
            batch = texts[i : i + _BATCH_SIZE]
            resp = httpx.post(
                f"{self.base_url}/embeddings",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": self.model, "input": batch, "encoding_format": "float"},
                timeout=60,
            )
            resp.raise_for_status()
            data = sorted(resp.json()["data"], key=lambda d: d["index"])  # 保证与输入顺序一致
            all_embeddings.extend(d["embedding"] for d in data)
        return all_embeddings
