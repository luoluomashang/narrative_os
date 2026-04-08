"""
skills/dsl.py — Phase 1: SkillDSL（统一调用协议）

所有生成任务必须通过 SkillDSL 调用，杜绝直接调用 LLM。

核心组件：
  SkillRequest   — 输入协议（skill名/输入参数/约束/输出格式）
  SkillResponse  — 输出协议（状态/输出/token消耗/延迟/错误）
  SkillRegistry  — 全局注册表（单例）
  skill()        — 注册装饰器

UI 映射：技能积木库（无代码拖拽 / 结构化表单）
"""

from __future__ import annotations

import functools
import time
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field


# ------------------------------------------------------------------ #
# SkillRequest / SkillResponse                                          #
# ------------------------------------------------------------------ #

class SkillRequest(BaseModel):
    """
    统一调用协议 — 输入。

    constraints: 来自 methodology.yaml 8大法则 / writing_rules.yaml 的硬约束列表
    output_format: 期望输出格式（{"type": "text", "min_length": 1500} 等）
    """
    skill: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    constraints: list[str] = Field(default_factory=list)
    output_format: dict[str, Any] = Field(default_factory=dict)
    agent: str | None = None
    chapter: int | None = None

    model_config = {"frozen": True}


class SkillResponse(BaseModel):
    """统一调用协议 — 输出。"""
    skill: str
    status: str  # "success" | "failed" | "partial"
    output: Any = None
    token_usage: dict[str, int] = Field(default_factory=dict)  # {prompt: N, completion: N}
    latency_ms: float = 0.0
    errors: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def success(self) -> bool:
        return self.status == "success"

    @property
    def total_tokens(self) -> int:
        return self.token_usage.get("prompt", 0) + self.token_usage.get("completion", 0)


# ------------------------------------------------------------------ #
# SkillRegistry                                                         #
# ------------------------------------------------------------------ #

class SkillRegistry:
    """
    全局 Skill 注册表（进程级单例）。

    使用方式：
        registry = SkillRegistry.instance()

        # 注册
        @registry.register("generate_scene")
        def handle_scene(req: SkillRequest) -> SkillResponse: ...

        # 调用
        resp = registry.execute(SkillRequest(skill="generate_scene", inputs={...}))
    """

    _instance: "SkillRegistry | None" = None

    def __init__(self) -> None:
        self._handlers: dict[str, Callable[[SkillRequest], SkillResponse]] = {}
        self._meta: dict[str, dict[str, Any]] = {}

    @classmethod
    def instance(cls) -> "SkillRegistry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ---------------------------------------------------------------- #
    # Registration                                                       #
    # ---------------------------------------------------------------- #

    def register(
        self,
        name: str,
        *,
        description: str = "",
        input_schema: dict[str, Any] | None = None,
        output_schema: dict[str, Any] | None = None,
    ) -> Callable:
        """
        装饰器：将函数注册为 Skill handler。

        @registry.register("generate_scene", description="生成场景文本")
        def handle(req: SkillRequest) -> SkillResponse: ...
        """
        def decorator(fn: Callable[[SkillRequest], SkillResponse]) -> Callable:
            if name in self._handlers:
                raise ValueError(f"Skill '{name}' 已注册，不允许重复注册。如需覆盖请先 unregister()。")
            self._handlers[name] = fn
            self._meta[name] = {
                "description": description,
                "input_schema": input_schema or {},
                "output_schema": output_schema or {},
            }
            return fn
        return decorator

    def register_fn(
        self,
        name: str,
        handler: Callable[[SkillRequest], SkillResponse],
        **meta: Any,
    ) -> None:
        """直接注册（非装饰器形式）。"""
        self._handlers[name] = handler
        self._meta[name] = meta

    def unregister(self, name: str) -> None:
        self._handlers.pop(name, None)
        self._meta.pop(name, None)

    # ---------------------------------------------------------------- #
    # Execution                                                          #
    # ---------------------------------------------------------------- #

    def execute(self, request: SkillRequest) -> SkillResponse:
        """
        执行 Skill 调用。
        - 校验 skill 是否已注册
        - 记录执行时间
        - 捕获异常并返回 failed SkillResponse
        """
        if request.skill not in self._handlers:
            return SkillResponse(
                skill=request.skill,
                status="failed",
                errors=[f"Skill '{request.skill}' 未注册。已注册: {list(self._handlers)}"],
            )

        handler = self._handlers[request.skill]
        t0 = time.perf_counter()
        try:
            response = handler(request)
            elapsed = (time.perf_counter() - t0) * 1000
            # 确保 latency_ms 被填充
            return response.model_copy(update={"latency_ms": elapsed})
        except Exception as exc:
            elapsed = (time.perf_counter() - t0) * 1000
            return SkillResponse(
                skill=request.skill,
                status="failed",
                latency_ms=elapsed,
                errors=[f"{type(exc).__name__}: {exc}"],
            )

    async def execute_async(self, request: SkillRequest) -> SkillResponse:
        """异步版本（Phase 2 LLM Router 集成后主要使用此方法）。"""
        import asyncio
        handler = self._handlers.get(request.skill)
        if handler is None:
            return SkillResponse(
                skill=request.skill,
                status="failed",
                errors=[f"Skill '{request.skill}' 未注册"],
            )
        t0 = time.perf_counter()
        try:
            if asyncio.iscoroutinefunction(handler):
                response = await handler(request)
            else:
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(None, handler, request)
            elapsed = (time.perf_counter() - t0) * 1000
            return response.model_copy(update={"latency_ms": elapsed})
        except Exception as exc:
            elapsed = (time.perf_counter() - t0) * 1000
            return SkillResponse(
                skill=request.skill,
                status="failed",
                latency_ms=elapsed,
                errors=[f"{type(exc).__name__}: {exc}"],
            )

    # ---------------------------------------------------------------- #
    # Introspection                                                       #
    # ---------------------------------------------------------------- #

    def list_skills(self) -> list[str]:
        return list(self._handlers.keys())

    def get_meta(self, name: str) -> dict[str, Any]:
        return self._meta.get(name, {})

    def __repr__(self) -> str:
        return f"SkillRegistry(skills={self.list_skills()})"


# ------------------------------------------------------------------ #
# Module-level registry singleton                                       #
# ------------------------------------------------------------------ #

registry = SkillRegistry.instance()


def skill(
    name: str,
    *,
    description: str = "",
    input_schema: dict[str, Any] | None = None,
    output_schema: dict[str, Any] | None = None,
) -> Callable:
    """
    模块级装饰器，直接注册到全局 registry。

    使用方式：
        from narrative_os.skills.dsl import skill

        @skill("generate_scene", description="生成场景文本")
        def handle(req: SkillRequest) -> SkillResponse:
            ...
    """
    return registry.register(
        name,
        description=description,
        input_schema=input_schema,
        output_schema=output_schema,
    )
