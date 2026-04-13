"""routers/traces.py — 链路追踪、风格、WorldBuilder、一致性检查路由模块。"""
from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from narrative_os.infra.database import get_db
from narrative_os.interface.services.trace_service import TraceService, get_trace_service

from narrative_os.schemas.traces import (
    ConsistencyReport,
    Run,
    RunApprovalRequest,
    RunApprovalResponse,
    RunListResponse,
    StyleExtractRequest,
    StyleExtractResponse,
    PluginInfo,
    StylePreset,
    TraceResponse,
    WorldbuilderStartResponse,
    WorldbuilderStepRequest,
    WorldbuilderStepResponse,
    WorldBuilderDiscussRequest,
    ConsistencyCheckRequest,
)

router = APIRouter(tags=["traces"])

# ------------------------------------------------------------------ #
# 插件管理                                                              #
# ------------------------------------------------------------------ #

from threading import Lock as _Lock

_plugin_registry: dict[str, dict[str, Any]] = {
    "humanizer": {"id": "humanizer", "name": "Humanizer", "enabled": True, "description": "后处理去AI痕迹"},
    "consistency": {"id": "consistency", "name": "一致性检查", "enabled": True, "description": "情节/时间线一致性"},
    "style": {"id": "style", "name": "风格引擎", "enabled": True, "description": "文体风格控制"},
}
_plugin_lock = _Lock()

_STYLE_PRESETS: list[dict[str, Any]] = [
    {"id": "hemingway_concise", "name": "海明威·简洁", "genre": "literary", "tone": "minimalist", "sentence_length": "short",
     "params": {"adj_density": 15, "sentence_complexity": 20, "dialogue_ratio": 60, "pov_depth": 40, "imagery_density": 20}},
    {"id": "gibson_cyber", "name": "吉布森·赛博", "genre": "scifi", "tone": "gritty", "sentence_length": "medium",
     "params": {"adj_density": 80, "sentence_complexity": 75, "dialogue_ratio": 30, "pov_depth": 90, "imagery_density": 85}},
    {"id": "jinyong_wuxia", "name": "金庸·武侠", "genre": "wuxia", "tone": "heroic", "sentence_length": "medium",
     "params": {"adj_density": 60, "sentence_complexity": 70, "dialogue_ratio": 45, "pov_depth": 55, "imagery_density": 65}},
    {"id": "fantasy_epic", "name": "史诗奇幻", "genre": "fantasy", "tone": "heroic", "sentence_length": "long",
     "params": {"adj_density": 75, "sentence_complexity": 80, "dialogue_ratio": 35, "pov_depth": 50, "imagery_density": 80}},
    {"id": "horror_suspense", "name": "恐怖压抑", "genre": "horror", "tone": "oppressive", "sentence_length": "short",
     "params": {"adj_density": 65, "sentence_complexity": 60, "dialogue_ratio": 25, "pov_depth": 85, "imagery_density": 70}},
    {"id": "romance_emotional", "name": "情感言情", "genre": "romance", "tone": "warm", "sentence_length": "medium",
     "params": {"adj_density": 55, "sentence_complexity": 50, "dialogue_ratio": 65, "pov_depth": 75, "imagery_density": 55}},
    {"id": "suspense_thriller", "name": "悬疑惊悚", "genre": "suspense", "tone": "tense", "sentence_length": "short",
     "params": {"adj_density": 40, "sentence_complexity": 55, "dialogue_ratio": 50, "pov_depth": 80, "imagery_density": 45}},
    {"id": "literary_prose", "name": "文学纯文学", "genre": "literary", "tone": "introspective", "sentence_length": "long",
     "params": {"adj_density": 70, "sentence_complexity": 85, "dialogue_ratio": 30, "pov_depth": 90, "imagery_density": 75}},
    {"id": "mystery_detective", "name": "推理悬疑", "genre": "mystery", "tone": "analytical", "sentence_length": "medium",
     "params": {"adj_density": 35, "sentence_complexity": 60, "dialogue_ratio": 55, "pov_depth": 70, "imagery_density": 40}},
    {"id": "humor_light", "name": "轻松幽默", "genre": "humor", "tone": "playful", "sentence_length": "short",
     "params": {"adj_density": 30, "sentence_complexity": 30, "dialogue_ratio": 70, "pov_depth": 40, "imagery_density": 35}},
    {"id": "cultivation_xianxia", "name": "修仙爽文", "genre": "xianxia", "tone": "assertive", "sentence_length": "short",
     "params": {"adj_density": 35, "sentence_complexity": 40, "dialogue_ratio": 40, "pov_depth": 60, "imagery_density": 50}},
]

