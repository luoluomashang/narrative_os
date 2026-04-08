"""
infra/config.py — 配置加载器

从 narrativespace/config/*.yaml 只读加载规则库，
同时支持项目级 .narrative_os.env 或环境变量覆盖。
"""

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

# narrativespace 规则库路径（只读引用）
_REPO_ROOT = Path(__file__).resolve().parents[3]  # novel-control-world/
_NS_CONFIG_DIR = _REPO_ROOT / "narrativespace" / "config"
_ENV_FILE = _REPO_ROOT / "narrative_os" / ".narrative_os.env"

load_dotenv(_ENV_FILE, override=False)


@lru_cache(maxsize=64)
def load_yaml(name: str) -> dict[str, Any]:
    """
    按名称加载 narrativespace/config/<name>.yaml。
    结果被 lru_cache 缓存，进程内只读一次。
    """
    path = _NS_CONFIG_DIR / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def get_env(key: str, default: str | None = None) -> str | None:
    """读取环境变量，支持 .narrative_os.env 文件。"""
    return os.environ.get(key, default)


class Settings:
    """运行时全局设置（单例）。"""

    # LLM keys & endpoints
    openai_api_key: str = os.environ.get("OPENAI_API_KEY", "")
    anthropic_api_key: str = os.environ.get("ANTHROPIC_API_KEY", "")
    ollama_base_url: str = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

    # DeepSeek
    deepseek_api_key: str = os.environ.get("DEEPSEEK_API_KEY", "")

    # 自定义 OpenAI 兼容接口（vLLM / LM Studio / Azure / 任意 OpenAI-compat 端点）
    custom_llm_base_url: str = os.environ.get("CUSTOM_LLM_BASE_URL", "http://localhost:8080/v1")
    custom_llm_api_key: str = os.environ.get("CUSTOM_LLM_API_KEY", "")
    custom_llm_model_small: str = os.environ.get("CUSTOM_LLM_MODEL_SMALL", "custom-small")
    custom_llm_model_medium: str = os.environ.get("CUSTOM_LLM_MODEL_MEDIUM", "custom-medium")
    custom_llm_model_large: str = os.environ.get("CUSTOM_LLM_MODEL_LARGE", "custom-large")
    llm_strategy: str = os.environ.get("LLM_STRATEGY", "COST_OPTIMIZED")

    # 成本控制
    daily_token_budget: int = int(os.environ.get("DAILY_TOKEN_BUDGET", "500000"))
    max_retries: int = int(os.environ.get("MAX_RETRIES", "3"))

    # ChromaDB 路径（项目相对）
    chroma_db_path: str = os.environ.get("CHROMA_DB_PATH", ".narrative_os/chroma")

    # 日志
    log_level: str = os.environ.get("LOG_LEVEL", "INFO")
    log_dir: str = os.environ.get("LOG_DIR", ".narrative_os/logs")

    # 项目状态目录
    state_dir: str = os.environ.get("STATE_DIR", ".narrative_os")

    # 开发服务器端口配置
    api_host: str = os.environ.get("API_HOST", "127.0.0.1")
    api_port: int = int(os.environ.get("API_PORT", "8000"))
    frontend_port: int = int(os.environ.get("FRONTEND_PORT", "5173"))

    def update_llm_settings(self, data: dict[str, Any]) -> None:
        """
        运行时更新 LLM 相关设置，同时回写 .narrative_os.env 文件中对应的 key。
        只处理 LLM 相关字段，防止意外覆盖其他配置。
        """
        _allowed_keys = {
            "openai_api_key": "OPENAI_API_KEY",
            "anthropic_api_key": "ANTHROPIC_API_KEY",
            "ollama_base_url": "OLLAMA_BASE_URL",
            "deepseek_api_key": "DEEPSEEK_API_KEY",
            "custom_llm_base_url": "CUSTOM_LLM_BASE_URL",
            "custom_llm_api_key": "CUSTOM_LLM_API_KEY",
            "custom_llm_model_small": "CUSTOM_LLM_MODEL_SMALL",
            "custom_llm_model_medium": "CUSTOM_LLM_MODEL_MEDIUM",
            "custom_llm_model_large": "CUSTOM_LLM_MODEL_LARGE",
        }
        for attr, env_key in _allowed_keys.items():
            if attr in data:
                value = str(data[attr])
                setattr(self, attr, value)
                os.environ[env_key] = value

        # 回写 .narrative_os.env（更新或追加）
        _write_env_keys({_allowed_keys[k]: str(data[k]) for k in data if k in _allowed_keys})


def _mask_key(key: str) -> str:
    """将 API key 掩码处理，只显示末 4 位。"""
    if not key or len(key) <= 8:
        return "****"
    return key[:4] + "*" * (len(key) - 8) + key[-4:]


def _write_env_keys(updates: dict[str, str]) -> None:
    """
    将 updates 中的 KEY=VALUE 写入 .narrative_os.env。
    已有行则替换，新 key 则追加。
    """
    env_path = _ENV_FILE
    if not env_path.exists():
        lines: list[str] = []
    else:
        lines = env_path.read_text(encoding="utf-8").splitlines(keepends=True)

    written = set()
    new_lines: list[str] = []
    for line in lines:
        match = re.match(r"^([A-Z_][A-Z0-9_]*)\s*=", line)
        if match and match.group(1) in updates:
            key = match.group(1)
            new_lines.append(f"{key}={updates[key]}\n")
            written.add(key)
        else:
            new_lines.append(line)

    # 追加未在文件中出现的 key
    for key, value in updates.items():
        if key not in written:
            new_lines.append(f"{key}={value}\n")

    env_path.write_text("".join(new_lines), encoding="utf-8")


settings = Settings()
