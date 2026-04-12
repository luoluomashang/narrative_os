"""routers/settings.py — LLM 提供商配置路由模块。"""
from __future__ import annotations

import time
from fastapi import APIRouter, HTTPException, status

from narrative_os.schemas.settings import (
    LLMCurrentConfig,
    LLMProviderStatus,
    LLMProviderUpdateRequest,
    LLMSettingsResponse,
    LLMSettingsUpdateResponse,
    LLMTestRequest,
    LLMTestResult,
)

router = APIRouter(tags=["settings"])


@router.get("/settings/llm", response_model=LLMSettingsResponse, summary="读取 LLM 提供商配置")
async def get_llm_settings() -> LLMSettingsResponse:
    from narrative_os.infra.config import settings, _mask_key
    from narrative_os.execution.llm_router import router as llm_router
    provider_status = {
        name: LLMProviderStatus.model_validate(payload)
        for name, payload in llm_router.get_provider_status().items()
    }
    return LLMSettingsResponse(
        providers=provider_status,
        current_config=LLMCurrentConfig(
            openai_api_key=_mask_key(settings.openai_api_key),
            anthropic_api_key=_mask_key(settings.anthropic_api_key),
            ollama_base_url=settings.ollama_base_url,
            deepseek_api_key=_mask_key(settings.deepseek_api_key),
            custom_llm_base_url=settings.custom_llm_base_url,
            custom_llm_api_key=_mask_key(settings.custom_llm_api_key),
            custom_llm_model_small=settings.custom_llm_model_small,
            custom_llm_model_medium=settings.custom_llm_model_medium,
            custom_llm_model_large=settings.custom_llm_model_large,
        ),
    )


@router.put("/settings/llm", response_model=LLMSettingsUpdateResponse, summary="更新 LLM 提供商配置")
async def update_llm_settings(req: LLMProviderUpdateRequest) -> LLMSettingsUpdateResponse:
    from narrative_os.infra.config import settings
    from narrative_os.execution.llm_router import router as llm_router
    payload = {k: v for k, v in req.model_dump().items() if v is not None}
    if not payload:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请至少提供一个需要更新的字段")
    settings.update_llm_settings(payload)
    llm_router.refresh_from_settings()
    return LLMSettingsUpdateResponse(success=True, updated_keys=list(payload.keys()))


@router.post("/settings/llm/test", response_model=LLMTestResult, summary="测试 LLM 提供商连通性")
async def test_llm_connection(req: LLMTestRequest) -> LLMTestResult:
    from narrative_os.execution.llm_router import LLMRequest, LLMRouter, Backend
    from narrative_os.infra.config import settings

    provider_map = {
        "openai": Backend.OPENAI,
        "anthropic": Backend.ANTHROPIC,
        "ollama": Backend.OLLAMA,
        "deepseek": Backend.DEEPSEEK,
        "custom": Backend.CUSTOM,
    }
    backend = provider_map[req.provider]

    if req.provider == "openai" and not settings.openai_api_key:
        return LLMTestResult(success=False, error="未配置 OPENAI_API_KEY", latency_ms=0)
    if req.provider == "anthropic" and not settings.anthropic_api_key:
        return LLMTestResult(success=False, error="未配置 ANTHROPIC_API_KEY", latency_ms=0)
    if req.provider == "deepseek" and not settings.deepseek_api_key:
        return LLMTestResult(success=False, error="未配置 DEEPSEEK_API_KEY", latency_ms=0)

    test_req = LLMRequest(
        task_type="default",
        messages=[{"role": "user", "content": "回复 OK"}],
        backend_override=backend,
        max_tokens=10,
        temperature=0.0,
        skill_name="connection_test",
    )
    tmp_router = LLMRouter()
    t0 = time.time()
    try:
        resp = await tmp_router.call(test_req)
        latency = round((time.time() - t0) * 1000)
        return LLMTestResult(success=True, latency_ms=latency, model_used=resp.model_used)
    except Exception as exc:
        latency = round((time.time() - t0) * 1000)
        return LLMTestResult(success=False, error=str(exc), latency_ms=latency)