# WorldBuilder 会话存储
_wb_sessions: dict[str, Any] = {}
_wb_sessions_lock = _Lock()


def _get_wb_session(wb_session_id: str) -> Any:
    with _wb_sessions_lock:
        wb = _wb_sessions.get(wb_session_id)
    if wb is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"detail": f"WorldBuilder 会话 '{wb_session_id}' 不存在或已过期。", "code": "NOT_FOUND"},
        )
    return wb


# ------------------------------------------------------------------ #
# 链路追踪                                                              #
# ------------------------------------------------------------------ #


@router.get("/traces/{chapter_id}", response_model=TraceResponse, summary="执行链路追踪")
async def get_traces(chapter_id: str) -> TraceResponse:
    return TraceResponse(chapter_id=chapter_id, nodes=[], edges=[], note="tracing not yet available")


@router.get("/projects/{project_id}/runs", response_model=RunListResponse, summary="项目 Run 列表")
async def list_runs(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    svc: TraceService = Depends(get_trace_service),
) -> RunListResponse:
    return await svc.list_runs(db, project_id)


@router.get("/runs/{run_id}", response_model=Run, summary="Run 详情")
async def get_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    svc: TraceService = Depends(get_trace_service),
) -> Run:
    return await svc.get_run(db, run_id, include_steps=True)


@router.get("/runs/{run_id}/steps", response_model=Run, summary="RunStep + Artifact 树")
async def get_run_steps(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    svc: TraceService = Depends(get_trace_service),
) -> Run:
    return await svc.get_run(db, run_id, include_steps=True)


@router.post("/runs/{run_id}/approve", response_model=RunApprovalResponse, summary="Run HITL 审批")
async def approve_run(
    run_id: str,
    req: RunApprovalRequest,
    db: AsyncSession = Depends(get_db),
    svc: TraceService = Depends(get_trace_service),
) -> RunApprovalResponse:
    return await svc.approve_run(db, run_id, req.decision)


# ------------------------------------------------------------------ #
# 插件管理                                                              #
# ------------------------------------------------------------------ #


@router.get("/plugins", response_model=list[PluginInfo], summary="插件列表")
async def list_plugins() -> list[PluginInfo]:
    with _plugin_lock:
        return [PluginInfo.model_validate(item) for item in _plugin_registry.values()]


@router.post("/plugins/{plugin_id}/toggle", response_model=PluginInfo, summary="切换插件启用状态")
async def toggle_plugin(plugin_id: str) -> PluginInfo:
    with _plugin_lock:
        if plugin_id not in _plugin_registry:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"detail": f"插件 '{plugin_id}' 不存在。", "code": "NOT_FOUND"},
            )
        _plugin_registry[plugin_id]["enabled"] = not _plugin_registry[plugin_id]["enabled"]
        return PluginInfo.model_validate(dict(_plugin_registry[plugin_id]))


# ------------------------------------------------------------------ #
# 风格控制                                                              #
# ------------------------------------------------------------------ #


@router.post("/style/extract", response_model=StyleExtractResponse, summary="从文本提取风格参数")
async def extract_style(req: StyleExtractRequest) -> StyleExtractResponse:
    text = req.text
    sents = text.count("。") + text.count("！") + text.count("？") + text.count("\n")
    words = len(text)
    avg_len = words / max(sents, 1)
    sentence_length = "short" if avg_len < 15 else ("long" if avg_len > 40 else "medium")
    return StyleExtractResponse(
        sentence_length=sentence_length,
        tone="neutral",
        genre="general",
        style_directives=[],
        warning_words=[],
    )


@router.get("/style/presets", response_model=list[StylePreset], summary="风格预设列表")
async def list_style_presets() -> list[StylePreset]:
    return [StylePreset.model_validate(item) for item in _STYLE_PRESETS]


# ------------------------------------------------------------------ #
# WorldBuilder 会话端点                                                 #
# ------------------------------------------------------------------ #


