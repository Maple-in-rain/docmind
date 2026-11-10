# pytest 根目录配置：确保测试中 `from app...` 可导入

import pytest


@pytest.fixture(autouse=True)
def isolate_api_credentials(monkeypatch):
    """离线测试不依赖开发机 .env；MockTransport 测试显式提供占位 key。"""
    from app.config import settings
    monkeypatch.setattr(settings, "deepseek_api_key", "")
    monkeypatch.setattr(settings, "siliconflow_api_key", "")
