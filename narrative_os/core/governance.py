"""
core/governance.py — 阶段一：GovernancePlane（治理平面）

功能：
  - GovernanceHook  枚举（PRE_COMPILE / PRE_RUN / POST_RUN / POST_COMMIT）
  - RunPolicy       运行策略模型
  - GovernanceResult 运行结果模型
  - GovernancePlane  治理平面（注册/触发钩子、加载/保存策略）
  - RunContext       运行上下文（供 orchestrator 注入，记录 Artifact 元数据）

与 orchestrator 集成点：
  PRE_RUN    — 成本预估，超限时中止
  POST_RUN   — 写入 Trace、一致性检查、质量评估；低质量 + HITL 时暂停
  POST_COMMIT — 更新 Metrics History、生成成本摘要
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Awaitable

from pydantic import BaseModel, Field
from sqlalchemy.exc import OperationalError

from narrative_os.infra.database import AsyncSessionLocal, ensure_database_runtime
from narrative_os.infra.models import (
    ApprovalCheckpointRecord,
    ArtifactRecord,
    RunRecord,
    RunStepRecord,
)
from narrative_os.schemas.traces import Artifact, RunStatus, RunType


_SQLITE_LOCK_RETRY_DELAYS = (0.05, 0.1, 0.2, 0.4, 0.8)


def _is_sqlite_lock_error(exc: OperationalError) -> bool:
    return "database is locked" in str(exc).lower()


async def _run_db_operation(operation: Callable[[Any], Awaitable[Any]]) -> Any:
    last_error: OperationalError | None = None
    for delay in (0.0, *_SQLITE_LOCK_RETRY_DELAYS):
        if delay:
            await asyncio.sleep(delay)
        await ensure_database_runtime()
        try:
            async with AsyncSessionLocal() as session:
                return await operation(session)
        except OperationalError as exc:
            if not _is_sqlite_lock_error(exc):
                raise
            last_error = exc
    if last_error is not None:
        raise last_error
    raise RuntimeError("database operation retry loop exited unexpectedly")


# ------------------------------------------------------------------ #
# 枚举                                                                  #
# ------------------------------------------------------------------ #

class GovernanceHook(str, Enum):
    PRE_COMPILE  = "pre_compile"   # 编译前：检查资源/约束
    PRE_RUN      = "pre_run"       # 运行前：成本预算/插件前置
    POST_RUN     = "post_run"      # 运行后：质量评估/一致性检查
    POST_COMMIT  = "post_commit"   # 提交后：追踪记录/版本验证


# ------------------------------------------------------------------ #
# 策略模型                                                              #
# ------------------------------------------------------------------ #

class RunPolicy(BaseModel):
    """项目运行策略。"""
    max_cost_per_chapter_usd: float = 0.5
    require_critic_pass: bool = True
    require_consistency_check: bool = True
    hitl_on_low_quality: bool = False   # 质量分 < quality_threshold 时暂停等待人工确认
    quality_threshold: float = 0.6      # HITL 触发阈值
    style_check_enabled: bool = True
    trace_enabled: bool = True


class GovernanceResult(BaseModel):
    """治理钩子执行结果。"""
    hook: GovernanceHook
    passed: bool = True
    blocked_reason: str | None = None
    warnings: list[str] = Field(default_factory=list)
    hitl_required: bool = False        # 是否需要人工确认（HITL 暂停）


# ------------------------------------------------------------------ #
# HITL 暂停异常                                                         #
# ------------------------------------------------------------------ #

class HITLPauseRequired(Exception):
    """质量分过低，需要人工确认后才能继续。"""
    def __init__(self, quality_score: float, threshold: float) -> None:
        self.quality_score = quality_score
        self.threshold = threshold
        super().__init__(
            f"质量分 {quality_score:.2f} 低于阈值 {threshold:.2f}，需要人工确认（HITL）"
        )


class CostLimitExceeded(Exception):
    """预估成本超出配置上限，流程中止。"""
    def __init__(self, estimated: float, limit: float) -> None:
        self.estimated = estimated
        self.limit = limit
        super().__init__(
            f"预估成本 ${estimated:.4f} 超出限额 ${limit:.2f}，流程中止"
        )


# ------------------------------------------------------------------ #
# GovernancePlane                                                       #
# ------------------------------------------------------------------ #

HandlerFn = Callable[["RunContext"], Awaitable[GovernanceResult] | GovernanceResult]


class GovernancePlane:
    """
    治理平面。

    用法：
        plane = GovernancePlane()
        plane.register_hook(GovernanceHook.PRE_RUN, my_handler)
        result = await plane.run_hooks(GovernanceHook.PRE_RUN, ctx)
    """

    def __init__(self) -> None:
        self._handlers: dict[GovernanceHook, list[HandlerFn]] = {
            h: [] for h in GovernanceHook
        }
        # project_id → RunPolicy（内存缓存）
        self._policies: dict[str, RunPolicy] = {}

    # -------------------------------------------------------------- #
    # 钩子注册 & 触发                                                   #
    # -------------------------------------------------------------- #

    def register_hook(self, hook: GovernanceHook, handler: HandlerFn) -> None:
        """注册一个钩子处理函数（可多次调用，按注册顺序执行）。"""
        self._handlers[hook].append(handler)

    def unregister_hook(self, hook: GovernanceHook, handler: HandlerFn) -> None:
        """移除一个钩子处理函数。"""
        try:
            self._handlers[hook].remove(handler)
        except ValueError:
            pass

    async def run_hooks(
        self,
        hook: GovernanceHook,
        context: "RunContext",
    ) -> GovernanceResult:
        """
        依次执行该 hook 下所有已注册的 handler。
        若某 handler 返回 passed=False，立即中止后续 handler。
        """
        import asyncio
        warnings: list[str] = []
        for handler in self._handlers[hook]:
            raw = handler(context)
            if asyncio.iscoroutine(raw):
                result: GovernanceResult = await raw  # type: ignore[assignment]
            else:
                result = raw  # type: ignore[assignment]
            warnings.extend(result.warnings)
            if not result.passed:
                return GovernanceResult(
                    hook=hook,
                    passed=False,
                    blocked_reason=result.blocked_reason,
                    warnings=warnings,
                    hitl_required=result.hitl_required,
                )
        return GovernanceResult(hook=hook, passed=True, warnings=warnings)

    # -------------------------------------------------------------- #
    # 策略管理                                                          #
    # -------------------------------------------------------------- #

    def load_policy(self, project_id: str) -> RunPolicy:
        """加载项目运行策略（如缓存中无则返回默认策略）。"""
        return self._policies.get(project_id, RunPolicy())

    def save_policy(self, project_id: str, policy: RunPolicy) -> None:
        """保存/更新项目运行策略到内存缓存。"""
        self._policies[project_id] = policy

    # -------------------------------------------------------------- #
    # 内置 PRE_RUN 处理器（成本预估）                                   #
    # -------------------------------------------------------------- #

    def make_cost_guard(self, project_id: str) -> HandlerFn:
        """
        创建成本守卫 handler。
        将此 handler 注册到 PRE_RUN，可在预估成本超出限额时中止流程。
        """
        def _cost_guard(ctx: "RunContext") -> GovernanceResult:
            policy = self.load_policy(project_id)
            estimated = ctx.estimated_cost_usd
            if estimated > policy.max_cost_per_chapter_usd:
                raise CostLimitExceeded(estimated, policy.max_cost_per_chapter_usd)
            warnings = []
            if estimated > policy.max_cost_per_chapter_usd * 0.8:
                warnings.append(
                    f"预估成本 ${estimated:.4f} 接近限额 ${policy.max_cost_per_chapter_usd:.2f}"
                )
            return GovernanceResult(hook=GovernanceHook.PRE_RUN, passed=True, warnings=warnings)
        return _cost_guard  # type: ignore[return-value]

    # -------------------------------------------------------------- #
    # 内置 POST_RUN 处理器（质量评估 + HITL）                           #
    # -------------------------------------------------------------- #

    def make_quality_guard(self, project_id: str) -> HandlerFn:
        """
        创建质量守卫 handler。
        将此 handler 注册到 POST_RUN，可在质量分过低且 hitl_on_low_quality=True 时暂停。
        """
        def _quality_guard(ctx: "RunContext") -> GovernanceResult:
            policy = self.load_policy(project_id)
            score = ctx.quality_score
            if (
                score is not None
                and score < policy.quality_threshold
                and policy.hitl_on_low_quality
            ):
                return GovernanceResult(
                    hook=GovernanceHook.POST_RUN,
                    passed=False,
                    blocked_reason=f"质量分 {score:.2f} 低于阈值 {policy.quality_threshold:.2f}",
                    hitl_required=True,
                )
            return GovernanceResult(hook=GovernanceHook.POST_RUN, passed=True)
        return _quality_guard  # type: ignore[return-value]


# ------------------------------------------------------------------ #
# RunContext                                                            #
# ------------------------------------------------------------------ #

class RunContext:
    """
    运行上下文，贯穿一次章节生成/互动推进的全生命周期。

    orchestrator 在调用 run_chapter() 时创建 RunContext，注入 GovernancePlane，
    并在各钩子触发点传入此 context。

    Agent 可通过 run_context.emit_artifact(artifact) 上报 Artifact（fire-and-forget）。
    """

    def __init__(
        self,
        project_id: str,
        chapter: int = 0,
        plane: GovernancePlane | None = None,
        run_type: RunType = RunType.CHAPTER_GENERATION,
        session_id: str | None = None,
        run_id: str | None = None,
    ) -> None:
        self.project_id = project_id
        self.chapter = chapter
        self.plane = plane or GovernancePlane()
        self.run_type = run_type
        self.session_id = session_id
        self.run_id = run_id or f"run_{uuid.uuid4().hex}"

        # 成本跟踪
        self.estimated_cost_usd: float = 0.0
        self.actual_cost_usd: float = 0.0

        # 质量跟踪
        self.quality_score: float | None = None

        # LLM 调用元数据（最近一次）
        self.last_token_in: int = 0
        self.last_token_out: int = 0
        self.last_latency_ms: int = 0

        # Artifact 列表
        self._artifacts: list[dict[str, Any]] = []
        self._step_ids: dict[str, str] = {}
        self._current_step_by_agent: dict[str, str] = {}
        self._approval_checkpoint_id: str | None = None
        self._pending_tasks: list[asyncio.Task[None]] = []

        # 时间
        self._started_at: float = time.time()

    # -------------------------------------------------------------- #
    # Run/Step 生命周期                                               #
    # -------------------------------------------------------------- #

    async def initialize_run(self) -> None:
        async def _op(session) -> None:
            record = await session.get(RunRecord, self.run_id)
            if record is None:
                session.add(
                    RunRecord(
                        id=self.run_id,
                        project_id=self.project_id,
                        run_type=self.run_type.value,
                        status=RunStatus.RUNNING.value,
                        chapter_num=self.chapter or None,
                        session_id=self.session_id,
                        total_cost_usd=self.actual_cost_usd,
                    )
                )
            await session.commit()

        await _run_db_operation(_op)

    async def begin_step(self, agent_name: str, step_index: int) -> str:
        await self.initialize_run()
        step_id = self._step_ids.get(agent_name)
        now = _utcnow()

        async def _op(session) -> str:
            nonlocal step_id
            if step_id is None:
                step_id = f"step_{uuid.uuid4().hex}"
                self._step_ids[agent_name] = step_id
                session.add(
                    RunStepRecord(
                        id=step_id,
                        run_id=self.run_id,
                        step_index=step_index,
                        agent_name=agent_name,
                        status=RunStatus.RUNNING.value,
                        started_at=now,
                    )
                )
            else:
                record = await session.get(RunStepRecord, step_id)
                if record is not None:
                    record.status = RunStatus.RUNNING.value
                    record.started_at = now
                    record.ended_at = None
            await session.commit()
            return step_id

        step_id = await _run_db_operation(_op)
        self._current_step_by_agent[agent_name] = step_id
        return step_id

    async def complete_step(self, agent_name: str, status: RunStatus = RunStatus.COMPLETED) -> None:
        step_id = self._step_ids.get(agent_name)
        if not step_id:
            return

        async def _op(session) -> None:
            record = await session.get(RunStepRecord, step_id)
            if record is None:
                return
            record.status = status.value
            record.ended_at = _utcnow()
            await session.commit()

        await _run_db_operation(_op)

    async def complete_run(self, status: RunStatus = RunStatus.COMPLETED) -> None:
        await self.flush()

        async def _op(session) -> None:
            record = await session.get(RunRecord, self.run_id)
            if record is None:
                return
            record.status = status.value
            record.total_cost_usd = self.actual_cost_usd
            if status != RunStatus.PAUSED:
                record.ended_at = _utcnow()
            await session.commit()

        await _run_db_operation(_op)

    async def pause_for_hitl(self, reason: str, context: str) -> str:
        await self.flush()
        checkpoint_id = f"checkpoint_{uuid.uuid4().hex}"
        self._approval_checkpoint_id = checkpoint_id

        async def _op(session) -> str:
            session.add(
                ApprovalCheckpointRecord(
                    id=checkpoint_id,
                    run_id=self.run_id,
                    reason=reason,
                    context=context,
                )
            )
            record = await session.get(RunRecord, self.run_id)
            if record is not None:
                record.status = RunStatus.PAUSED.value
            await session.commit()
            return checkpoint_id

        return await _run_db_operation(_op)

    async def resolve_approval(self, decision: str) -> None:

        async def _op(session) -> None:
            checkpoint = None
            if self._approval_checkpoint_id:
                checkpoint = await session.get(ApprovalCheckpointRecord, self._approval_checkpoint_id)
            if checkpoint is None:
                return
            checkpoint.decision = decision
            checkpoint.resolved_at = _utcnow()
            record = await session.get(RunRecord, self.run_id)
            if record is not None:
                record.status = (
                    RunStatus.COMPLETED.value if decision == "approve" else RunStatus.FAILED.value
                )
                if decision != "retry":
                    record.ended_at = _utcnow()
            await session.commit()

            await _run_db_operation(_op)

    async def flush(self) -> None:
        if not self._pending_tasks:
            return
        tasks = [task for task in self._pending_tasks if not task.done()]
        self._pending_tasks = []
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    # -------------------------------------------------------------- #
    # Artifact 上报                                                    #
    # -------------------------------------------------------------- #

    async def emit_artifact(self, artifact: Any) -> None:
        """
        fire-and-forget：将 Artifact 写入内存列表（阶段四会扩展为 DB 写入）。
        不阻塞主流程。
        """
        try:
            if isinstance(artifact, Artifact):
                payload = artifact
            else:
                raw = artifact.model_dump() if hasattr(artifact, "model_dump") else dict(artifact)
                try:
                    payload = Artifact.model_validate(raw)
                except Exception:
                    self._artifacts.append(raw)
                    return

            if not payload.artifact_id:
                payload = payload.model_copy(update={"artifact_id": f"artifact_{uuid.uuid4().hex}"})
            if not payload.run_id:
                payload = payload.model_copy(update={"run_id": self.run_id})
            if not payload.step_id:
                step_id = self._current_step_by_agent.get(payload.agent_name) or self._step_ids.get(payload.agent_name, "")
                payload = payload.model_copy(update={"step_id": step_id})

            data = payload.model_dump(mode="json")
            self._artifacts.append(data)
            task = asyncio.create_task(self._persist_artifact(payload))
            self._pending_tasks.append(task)
        except Exception:
            pass  # 上报失败不影响主流程

    def get_artifacts(self) -> list[dict[str, Any]]:
        """获取当前 RunContext 中全部已上报的 Artifact。"""
        return list(self._artifacts)

    async def _persist_artifact(self, artifact: Artifact) -> None:
        if not artifact.step_id:
            return

        async def _op(session) -> None:
            session.add(
                ArtifactRecord(
                    id=artifact.artifact_id,
                    run_id=artifact.run_id,
                    step_id=artifact.step_id,
                    artifact_type=artifact.artifact_type.value,
                    agent_name=artifact.agent_name,
                    input_summary=artifact.input_summary,
                    output_content=artifact.output_content,
                    quality_scores=json.dumps(artifact.quality_scores, ensure_ascii=False),
                    token_in=artifact.token_in,
                    token_out=artifact.token_out,
                    latency_ms=int(round(artifact.latency_ms)),
                    retry_count=artifact.retry_count,
                    retry_reason=artifact.retry_reason,
                )
            )
            await session.commit()

        await _run_db_operation(_op)

    # -------------------------------------------------------------- #
    # 治理钩子触发                                                      #
    # -------------------------------------------------------------- #

    async def trigger(self, hook: GovernanceHook) -> GovernanceResult:
        """触发指定治理钩子，返回聚合结果。"""
        return await self.plane.run_hooks(hook, self)

    # -------------------------------------------------------------- #
    # 便捷属性                                                          #
    # -------------------------------------------------------------- #

    @property
    def elapsed_seconds(self) -> float:
        return time.time() - self._started_at


# ------------------------------------------------------------------ #
# 全局单例（每个项目一个治理平面实例）                                   #
# ------------------------------------------------------------------ #

_governance_planes: dict[str, GovernancePlane] = {}


def get_governance_plane(project_id: str) -> GovernancePlane:
    """获取（或创建）指定项目的 GovernancePlane 单例。"""
    if project_id not in _governance_planes:
        _governance_planes[project_id] = GovernancePlane()
    return _governance_planes[project_id]


def create_run_context(
    project_id: str,
    chapter: int = 0,
    estimated_cost_usd: float = 0.0,
    run_type: RunType = RunType.CHAPTER_GENERATION,
    session_id: str | None = None,
) -> RunContext:
    """工厂函数：创建与指定项目绑定的 RunContext。"""
    plane = get_governance_plane(project_id)
    ctx = RunContext(
        project_id=project_id,
        chapter=chapter,
        plane=plane,
        run_type=run_type,
        session_id=session_id,
    )
    ctx.estimated_cost_usd = estimated_cost_usd
    return ctx


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)
