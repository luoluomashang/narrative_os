"""services/trpg_service.py — TRPG 会话应用服务（DB 持久化，解决双轨问题）。"""
from __future__ import annotations

import json
import time
import threading
from threading import Lock
from typing import Any

from fastapi import HTTPException, status

from narrative_os.agents.interactive import InteractiveSession
from narrative_os.infra.database import AsyncSessionLocal, fire_and_forget
from narrative_os.infra.models import TrpgSession as TrpgSessionModel


# ------------------------------------------------------------------ #
# 模块级状态（从 api.py 迁移）                                          #
# ------------------------------------------------------------------ #

_sessions: dict[str, tuple[InteractiveSession, float]] = {}
_sessions_lock = Lock()
SESSION_TTL_SECONDS = 3600

_interactive_agent: Any | None = None


def get_interactive_agent():
    global _interactive_agent
    if _interactive_agent is None:
        from narrative_os.agents.interactive import InteractiveAgent

        _interactive_agent = InteractiveAgent()
    return _interactive_agent


# ------------------------------------------------------------------ #
# TrpgService                                                          #
# ------------------------------------------------------------------ #

class TrpgService:
    """TRPG 会话管理服务：内存缓存 + DB 持久化双保险。"""

    def get_session(self, session_id: str) -> InteractiveSession:
        """获取会话：先查内存，再查 DB 重建。"""
        with _sessions_lock:
            entry = _sessions.get(session_id)
        if entry is not None:
            session, _ = entry
            with _sessions_lock:
                _sessions[session_id] = (session, time.time())
            return session
        # 尝试从 DB 重建
        return self._reconstruct_from_db_sync(session_id)

    def _reconstruct_from_db_sync(self, session_id: str) -> InteractiveSession:
        """同步版本：从 DB 重建 InteractiveSession（供启动时恢复）。"""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 在事件循环中无法同步等待，抛出 404
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={"detail": f"会话 '{session_id}' 不存在。", "code": "NOT_FOUND"},
                )
            return loop.run_until_complete(self._load_session_from_db(session_id))
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"detail": f"会话 '{session_id}' 不存在。", "code": "NOT_FOUND"},
            )

    async def load_session_async(self, session_id: str) -> InteractiveSession:
        """异步版本：先查内存，再查 DB 重建。供路由层使用。"""
        with _sessions_lock:
            entry = _sessions.get(session_id)
        if entry is not None:
            session, _ = entry
            with _sessions_lock:
                _sessions[session_id] = (session, time.time())
            return session
        return await self._load_session_from_db(session_id)

    async def _load_session_from_db(self, session_id: str) -> InteractiveSession:
        try:
            async with AsyncSessionLocal() as db:
                row = await db.get(TrpgSessionModel, session_id)
                if row is None or row.phase == "ENDED":
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail={"detail": f"会话 '{session_id}' 不存在。", "code": "NOT_FOUND"},
                    )
                # history_json stores full InteractiveSession JSON (after Phase 2)
                history_data = row.history_json
                if history_data and history_data != "[]" and history_data.startswith("{"):
                    # Full session JSON stored
                    session = InteractiveSession.model_validate_json(history_data)
                    with _sessions_lock:
                        _sessions[session_id] = (session, time.time())
                    return session
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={"detail": f"会话 '{session_id}' 状态无法恢复（进程已重启）。", "code": "NOT_FOUND"},
                )
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"detail": f"会话 '{session_id}' 不存在。", "code": "NOT_FOUND"},
            )

    def put_session(self, session: InteractiveSession) -> None:
        """放入内存缓存并异步持久化到 DB。"""
        with _sessions_lock:
            _sessions[session.session_id] = (session, time.time())
        fire_and_forget(self._persist_session(session))

    async def _persist_session(self, session: InteractiveSession) -> None:
        """将完整 InteractiveSession 序列化到 DB history_json 字段。"""
        try:
            async with AsyncSessionLocal() as db:
                row = await db.get(TrpgSessionModel, session.session_id)
                if row is not None:
                    # 存储完整 session JSON 以支持跨进程恢复 (2.C)
                    row.history_json = session.model_dump_json()
                    row.phase = session.phase.value
                    row.turn_count = session.turn
                    row.scene_pressure = session.scene_pressure
                    row.emotional_temp_json = json.dumps(
                        session.emotional_temperature
                        if isinstance(session.emotional_temperature, dict)
                        else {"current": session.emotional_temperature},
                        ensure_ascii=False,
                    )
                    await db.commit()
        except Exception:
            pass

    def remove_session(self, session_id: str) -> None:
        with _sessions_lock:
            _sessions.pop(session_id, None)

    def cleanup_stale(self) -> None:
        cutoff = time.time() - SESSION_TTL_SECONDS
        with _sessions_lock:
            expired = [sid for sid, (_, ts) in _sessions.items() if ts < cutoff]
            for sid in expired:
                del _sessions[sid]


# ------------------------------------------------------------------ #
# 全局单例 + 后台清理线程                                               #
# ------------------------------------------------------------------ #

_trpg_service: TrpgService | None = None


def get_trpg_service() -> TrpgService:
    global _trpg_service
    if _trpg_service is None:
        _trpg_service = TrpgService()
    return _trpg_service


def _cleanup_loop() -> None:
    while True:
        time.sleep(600)
        try:
            get_trpg_service().cleanup_stale()
        except Exception:
            pass


_cleanup_thread = threading.Thread(target=_cleanup_loop, daemon=True)
_cleanup_thread.start()


# ------------------------------------------------------------------ #
# 向后兼容的模块级函数（api.py 重构前旧测试使用）                        #
# ------------------------------------------------------------------ #


def _cleanup_stale_sessions() -> None:
    """删除过期的 TRPG 会话（向后兼容别名）。"""
    get_trpg_service().cleanup_stale()


def _get_session(session_id: str) -> InteractiveSession:
    """获取会话，不存在时抛出 404（向后兼容同步别名）。"""
    with _sessions_lock:
        entry = _sessions.get(session_id)
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"detail": f"会话 '{session_id}' 不存在。", "code": "NOT_FOUND"},
        )
    session, _ = entry
    with _sessions_lock:
        _sessions[session_id] = (session, time.time())
    return session
