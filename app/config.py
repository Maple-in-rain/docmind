"""全局配置：环境变量 > .env 文件 > 默认值。

.pydantic-settings 会自动读取项目根目录的 .env 文件。
注意：.env 含 API key，已在 .gitignore 中排除，严禁提交。
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- 路径 ----
    data_dir: Path = Path(__file__).resolve().parent.parent / "data"

    # ---- LLM（DeepSeek）----
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"

    # ---- Embedding / Rerank（硅基流动）----
    siliconflow_api_key: str = ""
    siliconflow_base_url: str = "https://api.siliconflow.cn/v1"
    embedding_model: str = "BAAI/bge-m3"
    rerank_model: str = "BAAI/bge-reranker-v2-m3"

    # ---- 检索参数（默认值待第 3 周评估实验用数据定稿）----
    chunk_size: int = 512
    chunk_overlap: int = 50
    top_k: int = 5
    collection_name: str = "docmind"

    # ---- 上传 ----
    max_upload_mb: int = 20


settings = Settings()
