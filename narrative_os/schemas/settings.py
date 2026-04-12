"""schemas/settings.py — 设置管理请求/响应模型。"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class LLMProviderStatus(BaseModel):
    available: bool = False
    models: list[str] | dict[str, str] = Field(default_factory=list)


class LLMCurrentConfig(BaseModel):
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    ollama_base_url: str = ""
    deepseek_api_key: str = ""
    custom_llm_base_url: str = ""
    custom_llm_api_key: str = ""
    custom_llm_model_small: str = ""
    custom_llm_model_medium: str = ""
    custom_llm_model_large: str = ""


class LLMSettingsResponse(BaseModel):
    providers: dict[str, LLMProviderStatus]
    current_config: LLMCurrentConfig


class LLMSettingsUpdateResponse(BaseModel):
    success: bool = True
    updated_keys: list[str]


class LLMProviderUpdateRequest(BaseModel):
    """更新 LLM 提供商配置的请求体。所有字段均为可选。"""
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    ollama_base_url: Optional[str] = None
    deepseek_api_key: Optional[str] = None
    custom_llm_base_url: Optional[str] = None
    custom_llm_api_key: Optional[str] = None
    custom_llm_model_small: Optional[str] = None
    custom_llm_model_medium: Optional[str] = None
    custom_llm_model_large: Optional[str] = None


class LLMTestRequest(BaseModel):
    """测试指定 provider 连通性的请求体。"""
    provider: Literal["openai", "anthropic", "ollama", "deepseek", "custom"]


class LLMTestResult(BaseModel):
    success: bool
    latency_ms: int
    model_used: str | None = None
    error: str | None = None
