"""
infra/hitl.py — Phase 2 (Human-in-the-Loop): Approval Gate

设计目标：
  - 在 Orchestrator 流水线的关键节点暂停，等待用户审批/修改
  - 支持阻塞（await checkpoint()）和非阻塞（回调通知）两种模式
  - timeout 到期时自动以 APPROVED 状态继续（可配置）
  - 线程安全，asyncio 原生

典型用法（阻塞）：
    mgr = HITLManager.instance()

    # 在 planner_node 完成后暂停
    resp = await mgr.checkpoint(
        gate_type="planner_output",
        payload=output.model_dump(),
        description="第3章骨架已生成，请审阅",
    )
    if resp.status == ApprovalStatus.MODIFIED:
        output = PlannerOutput(**resp.modified_payload)
    elif resp.status == ApprovalStatus.REJECTED:
        raise RuntimeError("用户拒绝了骨架方案")

人机协同（非阻塞）：
    mgr.register_handler("planner_output", my_notification_fn)  # 触发后台通知
    # my_notification_fn(request: ApprovalRequest) → None（异步发送消息到 UI）
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable, Coroutine
from datetime import datetime, timezone
from enum import Enum
from typing import Any, ClassVar

from pydantic import BaseModel, Field

from narrative_os.infra.logging import logger


# ------------------------------------------------------------------ #
# 枚举 & 数据模型                                                        #
# ------------------------------------------------------------------ #

class ApprovalStatus(str, Enum):
    PENDING  = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    MODIFIED = "modified"
    TIMEOUT  = "timeout"


class ApprovalRequest(BaseModel):
    """checkpoint() 发起的审批请求。"""
    gate_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    gate_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    description: str = ""
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    timeout: float = 300.0    # 秒，0 = 永不超时


class ApprovalResponse(BaseModel):
    """审批结果。"""
    gate_id: str
    status: ApprovalStatus
    modified_payload: dict[str, Any] | None = None
    comment: str = ""
    resolved_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# ------------------------------------------------------------------ #
# HITLManager                                                           #
# ------------------------------------------------------------------ #

_Handler = Callable[["ApprovalRequest"], Coroutine | None]


class HITLManager:
    """
    进程级单例 HITL 管理器。

    线程/协程安全：每个 pending gate 持有一个 asyncio.Event，
    resolve/approve/reject 触发 Event，checkpoint() await 返回。
    """

    _instance: ClassVar["HITLManager | None"] = None

    def __init__(self) -> None:
        # gate_id  →  (ApprovalRequest, asyncio.Event, ApprovalResponse | None)
        self._pending: dict[str, tuple[ApprovalRequest, asyncio.Event, list]] = {}
        self._handlers: dict[str, list[_Handler]] = {}  # gate_type → [handlers]

    @classmethod
    def instance(cls) -> "HITLManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ---------------------------------------------------------------- #
    # 主接口                                                              #
    # ---------------------------------------------------------------- #

    async def checkpoint(
        self,
        gate_type: str,
        payload: dict[str, Any],
        description: str = "",
        *,
        timeout: float = 300.0,
    ) -> ApprovalResponse:
        """
        阻塞直到用户 approve / reject / modify 或 timeout。

        timeout=0 → 永不超时（等待系统调用 approve/reject）。
        timeout > 0 → 到期返回 TIMEOUT 状态（相当于自动 APPROVED）。
        """
        req = ApprovalRequest(
            gate_type=gate_type,
            payload=payload,
            description=description,
            timeout=timeout,
        )
        event = asyncio.Event()
        result_holder: list[ApprovalResponse] = []
        self._pending[req.gate_id] = (req, event, result_holder)

        logger.info(
            "hitl_checkpoint",
            gate_id=req.gate_id,
            gate_type=gate_type,
            description=description,
        )

        # 触发已注册的通知回调（非阻塞）
        await self._notify_handlers(gate_type, req)

        try:
            if timeout > 0:
                try:
                    await asyncio.wait_for(asyncio.shield(event.wait()), timeout=timeout)
                except asyncio.TimeoutError:
                    resp = ApprovalResponse(
                        gate_id=req.gate_id,
                        status=ApprovalStatus.TIMEOUT,
                        comment="自动超时批准",
                    )
                    self._pending.pop(req.gate_id, None)
                    logger.warn(
                        "hitl_timeout",
                        gate_id=req.gate_id,
                        gate_type=gate_type,
                    )
                    return resp
            else:
                await event.wait()
        finally:
            self._pending.pop(req.gate_id, None)

        return result_holder[0] if result_holder else ApprovalResponse(
            gate_id=req.gate_id,
            status=ApprovalStatus.APPROVED,
        )

    # ---------------------------------------------------------------- #
    # 审批操作（从外部触发，如 CLI / API / UI）                              #
    # ---------------------------------------------------------------- #

    def approve(
        self,
        gate_id: str,
        *,
        modified_payload: dict[str, Any] | None = None,
        comment: str = "",
    ) -> bool:
        """
        批准请求。modified_payload 不为 None 时状态变为 MODIFIED。
        返回 True 表示成功，False 表示 gate_id 不存在。
        """
        status = (
            ApprovalStatus.MODIFIED if modified_payload is not None
            else ApprovalStatus.APPROVED
        )
        return self.resolve(gate_id, status=status,
                            modified_payload=modified_payload, comment=comment)

    def reject(self, gate_id: str, *, comment: str = "") -> bool:
        """拒绝请求。"""
        return self.resolve(gate_id, status=ApprovalStatus.REJECTED, comment=comment)

    def resolve(
        self,
        gate_id: str,
        *,
        status: ApprovalStatus,
        modified_payload: dict[str, Any] | None = None,
        comment: str = "",
    ) -> bool:
        """通用 resolve，触发等待端的 Event。"""
        entry = self._pending.get(gate_id)
        if entry is None:
            return False
        req, event, holder = entry
        resp = ApprovalResponse(
            gate_id=gate_id,
            status=status,
            modified_payload=modified_payload,
            comment=comment,
        )
        holder.append(resp)
        event.set()
        logger.info("hitl_resolved", gate_id=gate_id, status=status.value)
        return True

    # ---------------------------------------------------------------- #
    # 查询                                                                #
    # ---------------------------------------------------------------- #

    def list_pending(self) -> list[ApprovalRequest]:
        """返回当前所有挂起的审批请求（快照）。"""
        return [req for req, _, _ in self._pending.values()]

    def is_pending(self, gate_id: str) -> bool:
        return gate_id in self._pending

    # ---------------------------------------------------------------- #
    # 回调注册                                                             #
    # ---------------------------------------------------------------- #

    def register_handler(self, gate_type: str, handler: _Handler) -> None:
        """
        注册通知回调。handler(req) 在 checkpoint() 发起后立即被调用（非阻塞）。
        同一 gate_type 可注册多个 handler。
        """
        self._handlers.setdefault(gate_type, []).append(handler)

    def unregister_handler(self, gate_type: str) -> None:
        """移除某 gate_type 的所有 handler。"""
        self._handlers.pop(gate_type, None)

    # ---------------------------------------------------------------- #
    # 内部                                                                #
    # ---------------------------------------------------------------- #

    async def _notify_handlers(
        self, gate_type: str, req: ApprovalRequest
    ) -> None:
        handlers = self._handlers.get(gate_type, [])
        for h in handlers:
            try:
                result = h(req)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as exc:
                logger.warn("hitl_handler_error", gate_type=gate_type, error=str(exc))
