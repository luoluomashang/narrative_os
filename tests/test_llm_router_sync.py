"""
tests/test_llm_router_sync.py — Phase 5-F2: LLM Router Settings 同步测试

验证 Settings → Router 实时同步、惰性加载、全局单例。
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from narrative_os.execution.llm_router import (
    Backend,
    LLMRouter,
    ModelTier,
    _DEFAULT_MODELS,
    router,
)


# ------------------------------------------------------------------ #
# F2-1: refresh_from_settings 更新 Custom 模型                         #
# ------------------------------------------------------------------ #

def test_refresh_from_settings_updates_custom():
    """Settings 更新后 Router Custom 模型同步。"""
    r = LLMRouter()
    # 修改 settings 中的值
    with patch("narrative_os.execution.llm_router.settings") as mock_settings:
        mock_settings.custom_llm_model_small = "my-small-v2"
        mock_settings.custom_llm_model_medium = "my-medium-v2"
        mock_settings.custom_llm_model_large = "my-large-v2"
        r.refresh_from_settings()

    assert r._models[Backend.CUSTOM][ModelTier.SMALL] == "my-small-v2"
    assert r._models[Backend.CUSTOM][ModelTier.MEDIUM] == "my-medium-v2"
    assert r._models[Backend.CUSTOM][ModelTier.LARGE] == "my-large-v2"


# ------------------------------------------------------------------ #
# F2-2: _DEFAULT_MODELS 不含 import 时 Settings 值                     #
# ------------------------------------------------------------------ #

def test_default_models_no_import_time_settings():
    """_DEFAULT_MODELS 不应包含 CUSTOM 后端（仅在实例化时惰性加载）。"""
    assert Backend.CUSTOM not in _DEFAULT_MODELS


# ------------------------------------------------------------------ #
# F2-3: PUT /settings/llm 后 Router 立即反映新值                        #
# ------------------------------------------------------------------ #

def test_api_update_triggers_refresh():
    """PUT /settings/llm 成功后 router.refresh_from_settings() 应被调用。"""
    from narrative_os.interface.api import app

    client = TestClient(app, raise_server_exceptions=False)

    with (
        patch("narrative_os.infra.config.settings") as mock_settings,
        patch("narrative_os.execution.llm_router.router") as mock_router,
    ):
        mock_settings.update_llm_settings = MagicMock()
        resp = client.put(
            "/settings/llm",
            json={"custom_llm_base_url": "http://localhost:8080/v1"},
        )

    assert resp.status_code == 200
    mock_router.refresh_from_settings.assert_called_once()


# ------------------------------------------------------------------ #
# F2-4: 全局只有一个 default_router 实例                                 #
# ------------------------------------------------------------------ #

def test_single_router_instance():
    """模块级 router 是 LLMRouter 实例。"""
    assert isinstance(router, LLMRouter)

    # 再次 import 得到同一对象
    from narrative_os.execution.llm_router import router as r2
    assert r2 is router
