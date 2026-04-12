"""
infra/logging.py — 结构化日志

每次 LLM 调用、Agent 执行、Skill 调用都通过此模块记录。
格式：JSON Lines，每行一条 LogEntry。
"""

from __future__ import annotations

import contextvars
import json
import logging
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from narrative_os.infra.config import settings

# 请求级追踪 ID
_correlation_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "correlation_id", default=""
)


def set_correlation_id(cid: str) -> None:
    """设置当前上下文的 correlation_id（由 API 中间件调用）。"""
    _correlation_id.set(cid)


def get_correlation_id() -> str:
    """获取当前上下文的 correlation_id。"""
    return _correlation_id.get("")


def _ensure_log_dir() -> Path:
    p = Path(settings.log_dir)
    p.mkdir(parents=True, exist_ok=True)
    return p


class StructuredLogger:
    """
    写入 JSON Lines 日志文件 (.narrative_os/logs/narrative_YYYY-MM-DD.jsonl)。
    同时将 ERROR+ 级别输出到 stderr（Rich 兼容）。
    """

    def __init__(self) -> None:
        self._log_dir = _ensure_log_dir()
        self._stderr_handler = logging.StreamHandler(stream=sys.stderr)
        self._stderr_handler.setLevel(logging.ERROR)

    def _log_file(self) -> Path:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return self._log_dir / f"narrative_{date_str}.jsonl"

    def _write(self, entry: dict[str, Any]) -> None:
        self._log_dir.mkdir(parents=True, exist_ok=True)
        with self._log_file().open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def _build_entry(
        self,
        level: str,
        event: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "event": event,
        }
        cid = _correlation_id.get("")
        if cid:
            entry["correlation_id"] = cid
        entry.update(kwargs)
        return entry

    def info(self, event: str, **kwargs: Any) -> None:
        self._write(self._build_entry("INFO", event, **kwargs))

    def warn(self, event: str, **kwargs: Any) -> None:
        self._write(self._build_entry("WARN", event, **kwargs))

    def error(self, event: str, **kwargs: Any) -> None:
        entry = self._build_entry("ERROR", event, **kwargs)
        self._write(entry)
        print(json.dumps(entry, ensure_ascii=False), file=sys.stderr)

    def llm_call(
        self,
        *,
        model: str,
        skill: str,
        prompt_tokens: int,
        completion_tokens: int,
        latency_ms: float,
        success: bool,
        agent: str | None = None,
        error: str | None = None,
    ) -> None:
        """专用：记录每次 LLM 调用的遥测数据。"""
        self._write(
            self._build_entry(
                "LLM",
                "llm_call",
                model=model,
                skill=skill,
                agent=agent,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
                latency_ms=latency_ms,
                success=success,
                error=error,
            )
        )

    def agent_exec(
        self,
        *,
        agent: str,
        status: str,  # started | completed | failed
        input_summary: str = "",
        output_summary: str = "",
        elapsed_ms: float = 0.0,
    ) -> None:
        """专用：记录 Agent 执行事件。"""
        self._write(
            self._build_entry(
                "AGENT",
                "agent_exec",
                agent=agent,
                status=status,
                input_summary=input_summary,
                output_summary=output_summary,
                elapsed_ms=elapsed_ms,
            )
        )


# 全局单例
logger = StructuredLogger()


def get_logger(name: str | None = None) -> StructuredLogger:
    """返回全局 StructuredLogger 单例（name 参数保留用于未来模块化扩展）。"""
    return logger
