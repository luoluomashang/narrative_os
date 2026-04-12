"""routers/trpg.py — TRPG 会话路由模块（REST + WebSocket）。"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status

from narrative_os.schemas.trpg import (
    CreateSessionRequest,
    CreateSessionResponse,
    SessionStepRequest,
    InterruptRequest,
    RollbackRequest,
    SessionStatusResponse,
    SessionSummary,
    TurnRecordResponse,
    SaveRequest,
    SavePoint,
    ControlModeRequest,
    ControlModeResponse,
    AgendaResponse,
    SessionCommitRequest,
    SessionCommitResponse,
)
from narrative_os.interface.services.trpg_service import TrpgService, get_trpg_service

router = APIRouter(tags=["trpg"])


def _svc() -> TrpgService:
    return get_trpg_service()


# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #


def _to_turn_response(session: Any) -> TurnRecordResponse:
    """从 session 最新 DM Turn 构建响应。"""
    dm_turns = [t for t in session.history if t.who == "dm"]
    if not dm_turns:
        return TurnRecordResponse(
            turn_id=0, who="system", content="", scene_pressure=5.0,
            density="normal", phase=session.phase.value, has_decision=False,
        )
    last = dm_turns[-1]
    options = last.decision.options if last.decision else []
    return TurnRecordResponse(
        turn_id=last.turn_id,
        who=last.who,
        content=last.content,
        scene_pressure=last.scene_pressure,
        density=last.density,
        phase=last.phase.value,
        has_decision=last.decision is not None and not last.decision.is_free_action,
        decision_options=options,
    )


# ------------------------------------------------------------------ #
# TRPG REST 端点                                                        #
# ------------------------------------------------------------------ #


def _get_agent():
    """Get the InteractiveAgent, checking api-level namespace first for mocking."""
    import sys
    _api = sys.modules.get("narrative_os.interface.api")
    if _api is not None and hasattr(_api, "_interactive_agent"):
        return _api._interactive_agent
    from narrative_os.interface.services.trpg_service import _interactive_agent
    return _interactive_agent


@router.post("/sessions/create", response_model=CreateSessionResponse, status_code=status.HTTP_201_CREATED, summary="创建 TRPG 会话")
async def create_session(
    req: CreateSessionRequest, svc: TrpgService = Depends(_svc)
) -> CreateSessionResponse:
    from narrative_os.agents.interactive import SessionConfig

    cfg = SessionConfig(
        project_id=req.project_id,
        character_name=req.character_name,
        density_override=req.density,
        opening_prompt=req.opening_prompt,
        world_summary=req.world_summary,
        max_history_turns=req.max_history_turns,
    )
    agent = _get_agent()
    session = agent.create_session(cfg)

    try:
        opening_turn = await agent.start(session)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"detail": f"会话启动失败：{exc}", "code": "INTERNAL_ERROR"},
        )

    svc.put_session(session)
    return CreateSessionResponse(
        session_id=session.session_id,
        phase=session.phase.value,
        density=session.density,
        scene_pressure=session.scene_pressure,
        opening_turn=_to_turn_response(session),
    )


@router.post("/sessions/{session_id}/step", summary="玩家行动推进一步")
async def session_step(
    session_id: str,
    req: SessionStepRequest,
    svc: TrpgService = Depends(_svc),
) -> TurnRecordResponse:
    from narrative_os.agents.interactive import SessionPhase
    session = await svc.load_session_async(session_id)
    if session.phase not in {SessionPhase.PING_PONG, SessionPhase.PACING_ALERT}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"detail": f"当前阶段 {session.phase} 不接受 step 操作。", "code": "INVALID_PHASE"},
        )
    try:
        await _get_agent().step(session, req.user_input)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"detail": str(exc), "code": "INTERNAL_ERROR"},
        )
    svc.put_session(session)
    return _to_turn_response(session)


@router.post("/sessions/{session_id}/interrupt", summary="发送帮回指令")
async def session_interrupt(
    session_id: str,
    req: InterruptRequest,
    svc: TrpgService = Depends(_svc),
) -> TurnRecordResponse:
    session = await svc.load_session_async(session_id)
    try:
        await _get_agent().interrupt(session, req.bangui_command)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"detail": str(exc), "code": "INTERNAL_ERROR"},
        )
    svc.put_session(session)
    return _to_turn_response(session)


@router.post("/sessions/{session_id}/rollback", summary="回滚 N 步")
async def session_rollback(
    session_id: str,
    req: RollbackRequest,
    svc: TrpgService = Depends(_svc),
) -> SessionStatusResponse:
    session = await svc.load_session_async(session_id)
    _get_agent().rollback(session, steps=req.steps)
    svc.put_session(session)
    return SessionStatusResponse(
        session_id=session.session_id,
        project_id=session.project_id,
        phase=session.phase.value,
        turn=session.turn,
        scene_pressure=session.scene_pressure,
        density=session.density,
        history_count=len(session.history),
        emotional_temperature=session.emotional_temperature,
        turn_char_count=session.turn_char_count,
    )


@router.get("/sessions/{session_id}/status", response_model=SessionStatusResponse, summary="查看会话状态")
async def session_status(
    session_id: str, svc: TrpgService = Depends(_svc)
) -> SessionStatusResponse:
    session = await svc.load_session_async(session_id)
    return SessionStatusResponse(
        session_id=session.session_id,
        project_id=session.project_id,
        phase=session.phase.value,
        turn=session.turn,
        scene_pressure=session.scene_pressure,
        density=session.density,
        history_count=len(session.history),
        emotional_temperature=session.emotional_temperature,
        turn_char_count=session.turn_char_count,
    )


@router.post("/sessions/{session_id}/end", response_model=SessionSummary, summary="结束 TRPG 会话")
async def session_end(
    session_id: str, svc: TrpgService = Depends(_svc)
) -> SessionSummary:
    import sys
    from narrative_os.core.state import StateManager as _CoreStateManager
    from narrative_os.core.state import ChapterMeta
    _api = sys.modules.get("narrative_os.interface.api")
    StateManager = getattr(_api, "StateManager", _CoreStateManager) if _api else _CoreStateManager
    session = await svc.load_session_async(session_id)
    result = _get_agent().land(session)

    chapter_text = result.get("chapter_text", "")
    saved_chapter: int | None = None
    if chapter_text:
        try:
            from narrative_os.infra.logging import logger
            state_mgr = StateManager(project_id=session.project_id, base_dir=".narrative_state")
            try:
                state_mgr.load_state()
            except FileNotFoundError:
                state_mgr.initialize(project_name=session.project_id)
            new_ch = state_mgr.state.current_chapter + 1
            state_mgr.save_chapter_text(new_ch, chapter_text)
            chapter_meta = ChapterMeta(
                chapter=new_ch,
                summary=result.get("history_summary", "")[:200],
                quality_score=0.0,
                hook_score=0.0,
                word_count=result.get("word_count", len(chapter_text)),
            )
            kb = state_mgr.load_kb()
            state_mgr.commit_chapter(
                new_ch,
                plot_graph_dict=kb.get("plot_graph") if isinstance(kb, dict) else None,
                characters_dict=kb.get("characters") if isinstance(kb, dict) else None,
                world_dict=kb.get("world") if isinstance(kb, dict) else None,
                chapter_meta=chapter_meta,
            )
            hook_text = result.get("hook", "")
            if hook_text:
                kb2 = state_mgr.load_kb() or {}
                kb2["last_hook"] = hook_text
                state_mgr.save_kb(kb2)
            saved_chapter = new_ch
        except Exception as _e:
            logger.warn(
                "trpg_chapter_persist_nonfatal_failed",
                project_id=session.project_id,
                session_id=session_id,
                error=str(_e),
            )

    svc.remove_session(session_id)
    return SessionSummary(
        duration_minutes=0,
        turn_count=result.get("turns", 0),
        word_count=result.get("word_count", 0),
        bangui_count=0,
        key_decisions=[],
        next_hook=result.get("hook", result.get("history_summary", "")),
        character_delta=result.get("character_deltas", []),
        saved_chapter=saved_chapter,
    )


# ------------------------------------------------------------------ #
# SL 存档                                                              #
# ------------------------------------------------------------------ #


@router.post(
    "/projects/{project_id}/sessions/{session_id}/save",
    status_code=status.HTTP_201_CREATED,
    summary="手动存档",
)
async def create_save(
    project_id: str,
    session_id: str,
    req: SaveRequest,
    svc: TrpgService = Depends(_svc),
) -> SavePoint:
    from narrative_os.core.save_load import get_save_store
    session = await svc.load_session_async(session_id)
    store = get_save_store(session_id)
    sp = store.create(session=session, trigger=req.trigger, memory_summary=session.memory_summary_cache)
    return SavePoint(
        save_id=sp.save_id,
        trigger=sp.trigger,
        timestamp=sp.timestamp,
        turn=sp.turn,
        scene_pressure=getattr(sp, "scene_pressure", None),
    )


@router.get("/projects/{project_id}/sessions/{session_id}/saves", response_model=list[SavePoint], summary="列出存档点")
async def list_saves(
    project_id: str, session_id: str, svc: TrpgService = Depends(_svc)
) -> list[SavePoint]:
    from narrative_os.core.save_load import get_save_store
    await svc.load_session_async(session_id)  # 验证会话存在
    store = get_save_store(session_id)
    saves = store.list_saves(session_id)
    return [
        SavePoint(
            save_id=s.save_id,
            trigger=s.trigger,
            timestamp=s.timestamp,
            turn=s.turn,
            scene_pressure=s.scene_pressure,
        )
        for s in saves
    ]


@router.post("/projects/{project_id}/sessions/{session_id}/load/{save_id}", summary="读档")
async def load_save(
    project_id: str, session_id: str, save_id: str, svc: TrpgService = Depends(_svc)
) -> dict[str, Any]:
    from narrative_os.core.save_load import SoftRollback, get_save_store
    session = await svc.load_session_async(session_id)
    store = get_save_store(session_id)
    sp = store.get(save_id)
    if sp is None:
        raise HTTPException(status_code=404, detail=f"存档 '{save_id}' 不存在")
    SoftRollback().restore(session, sp)
    svc.put_session(session)
    return {
        "save_id": save_id,
        "restored_turn": session.turn,
        "memory_summary_preserved": bool(session.memory_summary_cache),
    }


@router.delete(
    "/projects/{project_id}/sessions/{session_id}/saves/{save_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除存档",
)
async def delete_save(
    project_id: str, session_id: str, save_id: str, svc: TrpgService = Depends(_svc)
) -> None:
    from narrative_os.core.save_load import get_save_store
    await svc.load_session_async(session_id)
    store = get_save_store(session_id)
    store.delete(save_id)


# ------------------------------------------------------------------ #
# 控制权模式 + Agenda                                                   #
# ------------------------------------------------------------------ #


@router.post("/projects/{project_id}/sessions/{session_id}/control-mode", response_model=ControlModeResponse, summary="切换控制权模式")
async def set_control_mode(
    project_id: str,
    session_id: str,
    req: ControlModeRequest,
    svc: TrpgService = Depends(_svc),
) -> ControlModeResponse:
    from narrative_os.core.interactive_modes import ControlMode, ControlModeConfig
    session = await svc.load_session_async(session_id)
    try:
        new_mode = ControlMode(req.mode)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"未知控制模式: {req.mode}")
    session.control_mode = new_mode
    session.mode_config = ControlModeConfig(
        mode=new_mode,
        ai_controlled_characters=req.ai_controlled_characters,
        allow_protagonist_proxy=req.allow_protagonist_proxy,
        director_intervention_enabled=req.director_intervention_enabled,
    )
    svc.put_session(session)
    return ControlModeResponse(
        session_id=session_id,
        mode=new_mode.value,
        prompt_hint=session.mode_config.prompt_hint,
    )


@router.get("/projects/{project_id}/sessions/{session_id}/agenda", response_model=AgendaResponse, summary="查看 Agenda 状态")
async def get_session_agenda(
    project_id: str, session_id: str, svc: TrpgService = Depends(_svc)
) -> AgendaResponse:
    session = await svc.load_session_async(session_id)
    return AgendaResponse(session_id=session_id, turn=session.turn, agenda=session.last_agenda)


# ------------------------------------------------------------------ #
# ChangeSet / Canon Commit (Phase 4 + Phase 1)                         #
# ------------------------------------------------------------------ #


@router.post(
    "/projects/{project_id}/sessions/{session_id}/commit",
    status_code=status.HTTP_201_CREATED,
    summary="互动结束后选择提交方式",
)
async def commit_session(
    project_id: str,
    session_id: str,
    req: SessionCommitRequest,
    svc: TrpgService = Depends(_svc),
) -> SessionCommitResponse:
    from narrative_os.core.evolution import SessionCommitMode, get_canon_commit
    await svc.load_session_async(session_id)  # 验证会话存在
    _mode_str = req.mode or req.commit_type
    try:
        mode = SessionCommitMode(_mode_str)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"未知提交模式: {_mode_str}")
    cc = get_canon_commit(project_id)
    cs = cc.commit_session(
        project_id=project_id,
        session_id=session_id,
        mode=mode,
        draft_content=req.draft_content,
        require_canon_confirm=req.require_canon_confirm,
    )
    return SessionCommitResponse(
        changeset_id=cs.changeset_id,
        commit_mode=cs.commit_mode.value,
        changes_count=len(cs.changes),
        canon_confirmed=cs.canon_confirmed,
    )


# ------------------------------------------------------------------ #
# WebSocket 端点                                                        #
# ------------------------------------------------------------------ #


@router.websocket("/ws/sessions/{session_id}")
async def ws_session(
    websocket: WebSocket,
    session_id: str,
    svc: TrpgService = Depends(_svc),
) -> None:
    """WebSocket 流式叙事端点。"""
    await websocket.accept()
    try:
        from narrative_os.agents.interactive import SessionPhase

        try:
            session = await svc.load_session_async(session_id)
        except HTTPException:
            await websocket.send_json({"type": "error", "message": f"会话 '{session_id}' 不存在"})
            await websocket.close(code=4004)
            return

        agent = _get_agent()

        while True:
            try:
                data = await websocket.receive_json()
            except WebSocketDisconnect:
                break

            user_action = data.get("action", "").strip()
            density_override = data.get("density", None)
            if not user_action:
                await websocket.send_json({"type": "error", "message": "action 不能为空"})
                continue

            if session.phase not in {SessionPhase.PING_PONG, SessionPhase.PACING_ALERT}:
                await websocket.send_json({"type": "error", "message": f"当前阶段 {session.phase} 不接受行动"})
                continue

            prev_phase = session.phase
            prev_density = session.density
            if density_override in ("dense", "normal", "sparse"):
                session.density = density_override
                session.config.density_override = density_override

            try:
                await agent.step(session, user_action)
            except Exception as exc:
                await websocket.send_json({"type": "error", "message": str(exc)})
                continue

            svc.put_session(session)
            dm_turns = [t for t in session.history if t.who == "dm"]
            if dm_turns:
                last_turn = dm_turns[-1]
                if session.phase != prev_phase:
                    await websocket.send_json({"type": "phase_change", "phase": session.phase.value})
                if session.density != prev_density:
                    await websocket.send_json({"type": "density_change", "density": session.density})
                if session.phase.value == "PACING_ALERT":
                    await websocket.send_json({
                        "type": "pacing_alert",
                        "chars_so_far": session.turn_char_count,
                        "reason": last_turn.metadata.get("pacing_alert_reason", ""),
                    })
                if "agency_violation_warning" in last_turn.metadata:
                    await websocket.send_json({
                        "type": "agency_warning",
                        "fragment": last_turn.metadata["agency_violation_warning"],
                    })
                temp = session.emotional_temperature
                if abs(temp.get("drift", 0.0)) >= 1.0:
                    await websocket.send_json({
                        "type": "temp_drift",
                        "current": temp.get("current", 5.0),
                        "drift": temp.get("drift", 0.0),
                    })
                for ch in last_turn.content:
                    await websocket.send_json({"type": "chunk", "content": ch})
                    await asyncio.sleep(0)
                has_decision = last_turn.decision is not None and not last_turn.decision.is_free_action
                options = last_turn.decision.options if last_turn.decision else []
                risk_levels = last_turn.decision.risk_levels if last_turn.decision else []
                decision_type = last_turn.decision.decision_type if last_turn.decision else "action"
                await websocket.send_json({
                    "type": "turn_complete",
                    "phase": session.phase.value,
                    "scene_pressure": session.scene_pressure,
                    "emotional_temperature": session.emotional_temperature,
                    "density": session.density,
                    "record": {
                        "turn_id": last_turn.turn_id,
                        "who": last_turn.who,
                        "content": last_turn.content,
                        "scene_pressure": last_turn.scene_pressure,
                        "density": last_turn.density,
                        "phase": last_turn.phase.value,
                        "has_decision": has_decision,
                        "decision_options": options,
                        "decision_type": decision_type,
                        "risk_levels": risk_levels,
                    },
                })
    except WebSocketDisconnect:
        pass
