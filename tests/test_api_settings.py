"""
tests/test_api_settings.py — 阶段六：LLM 配置端点测试

覆盖三个 settings 端点：
  GET  /settings/llm   — 读取 LLM 配置结构
  PUT  /settings/llm   — 更新 LLM 配置（含输入验证）
  POST /settings/llm/test — 连通性测试
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from narrative_os.interface.api import app


@pytest.fixture()
def client():
    return TestClient(app, raise_server_exceptions=False)


# ------------------------------------------------------------------ #
# GET /settings/llm                                                    #
# ------------------------------------------------------------------ #

def test_get_llm_settings_structure(client):
    """GET /settings/llm 返回含 providers 和 current_config 的结构。"""
    mock_status = {
        "openai": {"available": False, "models": ["gpt-4o", "gpt-4o-mini"]},
        "anthropic": {"available": False, "models": ["claude-3-5-sonnet-20241022"]},
        "ollama": {"available": False, "models": ["llama3"]},
        "deepseek": {"available": False, "models": ["deepseek-chat"]},
        "custom": {"available": False, "models": []},
    }

    with patch("narrative_os.execution.llm_router.LLMRouter.get_provider_status",
               return_value=mock_status):
        resp = client.get("/settings/llm")

    assert resp.status_code == 200
    data = resp.json()

    # 必须含顶层字段
    assert "providers" in data
    assert "current_config" in data

    # providers 包含各已知 provider
    providers = data["providers"]
    assert isinstance(providers, dict)
    for provider in ("openai", "anthropic", "ollama", "deepseek", "custom"):
        assert provider in providers

    # current_config 含配置项（API key 已掩码处理）
    cfg = data["current_config"]
    assert "openai_api_key" in cfg
    assert "anthropic_api_key" in cfg
    assert "deepseek_api_key" in cfg
    assert "custom_llm_base_url" in cfg

    # 确保不返回明文 key（掩码后不含 "sk-real" 等明文前缀）
    for key_field in ("openai_api_key", "anthropic_api_key", "deepseek_api_key"):
        val = cfg[key_field]
        # 若有值，必须是掩码格式（含 **** 或为空字符串）
        if val:
            assert "****" in val or val == "", \
                f"{key_field} 不应返回明文：{val}"


def test_get_llm_settings_providers_have_available_flag(client):
    """providers 字典中的每个 provider 条目都含 available 字段。"""
    mock_status = {
        p: {"available": False, "models": []}
        for p in ("openai", "anthropic", "ollama", "deepseek", "custom")
    }

    with patch("narrative_os.execution.llm_router.LLMRouter.get_provider_status",
               return_value=mock_status):
        resp = client.get("/settings/llm")

    assert resp.status_code == 200
    for name, info in resp.json()["providers"].items():
        assert "available" in info, f"provider '{name}' 缺少 available 字段"


# ------------------------------------------------------------------ #
# PUT /settings/llm                                                    #
# ------------------------------------------------------------------ #

def test_update_llm_settings_valid_key(client):
    """PUT /settings/llm 传入合法字段时返回 200 + success=True。"""
    with patch("narrative_os.infra.config.Settings.update_llm_settings") as mock_update:
        resp = client.put("/settings/llm", json={
            "ollama_base_url": "http://localhost:11434",
        })

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "updated_keys" in data
    assert "ollama_base_url" in data["updated_keys"]


def test_update_llm_settings_empty_payload_returns_400(client):
    """不传任何字段时应返回 400（无需要更新的字段）。"""
    resp = client.put("/settings/llm", json={})
    assert resp.status_code == 400


def test_update_llm_settings_validates_input(client):
    """PUT 传入非法字段名（不在 LLMProviderUpdateRequest schema 中）时返回 422。"""
    resp = client.put("/settings/llm", json={
        "unknown_field_xyz": "some_value",
    })
    # 非法字段被 Pydantic 忽略（extra=ignore），结果等价于空 payload → 400
    # 若 Pydantic 配置了 extra=forbid 则返回 422
    assert resp.status_code in (400, 422)


# ------------------------------------------------------------------ #
# POST /settings/llm/test                                              #
# ------------------------------------------------------------------ #

def test_test_llm_connection_returns_result(client):
    """POST /settings/llm/test 返回含 success 字段的结果（不真实调用 LLM）。"""
    resp = client.post("/settings/llm/test", json={"provider": "openai"})

    assert resp.status_code == 200
    data = resp.json()
    # 必须含 success 字段
    assert "success" in data
    # success 为 False 时，必须含 error 说明（未配置 key 的情况）
    if not data["success"]:
        assert "error" in data
    # latency_ms 字段存在
    assert "latency_ms" in data
    assert isinstance(data["latency_ms"], int)


def test_test_llm_connection_unconfigured_provider_returns_failure(client):
    """未配置密钥时，test 端点应返回 success=False 而非 500。"""
    # deepseek_api_key 未设置时，应优雅返回失败而非抛异常
    with patch("narrative_os.infra.config.settings") as mock_settings:
        mock_settings.deepseek_api_key = ""
        mock_settings.openai_api_key = ""
        mock_settings.anthropic_api_key = ""
        resp = client.post("/settings/llm/test", json={"provider": "deepseek"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert "error" in data


def test_test_llm_connection_invalid_provider_returns_422(client):
    """传入非枚举值 provider 应返回 422。"""
    resp = client.post("/settings/llm/test", json={"provider": "unknown_provider"})
    assert resp.status_code == 422


def test_test_llm_connection_ollama_succeeds_when_available(client):
    """当 Ollama router.call 成功时，返回 success=True + latency_ms。"""
    from narrative_os.execution.llm_router import LLMResponse, Backend

    mock_response = LLMResponse(
        content="OK",
        model_used="llama3",
        backend=Backend.OLLAMA,
        prompt_tokens=5,
        completion_tokens=2,
        latency_ms=42.0,
    )

    with patch("narrative_os.execution.llm_router.LLMRouter.call",
               new_callable=AsyncMock, return_value=mock_response):
        resp = client.post("/settings/llm/test", json={"provider": "ollama"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["latency_ms"] >= 0
    assert data.get("model_used") == "llama3"