@router.post("/worldbuilder/start", response_model=WorldbuilderStartResponse, summary="启动 WorldBuilder 会话")
async def worldbuilder_start() -> WorldbuilderStartResponse:
    from narrative_os.core.world_builder import WorldBuilder
    wb = WorldBuilder()
    result = wb.start()
    wb_id = str(uuid.uuid4())
    with _wb_sessions_lock:
        _wb_sessions[wb_id] = wb
    return WorldbuilderStartResponse(
        wb_session_id=wb_id,
        step=result.step.value,
        prompt=result.prompt_to_user,
        requires_confirmation=result.requires_confirmation,
        skippable=result.skippable,
        draft=result.draft,
    )


@router.post("/worldbuilder/step", response_model=WorldbuilderStepResponse, summary="推进 WorldBuilder 步骤")
async def worldbuilder_step(req: WorldbuilderStepRequest) -> WorldbuilderStepResponse:
    from narrative_os.core.state_snapshot_store import save_runtime_snapshot_payload
    from narrative_os.interface.services.project_service import get_project_service

    wb = _get_wb_session(req.wb_session_id)
    result = wb.submit_step(req.user_input)
    done = result.step.value == "done"

    seed_data = None
    if done:
        wb_state = wb.state
        seed_data = {
            "characters": wb_state.initial_characters or [],
            "world": wb_state.initial_world or {},
            "plot_nodes": wb_state.initial_plot_nodes or [],
        }
        _wb_project_id = f"wb_{req.wb_session_id[:8]}"
        try:
            project_svc = get_project_service()
            seed_handle = project_svc.try_load_project(_wb_project_id)
            if seed_handle is None:
                seed_handle = project_svc.initialize_project(_wb_project_id, title=_wb_project_id)
            _kb = seed_handle.load_kb()
            if wb_state.initial_characters:
                _kb["characters"] = wb_state.initial_characters
            if wb_state.initial_world:
                _kb["world"] = wb_state.initial_world
            if wb_state.initial_plot_nodes:
                _kb["plot_nodes"] = wb_state.initial_plot_nodes
            if wb_state.one_sentence:
                _kb["one_sentence"] = wb_state.one_sentence
            if wb_state.one_paragraph:
                _kb["one_paragraph"] = wb_state.one_paragraph
            seed_handle.save_kb(_kb)
            seed_handle.save_state()
            save_runtime_snapshot_payload(
                _wb_project_id,
                characters=wb_state.initial_characters or [],
                world=wb_state.initial_world or {},
            )
        except Exception:
            pass

    return WorldbuilderStepResponse(
        wb_session_id=req.wb_session_id,
        step=result.step.value,
        prompt=result.prompt_to_user,
        done=done,
        requires_confirmation=result.requires_confirmation,
        skippable=result.skippable,
        draft=result.draft,
        seed_data=seed_data,
    )


@router.post("/worldbuilder/discuss", summary="与 AI 讨论世界构建步骤 (SSE)")
async def worldbuilder_discuss(req: WorldBuilderDiscussRequest):
    wb = _get_wb_session(req.wb_session_id)

    async def event_stream():
        try:
            async for chunk in wb.discuss(req.message):
                yield f"data: {json.dumps({'text': chunk}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'done': True}, ensure_ascii=False)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'error': str(exc)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ------------------------------------------------------------------ #
# 一致性检查                                                            #
# ------------------------------------------------------------------ #


@router.post("/consistency/check", response_model=ConsistencyReport, summary="情节/时间线一致性检查")
async def run_consistency_check(req: ConsistencyCheckRequest) -> ConsistencyReport:
    import sys
    _api = sys.modules.get("narrative_os.interface.api")
    _CC = getattr(_api, "ConsistencyChecker", None) if _api else None
    if _CC is None:
        from narrative_os.skills.consistency import ConsistencyChecker as _CC
    checker = _CC()
    report = checker.check(text=req.text, chapter=req.chapter)
    return ConsistencyReport(
        score=report.score,
        issues=[
            {
                "dimension": issue.dimension,
                "severity": issue.severity,
                "description": issue.description,
                "suggestion": issue.suggestion,
                "source_rule": issue.source_rule,
                "confidence": issue.confidence,
            }
            for issue in report.issues
        ],
        summary=report.summary(),
    )
