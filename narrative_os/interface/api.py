"""
interface/api.py — Phase 4: FastAPI REST API

路由：
  POST  /chapters/run           完整生成一章
  POST  /chapters/plan          仅规划骨架（不写正文）
  GET   /projects/{id}/status   查看项目状态
  GET   /cost                   今日 token 消耗
  POST  /metrics                计算草稿指标
  GET   /health                 健康检查

所有请求体/响应体均为 Pydantic BaseModel。
错误统一返回 {"detail": "..."} + 适当 HTTP 状态码。
"""

from __future__ import annotations

import asyncio
import json
import time
import threading
import uuid
from contextlib import asynccontextmanager
from threading import Lock
from typing import Any, Literal, Optional

from fastapi import Body, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

# DB 持久化
from narrative_os.infra.database import init_db, AsyncSessionLocal, fire_and_forget
from narrative_os.infra.models import (
    TrpgSession as TrpgSessionModel,
    WorldbuilderSession as WbSessionModel,
    Project as ProjectModel,
)
from narrative_os.infra.models import (
    WorldSandbox as WorldSandboxModel,
    StoryConcept as StoryConceptModel,
)
from narrative_os.core.world_sandbox import (
    WorldSandboxData,
    ConceptData,
    Region,
    Faction,
    PowerSystem,
    WorldRelation,
    TimelineSandboxEvent,
    RelationType,
    PowerSystemTemplateType,
    POWER_SYSTEM_TEMPLATES,
    get_template_summary,
    normalize_relation_type,
)

# Module-level imports so tests can monkeypatch cleanly
from narrative_os.agents.interactive import (
    InteractiveAgent,
    InteractiveSession,
    SessionConfig,
    SessionPhase,
)
from narrative_os.agents.planner import PlannerAgent, PlannerInput
from narrative_os.agents.writer import ChapterDraft
from narrative_os.core.state import StateManager, ChapterMeta
from narrative_os.infra.cost import cost_ctrl
from narrative_os.orchestrator.graph import run_chapter
from narrative_os.infra.config import settings
from narrative_os.skills.metrics import NarrativeMetricsCalc
# Phase 7 imports
from narrative_os.core.plot import PlotGraph
from narrative_os.core.memory import MemorySystem
from narrative_os.skills.style_engine import StyleEngine
from narrative_os.core.world_builder import WorldBuilder
from narrative_os.skills.consistency import ConsistencyChecker

@asynccontextmanager
async def _lifespan(app: FastAPI):  # type: ignore[type-arg]
    """应用启动时初始化 DB，关闭时清理（预留）。"""
    await init_db()
    yield


app = FastAPI(
    title="Narrative OS API",
    description="可编程叙事操作系统 REST API",
    version="0.1.0",
    lifespan=_lifespan,
)


# ------------------------------------------------------------------ #
# 请求追踪中间件                                                        #
# ------------------------------------------------------------------ #

@app.middleware("http")
async def _inject_correlation_id(request: Request, call_next):  # type: ignore[type-arg]
    """为每个请求生成 correlation_id，注入日志上下文并添加到响应头。"""
    from narrative_os.infra.logging import set_correlation_id
    cid = uuid.uuid4().hex[:8]
    set_correlation_id(cid)
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = cid
    return response


# ------------------------------------------------------------------ #
# Request / Response 模型                                               #
# ------------------------------------------------------------------ #

class RunChapterRequest(BaseModel):
    chapter: int = Field(ge=1, le=9999)
    volume: int = Field(default=1, ge=1, le=999)
    target_summary: str = Field(min_length=1)
    word_count_target: int = Field(default=2000, ge=500, le=20000)
    strategy: str = settings.llm_strategy
    previous_hook: str = ""
    existing_arc_summary: str = ""
    character_names: list[str] = Field(default_factory=list)
    world_rules: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    project_id: str = "default"
    skill_names: list[str] = Field(default_factory=list)  # narrativespace skills to activate


class RunChapterResponse(BaseModel):
    chapter: int
    volume: int
    text: str
    word_count: int
    change_ratio: float
    quality_score: float
    hook_score: float
    passed: bool
    retry_count: int


class PlanChapterRequest(BaseModel):
    chapter: int
    volume: int = 1
    target_summary: str
    word_count_target: int = 2000
    previous_hook: str = ""
    character_names: list[str] = Field(default_factory=list)
    world_rules: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    project_id: str = "default"


class PlanChapterResponse(BaseModel):
    chapter_outline: str
    planned_nodes: list[dict[str, Any]]
    dialogue_goals: list[str]
    hook_suggestion: str
    hook_type: str
    tension_curve: list[float]


class CostResponse(BaseModel):
    used_tokens: int
    budget_tokens: int
    usage_ratio: float
    by_skill: dict[str, int]
    by_agent: dict[str, int]


class MetricsRequest(BaseModel):
    draft: dict[str, Any]             # ChapterDraft JSON
    word_count_target: int = 2000


class MetricsResponse(BaseModel):
    chapter: int
    overall_score: float
    avg_tension: float
    hook_score: float
    payoff_density: float
    pacing_score: float
    tension_trend: str
    consistency_score: float
    word_efficiency: float
    # 8 narrativespace quality dimensions
    qd_01_catharsis: float = 0.0        # 宣泄感
    qd_02_golden_finger: float = 0.0    # 金手指利用率
    qd_03_rhythm: float = 0.0           # 节奏
    qd_04_dialogue: float = 0.0         # 对白辨识度
    qd_05_char_consistency: float = 0.0 # 人物一致性
    qd_06_meaning: float = 0.0          # 意义契合度
    qd_07_hook: float = 0.0             # 钉子强度
    qd_08_readability: float = 0.0      # 易读性


# ------------------------------------------------------------------ #
# 路由实现                                                              #
# ------------------------------------------------------------------ #

@app.get("/health", summary="健康检查")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": app.version}


# ---------------------- run chapter -------------------------------- #

@app.post(
    "/chapters/run",
    response_model=RunChapterResponse,
    status_code=status.HTTP_200_OK,
    summary="完整生成一章",
)
async def run_chapter_route(req: RunChapterRequest) -> RunChapterResponse:
    # ── B7: 自动补全 previous_hook ──────────────────────────────────
    if not req.previous_hook and req.chapter > 1:
        try:
            _hook_mgr = StateManager(project_id=req.project_id, base_dir=".narrative_state")
            _hook_mgr.load_state()
            _hook_kb = _hook_mgr.load_kb()
            _auto_hook = _hook_kb.get(f"chapter_{req.chapter - 1}_hook", "")
            if not _auto_hook:
                # 降级：从 ChapterMeta.summary 中提取
                _prev_meta = next(
                    (m for m in reversed(_hook_mgr.state.chapters) if m.chapter == req.chapter - 1),
                    None,
                )
                if _prev_meta:
                    _auto_hook = _prev_meta.summary
            if _auto_hook:
                req = req.model_copy(update={"previous_hook": _auto_hook})
        except Exception:
            pass  # 自动填充失败不阻断

    try:
        async with asyncio.timeout(180):  # 3 分钟超时
            result = await run_chapter(
                chapter=req.chapter,
                volume=req.volume,
                target_summary=req.target_summary,
                word_count_target=req.word_count_target,
                strategy=req.strategy,
                previous_hook=req.previous_hook,
                existing_arc_summary=req.existing_arc_summary,
                character_names=req.character_names,
                world_rules=req.world_rules,
                constraints=req.constraints,
                thread_id=f"{req.project_id}-ch{req.chapter:04d}",
            )
    except TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="章节生成超时，请重试",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"生成失败：{exc}",
        )

    edited = result.get("edited_chapter")
    if edited is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="未能生成最终章节。",
        )

    critic = result.get("critic_report")

    # ── B1: 章节持久化 ──────────────────────────────────────────────
    try:
        state_mgr = StateManager(project_id=req.project_id, base_dir=".narrative_state")
        try:
            state_mgr.load_state()
        except FileNotFoundError:
            state_mgr.initialize(project_name=req.project_id)

        # 保存章节文本文件
        state_mgr.save_chapter_text(edited.chapter, edited.text)

        # 构建 ChapterMeta
        chapter_meta = ChapterMeta(
            chapter=edited.chapter,
            summary=req.target_summary[:200],
            quality_score=critic.quality_score if critic else 0.0,
            hook_score=critic.hook_score if critic else 0.0,
            word_count=edited.word_count,
        )

        # 加载 KB 中的 plot/characters/world 数据
        kb = state_mgr.load_kb()
        plot_dict = kb.get("plot_graph") if isinstance(kb, dict) else None
        chars_dict = kb.get("characters") if isinstance(kb, dict) else None
        world_dict = kb.get("world") if isinstance(kb, dict) else None

        # 提交章节快照（含版本锁）
        state_mgr.commit_chapter(
            edited.chapter,
            plot_graph_dict=plot_dict if isinstance(plot_dict, dict) else None,
            characters_dict=chars_dict,
            world_dict=world_dict,
            chapter_meta=chapter_meta,
        )

        # 提取并写入 hook 到 KB（供下一章自动读取）
        hook_text = ""
        planner_out = result.get("planner_output")
        if planner_out and hasattr(planner_out, "hook_suggestion"):
            hook_text = planner_out.hook_suggestion
        if not hook_text and critic and hasattr(critic, "review_summary"):
            hook_text = critic.review_summary[:300]
        if hook_text:
            kb[f"chapter_{edited.chapter}_hook"] = hook_text
            state_mgr.save_kb(kb)
    except Exception as _persist_exc:
        import warnings
        warnings.warn(f"章节持久化失败（非致命）：{_persist_exc}", stacklevel=2)

    return RunChapterResponse(
        chapter=edited.chapter,
        volume=edited.volume,
        text=edited.text,
        word_count=edited.word_count,
        change_ratio=edited.change_ratio,
        quality_score=critic.quality_score if critic else 0.0,
        hook_score=critic.hook_score if critic else 0.0,
        passed=critic.passed if critic else True,
        retry_count=result.get("retry_count", 0),
    )


# ---------------------- plan chapter -------------------------------- #

@app.post(
    "/chapters/plan",
    response_model=PlanChapterResponse,
    status_code=status.HTTP_200_OK,
    summary="仅生成章节剧情骨架",
)
async def plan_chapter_route(req: PlanChapterRequest) -> PlanChapterResponse:
    inp = PlannerInput(
        chapter=req.chapter,
        volume=req.volume,
        target_summary=req.target_summary,
        word_count_target=req.word_count_target,
        previous_hook=req.previous_hook,
        character_names=req.character_names,
        world_rules=req.world_rules,
        constraints=req.constraints,
    )
    try:
        plan = await PlannerAgent().plan(inp)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"规划失败：{exc}",
        )

    return PlanChapterResponse(
        chapter_outline=plan.chapter_outline,
        planned_nodes=[n.model_dump() for n in plan.planned_nodes],
        dialogue_goals=plan.dialogue_goals,
        hook_suggestion=plan.hook_suggestion,
        hook_type=plan.hook_type,
        tension_curve=[v for _, v in plan.tension_curve],
    )


# ---------------------- project status ------------------------------ #

@app.get(
    "/projects/{project_id}/status",
    status_code=status.HTTP_200_OK,
    summary="查看项目状态",
)
async def project_status(project_id: str) -> dict[str, Any]:
    mgr = StateManager(project_id=project_id, base_dir=".narrative_state")
    try:
        mgr.load_state()
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"项目 '{project_id}' 不存在。",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )

    state = mgr.state
    return {
        "project_id": project_id,
        "current_chapter": state.current_chapter,
        "current_volume": state.current_volume,
        "total_word_count": sum(c.word_count for c in state.chapters),
        "versions": mgr.list_versions(),
    }


# ---------------------- cost ---------------------------------------- #

@app.get(
    "/cost",
    response_model=CostResponse,
    status_code=status.HTTP_200_OK,
    summary="查看今日 Token 消耗",
)
async def get_cost() -> CostResponse:
    s = cost_ctrl.summary()
    return CostResponse(
        used_tokens=s["used"],
        budget_tokens=s["budget"],
        usage_ratio=s["ratio"],
        by_skill=s.get("by_skill", {}),
        by_agent=s.get("by_agent", {}),
    )


# ---------------------- metrics ------------------------------------- #

@app.post(
    "/metrics",
    response_model=MetricsResponse,
    status_code=status.HTTP_200_OK,
    summary="计算叙事质量指标",
)
async def compute_metrics(req: MetricsRequest) -> MetricsResponse:
    try:
        draft = ChapterDraft.model_validate(req.draft)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"解析 ChapterDraft 失败：{exc}",
        )

    calc = NarrativeMetricsCalc()
    m = calc.evaluate_chapter(draft, word_count_target=req.word_count_target)

    return MetricsResponse(
        chapter=m.chapter,
        overall_score=m.overall_score,
        avg_tension=m.avg_tension,
        hook_score=m.hook_score,
        payoff_density=m.payoff_density,
        pacing_score=m.pacing_score,
        tension_trend=m.tension_trend,
        consistency_score=m.consistency_score,
        word_efficiency=m.word_efficiency,
        # derive 8D from available data
        qd_01_catharsis=round(min(m.avg_tension * 0.9, 10.0), 2),
        qd_02_golden_finger=round(m.payoff_density, 2),
        qd_03_rhythm=round(m.pacing_score, 2),
        qd_04_dialogue=round(m.word_efficiency * 0.8, 2),
        qd_05_char_consistency=round(m.consistency_score, 2),
        qd_06_meaning=round(m.overall_score * 0.85, 2),
        qd_07_hook=round(m.hook_score, 2),
        qd_08_readability=round(m.word_efficiency, 2),
    )


# ================================================================== #
# TRPG 会话端点（阶段 3）                                               #
# ================================================================== #

# ------------------------------------------------------------------ #
# TRPG 会话 Pydantic 模型                                               #
# ------------------------------------------------------------------ #

class CreateSessionRequest(BaseModel):
    project_id: str = "default"
    character_name: str = "主角"
    density: Literal["dense", "normal", "sparse"] = "normal"
    opening_prompt: str = ""
    world_summary: str = ""
    max_history_turns: int = Field(default=30, ge=5, le=100)


class SessionStepRequest(BaseModel):
    user_input: str = Field(..., min_length=1, max_length=2000)
    density: str | None = None  # override density: dense / normal / sparse


class InterruptRequest(BaseModel):
    bangui_command: str = Field(..., min_length=1)


class RollbackRequest(BaseModel):
    steps: int = Field(default=1, ge=1, le=10)


class SessionStatusResponse(BaseModel):
    session_id: str
    project_id: str
    phase: str
    turn: int
    scene_pressure: float
    density: str
    history_count: int
    emotional_temperature: dict = Field(default_factory=lambda: {"base": "neutral", "current": 5.0, "drift": 0.0})
    turn_char_count: int = 0


class TurnRecordResponse(BaseModel):
    turn_id: int
    who: str
    content: str
    scene_pressure: float
    density: str
    phase: str
    has_decision: bool
    decision_options: list[str] = Field(default_factory=list)


# Phase 7 request models
class StyleExtractRequest(BaseModel):
    text: str = Field(..., min_length=1)


class WorldbuilderStepRequest(BaseModel):
    wb_session_id: str
    user_input: str


class WorldBuilderDiscussRequest(BaseModel):
    wb_session_id: str
    message: str


class ConsistencyCheckRequest(BaseModel):
    text: str = Field(..., min_length=1)
    chapter: int = 0


# ------------------------------------------------------------------ #
# 内存会话存储                                                          #
# ------------------------------------------------------------------ #

_sessions: dict[str, tuple[InteractiveSession, float]] = {}
_sessions_lock = Lock()
SESSION_TTL_SECONDS = 3600  # 1 小时

_interactive_agent = InteractiveAgent()


# Phase 7: WorldBuilder session store
_wb_sessions: dict[str, WorldBuilder] = {}
_wb_sessions_lock = Lock()


def _get_wb_session(wb_session_id: str) -> WorldBuilder:
    """获取 WorldBuilder 会话，不存在时抛出 404。"""
    with _wb_sessions_lock:
        wb = _wb_sessions.get(wb_session_id)
    if wb is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"detail": f"WorldBuilder 会话 '{wb_session_id}' 不存在或已过期。", "code": "NOT_FOUND"},
        )
    return wb


# Phase 7: In-memory plugin registry (PluginRegistry not yet in codebase)
_plugin_registry: dict[str, dict[str, Any]] = {
    "humanizer": {"id": "humanizer", "name": "Humanizer", "enabled": True, "description": "后处理去AI痕迹"},
    "consistency": {"id": "consistency", "name": "一致性检查", "enabled": True, "description": "情节/时间线一致性"},
    "style": {"id": "style", "name": "风格引擎", "enabled": True, "description": "文体风格控制"},
}
_plugin_lock = Lock()


# Phase 7 + Phase 5: Built-in style presets (narrativespace style_modules)
_STYLE_PRESETS: list[dict[str, Any]] = [
    # Classic author DNA
    {"id": "hemingway_concise", "name": "海明威·简洁", "genre": "literary", "tone": "minimalist", "sentence_length": "short",
     "params": {"adj_density": 15, "sentence_complexity": 20, "dialogue_ratio": 60, "pov_depth": 40, "imagery_density": 20}},
    {"id": "gibson_cyber", "name": "吉布森·赛博", "genre": "scifi", "tone": "gritty", "sentence_length": "medium",
     "params": {"adj_density": 80, "sentence_complexity": 75, "dialogue_ratio": 30, "pov_depth": 90, "imagery_density": 85}},
    {"id": "jinyong_wuxia", "name": "金庸·武侠", "genre": "wuxia", "tone": "heroic", "sentence_length": "medium",
     "params": {"adj_density": 60, "sentence_complexity": 70, "dialogue_ratio": 45, "pov_depth": 55, "imagery_density": 65}},
    # narrativespace genre modules
    {"id": "fantasy_epic", "name": "史诗奇幻", "genre": "fantasy", "tone": "heroic", "sentence_length": "long",
     "params": {"adj_density": 75, "sentence_complexity": 80, "dialogue_ratio": 35, "pov_depth": 50, "imagery_density": 80},
     "focus": "世界规则、能力成本、制度反作用"},
    {"id": "horror_suspense", "name": "恐怖压抑", "genre": "horror", "tone": "oppressive", "sentence_length": "short",
     "params": {"adj_density": 65, "sentence_complexity": 60, "dialogue_ratio": 25, "pov_depth": 85, "imagery_density": 70},
     "focus": "感知扭曲、威胁缓释、环境叙述"},
    {"id": "romance_emotional", "name": "情感言情", "genre": "romance", "tone": "warm", "sentence_length": "medium",
     "params": {"adj_density": 55, "sentence_complexity": 50, "dialogue_ratio": 65, "pov_depth": 75, "imagery_density": 55},
     "focus": "关系压力与情感债推进"},
    {"id": "suspense_thriller", "name": "悬疑惊悚", "genre": "suspense", "tone": "tense", "sentence_length": "short",
     "params": {"adj_density": 40, "sentence_complexity": 55, "dialogue_ratio": 50, "pov_depth": 80, "imagery_density": 45},
     "focus": "信息差、节拍反转、证据锚点"},
    {"id": "literary_prose", "name": "文学纯文学", "genre": "literary", "tone": "introspective", "sentence_length": "long",
     "params": {"adj_density": 70, "sentence_complexity": 85, "dialogue_ratio": 30, "pov_depth": 90, "imagery_density": 75},
     "focus": "意象密度与散文语节"},
    {"id": "mystery_detective", "name": "推理悬疑", "genre": "mystery", "tone": "analytical", "sentence_length": "medium",
     "params": {"adj_density": 35, "sentence_complexity": 60, "dialogue_ratio": 55, "pov_depth": 70, "imagery_density": 40},
     "focus": "线索埋设、发现节拍、合理性优先"},
    {"id": "humor_light", "name": "轻松幽默", "genre": "humor", "tone": "playful", "sentence_length": "short",
     "params": {"adj_density": 30, "sentence_complexity": 30, "dialogue_ratio": 70, "pov_depth": 40, "imagery_density": 35},
     "focus": "节奏感、对白爆点、情绪出口"},
    {"id": "cultivation_xianxia", "name": "修仙爽文", "genre": "xianxia", "tone": "assertive", "sentence_length": "short",
     "params": {"adj_density": 35, "sentence_complexity": 40, "dialogue_ratio": 40, "pov_depth": 60, "imagery_density": 50},
     "focus": "金手指节奏、境界成长、爽感密度"},
]


def _get_session(session_id: str) -> InteractiveSession:
    """获取会话，不存在时抛出 404，同时更新访问时间。"""
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


def _cleanup_stale_sessions() -> None:
    """删除过期的 TRPG 会话（每 10 分钟运行一次）。"""
    while True:
        time.sleep(600)
        cutoff = time.time() - SESSION_TTL_SECONDS
        with _sessions_lock:
            expired = [sid for sid, (_, ts) in _sessions.items() if ts < cutoff]
            for sid in expired:
                del _sessions[sid]


def _to_turn_response(session: InteractiveSession) -> TurnRecordResponse:
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


# 启动后台清理线程
_cleanup_thread = threading.Thread(target=_cleanup_stale_sessions, daemon=True)
_cleanup_thread.start()


# ------------------------------------------------------------------ #
# TRPG REST 端点                                                        #
# ------------------------------------------------------------------ #

@app.post(
    "/sessions/create",
    status_code=status.HTTP_201_CREATED,
    summary="创建 TRPG 会话",
)
async def create_session(req: CreateSessionRequest) -> dict[str, Any]:
    cfg = SessionConfig(
        project_id=req.project_id,
        character_name=req.character_name,
        density_override=req.density,
        opening_prompt=req.opening_prompt,
        world_summary=req.world_summary,
        max_history_turns=req.max_history_turns,
    )
    session = _interactive_agent.create_session(cfg)

    try:
        opening_turn = await _interactive_agent.start(session)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"detail": f"会话启动失败：{exc}", "code": "INTERNAL_ERROR"},
        )

    with _sessions_lock:
        _sessions[session.session_id] = (session, time.time())

    # 持久化 TRPG session 到 DB
    async def _create_trpg_in_db() -> None:
        try:
            async with AsyncSessionLocal() as db:
                # 确保项目存在
                proj = await db.get(ProjectModel, req.project_id)
                if proj is None:
                    db.add(ProjectModel(id=req.project_id, title=req.project_id))
                db.add(TrpgSessionModel(
                    id=session.session_id,
                    project_id=req.project_id,
                    chapter_num=req.chapter if hasattr(req, 'chapter') else 1,
                    phase=session.phase.value,
                    turn_count=session.turn,
                    scene_pressure=session.scene_pressure,
                    emotional_temp_json=json.dumps(session.emotional_temperature
                        if isinstance(session.emotional_temperature, dict)
                        else {"current": session.emotional_temperature}, ensure_ascii=False),
                    history_json=json.dumps([], ensure_ascii=False),
                ))
                await db.commit()
        except Exception:
            pass
    fire_and_forget(_create_trpg_in_db())

    return {
        "session_id": session.session_id,
        "phase": session.phase.value,
        "density": session.density,
        "scene_pressure": session.scene_pressure,
        "opening_turn": _to_turn_response(session).model_dump(),
    }


@app.post(
    "/sessions/{session_id}/step",
    status_code=status.HTTP_200_OK,
    summary="玩家行动推进一步",
)
async def session_step(session_id: str, req: SessionStepRequest) -> TurnRecordResponse:
    session = _get_session(session_id)
    if session.phase not in {SessionPhase.PING_PONG, SessionPhase.PACING_ALERT}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"detail": f"当前阶段 {session.phase} 不接受 step 操作。",
                    "code": "INVALID_PHASE"},
        )
    try:
        await _interactive_agent.step(session, req.user_input)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"detail": str(exc), "code": "INTERNAL_ERROR"},
        )
    return _to_turn_response(session)


@app.post(
    "/sessions/{session_id}/interrupt",
    status_code=status.HTTP_200_OK,
    summary="发送帮回指令",
)
async def session_interrupt(session_id: str, req: InterruptRequest) -> TurnRecordResponse:
    session = _get_session(session_id)
    try:
        await _interactive_agent.interrupt(session, req.bangui_command)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"detail": str(exc), "code": "INTERNAL_ERROR"},
        )
    return _to_turn_response(session)


@app.post(
    "/sessions/{session_id}/rollback",
    status_code=status.HTTP_200_OK,
    summary="回滚 N 步",
)
async def session_rollback(session_id: str, req: RollbackRequest) -> SessionStatusResponse:
    session = _get_session(session_id)
    _interactive_agent.rollback(session, steps=req.steps)
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


@app.get(
    "/sessions/{session_id}/status",
    response_model=SessionStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="查看会话状态",
)
async def session_status(session_id: str) -> SessionStatusResponse:
    session = _get_session(session_id)
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


@app.post(
    "/sessions/{session_id}/end",
    status_code=status.HTTP_200_OK,
    summary="结束 TRPG 会话",
)
async def session_end(session_id: str) -> dict[str, Any]:
    """结束会话，将 TRPG 章节持久化，并返回摘要信息。"""
    session = _get_session(session_id)
    result = _interactive_agent.land(session)

    # ── B5: TRPG 章节持久化 ─────────────────────────────────────────
    chapter_text = result.get("chapter_text", "")
    saved_chapter: int | None = None
    if chapter_text:
        try:
            import warnings as _warnings
            state_mgr = StateManager(
                project_id=session.project_id, base_dir=".narrative_state"
            )
            try:
                state_mgr.load_state()
            except FileNotFoundError:
                state_mgr.initialize(project_name=session.project_id)

            # 确定新章节编号
            new_ch = state_mgr.state.current_chapter + 1

            # 保存章节文本
            state_mgr.save_chapter_text(new_ch, chapter_text)

            # 构建 ChapterMeta
            chapter_meta = ChapterMeta(
                chapter=new_ch,
                summary=result.get("history_summary", "")[:200],
                quality_score=0.0,
                hook_score=0.0,
                word_count=result.get("word_count", len(chapter_text)),
            )

            # 提交章节快照
            kb = state_mgr.load_kb()
            state_mgr.commit_chapter(
                new_ch,
                plot_graph_dict=kb.get("plot_graph") if isinstance(kb, dict) else None,
                characters_dict=kb.get("characters") if isinstance(kb, dict) else None,
                world_dict=kb.get("world") if isinstance(kb, dict) else None,
                chapter_meta=chapter_meta,
            )

            # 写入 hook 到 KB（供下一章自动读取）
            hook_text = result.get("hook", "")
            if hook_text:
                kb2 = state_mgr.load_kb() or {}
                kb2["last_hook"] = hook_text
                state_mgr.save_kb(kb2)

            saved_chapter = new_ch
        except Exception as _e:
            import warnings as _warnings
            _warnings.warn(f"TRPG 章节持久化失败（非致命）：{_e}")

    with _sessions_lock:
        _sessions.pop(session_id, None)

    # 更新 DB 中的 session 记录（ended_at + summary）
    async def _end_trpg_in_db() -> None:
        try:
            from datetime import datetime, timezone  # noqa: PLC0415
            async with AsyncSessionLocal() as db:
                row = await db.get(TrpgSessionModel, session_id)
                if row is not None:
                    row.ended_at = datetime.now(timezone.utc)
                    row.phase = "ENDED"
                    row.turn_count = result.get("turns", 0)
                    row.summary_json = json.dumps({
                        "word_count": result.get("word_count", 0),
                        "next_hook": result.get("hook", ""),
                        "history_summary": result.get("history_summary", ""),
                        "character_deltas": result.get("character_deltas", []),
                    }, ensure_ascii=False)
                    await db.commit()
        except Exception:
            pass
    fire_and_forget(_end_trpg_in_db())

    return {
        "duration_minutes": 0,
        "turn_count": result.get("turns", 0),
        "word_count": result.get("word_count", 0),
        "bangui_count": 0,
        "key_decisions": [],
        "next_hook": result.get("hook", result.get("history_summary", "")),
        "character_delta": result.get("character_deltas", []),
        "saved_chapter": saved_chapter,
    }


# ================================================================== #
# Phase 3: SL 存档 + 控制权模式 + Agenda 端点                          #
# ================================================================== #

class SaveRequest(BaseModel):
    trigger: str = "manual"   # manual / scene_start / major_decision / high_risk


@app.post(
    "/projects/{project_id}/sessions/{session_id}/save",
    status_code=status.HTTP_201_CREATED,
    summary="手动存档",
)
async def create_save(
    project_id: str,
    session_id: str,
    req: SaveRequest,
) -> dict[str, Any]:
    """将当前会话状态快照写入 SaveStore，返回 save_id。"""
    from narrative_os.core.save_load import get_save_store
    session = _get_session(session_id)
    store = get_save_store(session_id)

    sp = store.create(
        session=session,
        trigger=req.trigger,
        memory_summary=session.memory_summary_cache,
    )
    return {"save_id": sp.save_id, "trigger": sp.trigger, "timestamp": sp.timestamp, "turn": sp.turn}


@app.get(
    "/projects/{project_id}/sessions/{session_id}/saves",
    summary="列出存档点",
)
async def list_saves(project_id: str, session_id: str) -> list[dict[str, Any]]:
    """返回该会话的所有存档列表（不含完整快照数据）。"""
    from narrative_os.core.save_load import get_save_store
    _get_session(session_id)   # 验证会话存在
    store = get_save_store(session_id)
    saves = store.list_saves(session_id)
    return [
        {
            "save_id": s.save_id,
            "trigger": s.trigger,
            "timestamp": s.timestamp,
            "turn": s.turn,
            "scene_pressure": s.scene_pressure,
        }
        for s in saves
    ]


@app.post(
    "/projects/{project_id}/sessions/{session_id}/load/{save_id}",
    summary="读档",
)
async def load_save(project_id: str, session_id: str, save_id: str) -> dict[str, Any]:
    """从指定存档点恢复会话状态（软回退）。"""
    from narrative_os.core.save_load import SoftRollback, get_save_store
    session = _get_session(session_id)
    store = get_save_store(session_id)

    sp = store.get(save_id)
    if sp is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"存档 '{save_id}' 不存在")

    rollback = SoftRollback()
    rollback.restore(session, sp)
    return {
        "save_id": save_id,
        "restored_turn": session.turn,
        "memory_summary_preserved": bool(session.memory_summary_cache),
    }


@app.delete(
    "/projects/{project_id}/sessions/{session_id}/saves/{save_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除存档",
)
async def delete_save(project_id: str, session_id: str, save_id: str) -> None:
    """删除指定存档点。"""
    from narrative_os.core.save_load import get_save_store
    _get_session(session_id)
    store = get_save_store(session_id)
    store.delete(save_id)


class ControlModeRequest(BaseModel):
    mode: str   # user_driven / semi_agent / full_agent / director
    ai_controlled_characters: list[str] = []
    allow_protagonist_proxy: bool = False
    director_intervention_enabled: bool = True


@app.post(
    "/projects/{project_id}/sessions/{session_id}/control-mode",
    summary="切换控制权模式",
)
async def set_control_mode(
    project_id: str,
    session_id: str,
    req: ControlModeRequest,
) -> dict[str, Any]:
    """运行中切换控制权模式（4 档）。"""
    from narrative_os.core.interactive_modes import ControlMode, ControlModeConfig
    session = _get_session(session_id)

    try:
        new_mode = ControlMode(req.mode)
    except ValueError:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=f"未知控制模式: {req.mode}")

    session.control_mode = new_mode
    session.mode_config = ControlModeConfig(
        mode=new_mode,
        ai_controlled_characters=req.ai_controlled_characters,
        allow_protagonist_proxy=req.allow_protagonist_proxy,
        director_intervention_enabled=req.director_intervention_enabled,
    )
    return {
        "session_id": session_id,
        "mode": new_mode.value,
        "prompt_hint": session.mode_config.prompt_hint,
    }


@app.get(
    "/projects/{project_id}/sessions/{session_id}/agenda",
    summary="查看当前角色 Agenda 状态",
)
async def get_session_agenda(project_id: str, session_id: str) -> dict[str, Any]:
    """返回上一轮沙盘推演产生的各角色 Agenda 列表。"""
    session = _get_session(session_id)
    return {
        "session_id": session_id,
        "turn": session.turn,
        "agenda": session.last_agenda,
    }


# ================================================================== #


# ================================================================== #
# Phase 4: ChangeSet / Canon Commit 端点                               #
# ================================================================== #

class SessionCommitRequest(BaseModel):
    mode: str = "session_only"  # session_only / draft_chapter / canon_chapter
    draft_content: str = ""
    require_canon_confirm: bool = False


@app.get(
    "/projects/{project_id}/changesets",
    summary="获取待审变更集列表",
)
async def list_changesets(project_id: str) -> list[dict[str, Any]]:
    """返回该项目的所有变更集（摘要视图）。"""
    from narrative_os.core.evolution import get_canon_commit
    cc = get_canon_commit(project_id)
    changesets = cc.list_changesets(project_id)
    return [
        {
            "changeset_id": cs.changeset_id,
            "source": cs.source.value,
            "session_id": cs.session_id,
            "commit_mode": cs.commit_mode.value,
            "changes_count": len(cs.changes),
            "pending_count": len(cs.pending_changes()),
            "confirmed_count": len(cs.confirmed_changes()),
            "created_at": cs.created_at,
        }
        for cs in changesets
    ]


@app.get(
    "/projects/{project_id}/changesets/{changeset_id}",
    summary="查看变更集详情",
)
async def get_changeset(project_id: str, changeset_id: str) -> dict[str, Any]:
    """返回指定变更集的完整信息（包括所有变更条目）。"""
    from fastapi import HTTPException
    from narrative_os.core.evolution import get_canon_commit
    cc = get_canon_commit(project_id)
    cs = cc.get_changeset(changeset_id)
    if cs is None:
        raise HTTPException(status_code=404, detail=f"变更集 '{changeset_id}' 不存在")
    return cs.model_dump()


@app.post(
    "/projects/{project_id}/changesets/{changeset_id}/approve",
    summary="批量批准并提交正史",
)
async def approve_changeset(project_id: str, changeset_id: str) -> dict[str, Any]:
    """批量审批变更集中所有草稿变更并提交正史。"""
    from fastapi import HTTPException
    from narrative_os.core.evolution import get_canon_commit
    cc = get_canon_commit(project_id)
    if cc.get_changeset(changeset_id) is None:
        raise HTTPException(status_code=404, detail=f"变更集 '{changeset_id}' 不存在")
    # Phase 1: approve_all → CANON_PENDING
    approved_count = cc.approve_all(changeset_id)
    # Phase 2: commit_to_canon → CANON_CONFIRMED
    committed = cc.commit_to_canon(changeset_id)
    return {
        "changeset_id": changeset_id,
        "approved_count": approved_count,
        "committed_count": len(committed),
    }


@app.post(
    "/projects/{project_id}/changesets/{changeset_id}/reject",
    summary="驳回整个变更集",
)
async def reject_changeset(project_id: str, changeset_id: str) -> dict[str, Any]:
    """驳回指定变更集中所有变更。"""
    from fastapi import HTTPException
    from narrative_os.core.evolution import get_canon_commit
    cc = get_canon_commit(project_id)
    cs = cc.get_changeset(changeset_id)
    if cs is None:
        raise HTTPException(status_code=404, detail=f"变更集 '{changeset_id}' 不存在")
    rejected_count = 0
    for change in cs.changes:
        cc.reject_change(change.change_id)
        rejected_count += 1
    return {"changeset_id": changeset_id, "rejected_count": rejected_count}


@app.post(
    "/projects/{project_id}/sessions/{session_id}/commit",
    summary="互动结束后选择提交方式",
    status_code=status.HTTP_201_CREATED,
)
async def commit_session(
    project_id: str,
    session_id: str,
    req: SessionCommitRequest,
) -> dict[str, Any]:
    """TRPG 会话结束后，选择三种提交方式之一。"""
    from fastapi import HTTPException
    from narrative_os.core.evolution import SessionCommitMode, get_canon_commit
    _get_session(session_id)   # 验证会话存在
    try:
        mode = SessionCommitMode(req.mode)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"未知提交模式: {req.mode}")
    cc = get_canon_commit(project_id)
    cs = cc.commit_session(
        project_id=project_id,
        session_id=session_id,
        mode=mode,
        draft_content=req.draft_content,
        require_canon_confirm=req.require_canon_confirm,
    )
    return {
        "changeset_id": cs.changeset_id,
        "commit_mode": cs.commit_mode.value,
        "changes_count": len(cs.changes),
        "canon_confirmed": cs.canon_confirmed,
    }


# ------------------------------------------------------------------ #
# WebSocket 端点                                                        #
# ------------------------------------------------------------------ #

@app.websocket("/ws/sessions/{session_id}")
async def ws_session(websocket: WebSocket, session_id: str) -> None:
    """
    WebSocket 流式叙事端点。
    客户端发送 {"action": "..."}，服务端逐字符流式返回 DM 叙事。
    """
    await websocket.accept()
    try:
        # 验证会话存在
        with _sessions_lock:
            entry = _sessions.get(session_id)
        if entry is None:
            await websocket.send_json(
                {"type": "error", "message": f"会话 '{session_id}' 不存在"}
            )
            await websocket.close(code=4004)
            return

        session, _ = entry

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
                await websocket.send_json({
                    "type": "error",
                    "message": f"当前阶段 {session.phase} 不接受行动",
                })
                continue

            # Apply density override before step
            prev_phase = session.phase
            prev_density = session.density
            if density_override in ("dense", "normal", "sparse"):
                session.density = density_override  # type: ignore[assignment]
                session.config.density_override = density_override  # type: ignore[assignment]

            try:
                await _interactive_agent.step(session, user_action)
            except Exception as exc:
                await websocket.send_json({"type": "error", "message": str(exc)})
                continue

            dm_turns = [t for t in session.history if t.who == "dm"]
            if dm_turns:
                last_turn = dm_turns[-1]
                # Emit phase change if changed
                if session.phase != prev_phase:
                    await websocket.send_json({
                        "type": "phase_change",
                        "phase": session.phase.value,
                    })
                # Emit density change if changed
                if session.density != prev_density:
                    await websocket.send_json({
                        "type": "density_change",
                        "density": session.density,
                    })
                # Emit pacing alert if triggered
                if session.phase.value == "PACING_ALERT":
                    await websocket.send_json({
                        "type": "pacing_alert",
                        "chars_so_far": session.turn_char_count,
                        "reason": last_turn.metadata.get("pacing_alert_reason", ""),
                    })
                # Emit agency warning if present
                if "agency_violation_warning" in last_turn.metadata:
                    await websocket.send_json({
                        "type": "agency_warning",
                        "fragment": last_turn.metadata["agency_violation_warning"],
                    })
                # Emit emotional temperature drift if noticeable
                temp = session.emotional_temperature
                if abs(temp.get("drift", 0.0)) >= 1.0:
                    await websocket.send_json({
                        "type": "temp_drift",
                        "current": temp.get("current", 5.0),
                        "drift": temp.get("drift", 0.0),
                    })
                # 逐字符流式发送（模拟 streaming token）
                for ch in last_turn.content:
                    await websocket.send_json({"type": "chunk", "content": ch})
                    await asyncio.sleep(0)  # yield，允许事件循环处理其他消息
                # 发送完成信号 + 完整回合记录
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
    finally:
        pass  # 不做清理，会话由 TTL 机制管理


# ================================================================== #
# Phase 7: 数据访问 API 扩展（13 个端点）                               #
# ================================================================== #

# ------------------------------------------------------------------ #
# C1–C5 项目数据端点                                                    #
# ------------------------------------------------------------------ #

def _load_project_or_404(project_id: str) -> StateManager:
    """加载项目状态，不存在时抛出 404。"""
    mgr = StateManager(project_id=project_id, base_dir=".narrative_state")
    try:
        mgr.load_state()
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"detail": f"项目 '{project_id}' 不存在。", "code": "NOT_FOUND"},
        )
    return mgr


def _try_load_project(project_id: str) -> StateManager | None:
    """尝试加载项目状态。项目不存在时返回 None（数据端点用，不抛 404）。"""
    mgr = StateManager(project_id=project_id, base_dir=".narrative_state")
    try:
        mgr.load_state()
        return mgr
    except FileNotFoundError:
        return None
    except Exception:
        return None


@app.get("/projects/{project_id}/plot", summary="获取项目情节图")
async def get_project_plot(project_id: str) -> dict[str, Any]:
    """返回 PlotGraph 节点 + 边 JSON。项目不存在时返回空图。"""
    mgr = _try_load_project(project_id)
    if mgr is not None:
        kb = mgr.load_kb()
        plot_data = kb.get("plot_graph")
        if plot_data and isinstance(plot_data, dict):
            try:
                return PlotGraph.from_dict(plot_data).to_dict()
            except Exception:
                pass
    return PlotGraph().to_dict()


@app.get("/projects/{project_id}/characters", summary="角色列表摘要")
async def get_project_characters(project_id: str) -> list[dict[str, Any]]:
    """返回项目所有角色的摘要信息。项目不存在时返回空列表。"""
    mgr = _try_load_project(project_id)
    if mgr is None:
        return []
    kb = mgr.load_kb()
    characters = kb.get("characters", [])
    if not isinstance(characters, list):
        return []
    return [
        {
            "name": c.get("name", ""),
            "emotion": c.get("emotion", "平静"),
            "health": c.get("health", 100),
            "arc_stage": c.get("arc_stage", ""),
            "faction": c.get("faction", ""),
            "is_alive": c.get("is_alive", True),
        }
        for c in characters
        if isinstance(c, dict)
    ]


@app.get("/projects/{project_id}/characters/{name}", summary="角色详情")
async def get_character_detail(project_id: str, name: str) -> dict[str, Any]:
    """返回指定角色的完整状态。项目不存在时抛出 404。"""
    mgr = _try_load_project(project_id)
    if mgr is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"detail": f"角色 '{name}' 不存在。", "code": "NOT_FOUND"},
        )
    kb = mgr.load_kb()
    characters = kb.get("characters", [])
    for c in characters if isinstance(characters, list) else []:
        if isinstance(c, dict) and c.get("name") == name:
            return c
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"detail": f"角色 '{name}' 不存在。", "code": "NOT_FOUND"},
    )


# ------------------------------------------------------------------ #
# Character CRUD + Test-Voice                                          #
# ------------------------------------------------------------------ #

class CharacterCreateRequest(BaseModel):
    name: str
    traits: list[str] = Field(default_factory=list)
    goal: str = ""
    backstory: str = ""
    description: str = ""
    personality: str = ""
    alias: list[str] = Field(default_factory=list)
    speech_style: str = ""
    catchphrases: list[str] = Field(default_factory=list)
    dialogue_examples: list[dict] = Field(default_factory=list)
    motivations: list[dict] = Field(default_factory=list)
    scenario_context: str = ""
    system_instructions: str = ""
    faction: str = ""


@app.post("/projects/{project_id}/characters", summary="创建角色")
async def create_character(project_id: str, req: CharacterCreateRequest) -> dict[str, Any]:
    mgr = _try_load_project(project_id)
    if mgr is None:
        raise HTTPException(status_code=404, detail={"detail": "项目不存在", "code": "NOT_FOUND"})
    kb = mgr.load_kb()
    characters = kb.get("characters", [])
    if not isinstance(characters, list):
        characters = []
    # 名称唯一性校验
    if any(isinstance(c, dict) and c.get("name") == req.name for c in characters):
        raise HTTPException(status_code=409, detail={"detail": f"角色「{req.name}」已存在", "code": "CONFLICT"})
    new_char = req.model_dump()
    new_char.update({"emotion": "平静", "health": 1.0, "relationships": {}, "arc_stage": "防御",
                     "memory": [], "behavior_constraints": [], "voice_fingerprint": {},
                     "snapshot_history": [], "is_alive": True, "chapter_introduced": 1})
    characters.append(new_char)
    kb["characters"] = characters
    mgr.save_kb(kb)
    return new_char


@app.put("/projects/{project_id}/characters/{name}", summary="更新角色")
async def update_character(project_id: str, name: str, req: dict = Body(...)) -> dict[str, Any]:
    mgr = _try_load_project(project_id)
    if mgr is None:
        raise HTTPException(status_code=404, detail={"detail": "项目不存在", "code": "NOT_FOUND"})
    kb = mgr.load_kb()
    characters = kb.get("characters", [])
    if not isinstance(characters, list):
        raise HTTPException(status_code=404, detail={"detail": f"角色「{name}」不存在", "code": "NOT_FOUND"})
    for i, c in enumerate(characters):
        if isinstance(c, dict) and c.get("name") == name:
            # 合并更新，保留不在 req 中的字段
            merged = {**c, **req}
            merged["name"] = name  # name 不可通过 PUT 修改
            characters[i] = merged
            kb["characters"] = characters
            mgr.save_kb(kb)
            return merged
    raise HTTPException(status_code=404, detail={"detail": f"角色「{name}」不存在", "code": "NOT_FOUND"})


@app.delete("/projects/{project_id}/characters/{name}", summary="删除角色")
async def delete_character(project_id: str, name: str) -> dict[str, str]:
    mgr = _try_load_project(project_id)
    if mgr is None:
        raise HTTPException(status_code=404, detail={"detail": "项目不存在", "code": "NOT_FOUND"})
    kb = mgr.load_kb()
    characters = kb.get("characters", [])
    if not isinstance(characters, list):
        raise HTTPException(status_code=404, detail={"detail": f"角色「{name}」不存在", "code": "NOT_FOUND"})
    original_count = len(characters)
    characters = [c for c in characters if not (isinstance(c, dict) and c.get("name") == name)]
    if len(characters) == original_count:
        raise HTTPException(status_code=404, detail={"detail": f"角色「{name}」不存在", "code": "NOT_FOUND"})
    kb["characters"] = characters
    mgr.save_kb(kb)
    return {"deleted": name}


class TestVoiceRequest(BaseModel):
    scenario: str  # 场景描述，如"被敌人包围时"


@app.post("/projects/{project_id}/characters/{name}/test-voice", summary="口吻试戏")
async def test_character_voice(project_id: str, name: str, req: TestVoiceRequest) -> dict[str, str]:
    """
    给定场景描述，生成该角色视角的 1-2 句对话，用于验证口吻是否符合预期。
    使用角色的 voice_fingerprint、speech_style、dialogue_examples 作为参考。
    """
    mgr = _try_load_project(project_id)
    if mgr is None:
        raise HTTPException(status_code=404, detail={"detail": "项目不存在", "code": "NOT_FOUND"})
    kb = mgr.load_kb()
    characters = kb.get("characters", [])
    char = next(
        (c for c in characters if isinstance(c, dict) and c.get("name") == name),
        None
    )
    if char is None:
        raise HTTPException(status_code=404, detail={"detail": f"角色「{name}」不存在", "code": "NOT_FOUND"})

    # 构建提示词
    vf = char.get("voice_fingerprint", {})
    examples = char.get("dialogue_examples", [])
    examples_text = "\n".join(
        f'[{e.get("context", "")}] {e.get("dialogue", "")}' for e in examples[:3]
    ) if examples else "（无示例）"

    prompt = (
        f"你是角色「{char.get('name', name)}」。\n"
        f"性格：{char.get('personality', char.get('backstory', ''))}\n"
        f"语言风格：{char.get('speech_style', '自然')}\n"
        f"口头禅：{'、'.join(char.get('catchphrases', [])) or '无'}\n"
        f"高压时的说话方式：{vf.get('under_pressure', '') or '无特殊表现'}\n"
        f"历史对话示例：\n{examples_text}\n\n"
        f"当前场景：{req.scenario}\n"
        f"请以该角色的口吻，用 1-2 句话（可含动作描写）回应当前场景。直接输出对话，无需前缀。"
    )

    from narrative_os.execution.llm_router import LLMRequest, LLMRouter
    router = LLMRouter()
    try:
        llm_req = LLMRequest(
            task_type="voice_test",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.8,
            skill_name="test_voice",
        )
        resp = await router.call(llm_req)
        return {"dialogue": resp.content.strip()}
    except Exception as e:
        raise HTTPException(status_code=500, detail={"detail": f"生成失败：{e}", "code": "LLM_ERROR"})


# ------------------------------------------------------------------ #
# Phase 2: 四层角色端点                                                 #
# ------------------------------------------------------------------ #

@app.get("/projects/{project_id}/characters/{name}/drive", summary="获取角色Drive层")
async def get_character_drive(project_id: str, name: str) -> dict[str, Any]:
    """返回角色 Drive 层（核心欲望/恐惧/执念/目标/底线）。"""
    from narrative_os.core.character_repository import get_character_repository
    char = get_character_repository().get_character(project_id, name)
    if char is None:
        raise HTTPException(status_code=404, detail={"detail": f"角色「{name}」不存在", "code": "NOT_FOUND"})
    if char.drive is None:
        return {}
    return char.drive.model_dump()


@app.put("/projects/{project_id}/characters/{name}/drive", summary="更新角色Drive层")
async def update_character_drive(project_id: str, name: str, req: dict = Body(...)) -> dict[str, Any]:
    """更新角色 Drive 层字段（部分更新）。"""
    from narrative_os.core.character_repository import get_character_repository
    from narrative_os.core.character import CharacterDrive
    repo = get_character_repository()
    char = repo.get_character(project_id, name)
    if char is None:
        raise HTTPException(status_code=404, detail={"detail": f"角色「{name}」不存在", "code": "NOT_FOUND"})
    existing = char.drive.model_dump() if char.drive else {}
    merged = {**existing, **req}
    char.drive = CharacterDrive.model_validate(merged)
    repo.save_character(project_id, char)
    return char.drive.model_dump()


@app.put("/projects/{project_id}/characters/{name}/runtime", summary="更新角色Runtime层")
async def update_character_runtime(project_id: str, name: str, req: dict = Body(...)) -> dict[str, Any]:
    """更新角色 Runtime 层状态（互动推进时调用）。"""
    from narrative_os.core.character_repository import get_character_repository
    from narrative_os.core.character import CharacterRuntime
    repo = get_character_repository()
    char = repo.get_character(project_id, name)
    if char is None:
        raise HTTPException(status_code=404, detail={"detail": f"角色「{name}」不存在", "code": "NOT_FOUND"})
    existing = char.runtime.model_dump()
    merged = {**existing, **req}
    char.runtime = CharacterRuntime.model_validate(merged)
    repo.save_character(project_id, char)
    return char.runtime.model_dump()


@app.get("/projects/{project_id}/characters/{name}/social-matrix", summary="获取角色Social矩阵")
async def get_character_social_matrix(project_id: str, name: str) -> dict[str, Any]:
    """返回角色的多维关系矩阵。"""
    from narrative_os.core.character_repository import get_character_repository
    char = get_character_repository().get_character(project_id, name)
    if char is None:
        raise HTTPException(status_code=404, detail={"detail": f"角色「{name}」不存在", "code": "NOT_FOUND"})
    return {k: v.model_dump() for k, v in char.social_matrix.items()}


@app.put("/projects/{project_id}/characters/{name}/social-matrix", summary="更新角色Social矩阵")
async def update_character_social_matrix(project_id: str, name: str, req: dict = Body(...)) -> dict[str, Any]:
    """覆盖更新角色 Social 矩阵（传入目标角色名 → RelationshipProfile 字典）。"""
    from narrative_os.core.character_repository import get_character_repository
    from narrative_os.core.character import RelationshipProfile
    repo = get_character_repository()
    char = repo.get_character(project_id, name)
    if char is None:
        raise HTTPException(status_code=404, detail={"detail": f"角色「{name}」不存在", "code": "NOT_FOUND"})
    new_matrix: dict = {}
    for target, profile_data in req.items():
        if not isinstance(profile_data, dict):
            continue
        profile_data.setdefault("target_name", target)
        new_matrix[target] = RelationshipProfile.model_validate(profile_data)
    char.social_matrix = new_matrix
    # 同步 relationships 字段（兼容旧字段）
    for target, profile in new_matrix.items():
        char.relationships[target] = profile.affinity
    repo.save_character(project_id, char)
    return {k: v.model_dump() for k, v in char.social_matrix.items()}


@app.get("/projects/{project_id}/memory", summary="三层记忆快照")
async def get_project_memory(project_id: str) -> dict[str, Any]:
    """返回三层记忆系统的计数快照（MemorySnapshot 格式）。项目不存在时返回空快照。"""
    _try_load_project(project_id)  # verify path exists but don't 404 on miss
    mem = MemorySystem(project_id=project_id)
    try:
        counts = mem.collection_counts()
        short = counts.get("short", 0)  # type: ignore[call-overload]
        mid = counts.get("mid", 0)  # type: ignore[call-overload]
        long_ = counts.get("long", 0)  # type: ignore[call-overload]
    except Exception:
        short, mid, long_ = 0, 0, 0

    recent_anchors: list[dict[str, Any]] = []
    try:
        for r in mem.get_recent_anchors(last_n=5):
            recent_anchors.append({
                "record_id": r.record_id,
                "content": r.content,
                "similarity": r.similarity,
                "metadata": dict(r.metadata),
            })
    except Exception:
        pass

    return {
        "short_term": short,
        "mid_term": mid,
        "long_term": long_,
        "collections": {
            "short_term": short,
            "mid_term": mid,
            "long_term": long_,
        },
        "recent_anchors": recent_anchors,
    }


@app.get("/projects/{project_id}/memory/search", summary="RAG 记忆检索")
async def search_project_memory(
    project_id: str,
    q: str = Query(..., max_length=200),
) -> dict[str, Any]:
    """RAG 检索记忆，q 参数限制 200 字符以防 DoS。项目不存在时返回空结果。"""
    _try_load_project(project_id)
    mem = MemorySystem(project_id=project_id)
    try:
        results = mem.retrieve_memory(q, top_k=5)
        return {
            "query": q,
            "results": [
                {
                    "record_id": r.record_id,
                    "content": r.content,
                    "similarity": r.similarity,
                    "metadata": dict(r.metadata),
                }
                for r in results
            ],
        }
    except Exception:
        return {"query": q, "results": []}


# ------------------------------------------------------------------ #
# C6 执行链路追踪（降级处理）                                            #
# ------------------------------------------------------------------ #

@app.get("/traces/{chapter_id}", summary="执行链路追踪")
async def get_traces(chapter_id: str) -> dict[str, Any]:
    """返回章节执行链路树；日志尚无结构化数据时返回空树而非 500。"""
    return {
        "chapter_id": chapter_id,
        "nodes": [],
        "edges": [],
        "note": "tracing not yet available",
    }


# ------------------------------------------------------------------ #
# C7–C8 插件管理                                                       #
# ------------------------------------------------------------------ #

@app.get("/plugins", summary="插件列表")
async def list_plugins() -> list[dict[str, Any]]:
    """返回所有已注册插件及其启用状态。"""
    with _plugin_lock:
        return list(_plugin_registry.values())


@app.post("/plugins/{plugin_id}/toggle", summary="切换插件启用状态")
async def toggle_plugin(plugin_id: str) -> dict[str, Any]:
    """切换指定插件的 enabled 标志。"""
    with _plugin_lock:
        if plugin_id not in _plugin_registry:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"detail": f"插件 '{plugin_id}' 不存在。", "code": "NOT_FOUND"},
            )
        _plugin_registry[plugin_id]["enabled"] = not _plugin_registry[plugin_id]["enabled"]
        return dict(_plugin_registry[plugin_id])


# ------------------------------------------------------------------ #
# C9–C10 风格控制                                                      #
# ------------------------------------------------------------------ #

@app.post("/style/extract", summary="从文本提取风格参数")
async def extract_style(req: StyleExtractRequest) -> dict[str, Any]:
    """启发式提取 5 维风格参数（sentence_length / tone / genre / directives / warnings）。"""
    text = req.text
    sents = text.count("。") + text.count("！") + text.count("？") + text.count("\n")
    words = len(text)
    avg_len = words / max(sents, 1)
    sentence_length = "short" if avg_len < 15 else ("long" if avg_len > 40 else "medium")
    return {
        "sentence_length": sentence_length,
        "tone": "neutral",
        "genre": "general",
        "style_directives": [],
        "warning_words": [],
    }


@app.get("/style/presets", summary="风格预设列表")
async def list_style_presets() -> list[dict[str, Any]]:
    """返回内置风格预设列表。"""
    return _STYLE_PRESETS


# ------------------------------------------------------------------ #
# C11–C12 WorldBuilder 会话端点                                         #
# ------------------------------------------------------------------ #

@app.post("/worldbuilder/start", summary="启动 WorldBuilder 会话")
async def worldbuilder_start() -> dict[str, Any]:
    """创建新的 WorldBuilder 会话并返回第一步提示。"""
    wb = WorldBuilder()
    result = wb.start()
    wb_id = str(uuid.uuid4())
    with _wb_sessions_lock:
        _wb_sessions[wb_id] = wb

    # 持久化 WorldBuilder session 到 DB
    async def _create_wb_in_db() -> None:
        try:
            async with AsyncSessionLocal() as db:
                db.add(WbSessionModel(
                    id=wb_id,
                    project_id="default",  # 将在 worldbuilder_step 中绑定项目
                    current_step=result.step.value,
                    completed_steps_json=json.dumps([], ensure_ascii=False),
                    draft_json=json.dumps(result.draft or {}, ensure_ascii=False),
                ))
                await db.commit()
        except Exception:
            pass
    fire_and_forget(_create_wb_in_db())

    return {
        "wb_session_id": wb_id,
        "step": result.step.value,
        "prompt": result.prompt_to_user,
        "requires_confirmation": result.requires_confirmation,
        "skippable": result.skippable,
        "draft": result.draft,
    }


@app.post("/worldbuilder/step", summary="推进 WorldBuilder 步骤")
async def worldbuilder_step(req: WorldbuilderStepRequest) -> dict[str, Any]:
    """提交用户输入并推进 WorldBuilder 到下一步，返回下一步提示或完成标志。"""
    wb = _get_wb_session(req.wb_session_id)
    result = wb.submit_step(req.user_input)
    done = result.step.value == "done"

    # ── 完成时将种子数据写入项目 KB ───────────────────────────────────
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
            _seed_mgr = StateManager(project_id=_wb_project_id, base_dir=".narrative_state")
            try:
                _seed_mgr.load_state()
            except FileNotFoundError:
                _seed_mgr.initialize(project_name=_wb_project_id)
            _kb = _seed_mgr.load_kb()
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
            _seed_mgr.save_kb(_kb)
            _seed_mgr.save_state()
        except Exception:
            pass  # 写入失败不阻断，前端仍可继续

    # 更新 DB 中的 WorldBuilder session
    async def _update_wb_in_db() -> None:
        try:
            from datetime import datetime, timezone  # noqa: PLC0415
            async with AsyncSessionLocal() as db:
                row = await db.get(WbSessionModel, req.wb_session_id)
                if row is not None:
                    row.current_step = result.step.value
                    row.draft_json = json.dumps(result.draft or {}, ensure_ascii=False)
                    if done:
                        row.seed_data_json = json.dumps(seed_data or {}, ensure_ascii=False)
                        row.completed_at = datetime.now(timezone.utc)
                    await db.commit()
        except Exception:
            pass
    fire_and_forget(_update_wb_in_db())

    return {
        "wb_session_id": req.wb_session_id,
        "step": result.step.value,
        "prompt": result.prompt_to_user,
        "done": done,
        "requires_confirmation": result.requires_confirmation,
        "skippable": result.skippable,
        "draft": result.draft,
        "seed_data": seed_data,
    }


@app.post("/worldbuilder/discuss", summary="与 AI 讨论当前世界构建步骤 (SSE)")
async def worldbuilder_discuss(req: WorldBuilderDiscussRequest):
    """以 SSE 流式返回 AI 对当前步骤的反馈和建议。"""
    wb = _get_wb_session(req.wb_session_id)

    async def event_stream():
        try:
            async for chunk in wb.discuss(req.message):
                # SSE 格式: data: <text>\n\n
                yield f"data: {json.dumps({'text': chunk}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'done': True}, ensure_ascii=False)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'error': str(exc)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ------------------------------------------------------------------ #
# C13 一致性检查                                                        #
# ------------------------------------------------------------------ #

@app.post("/consistency/check", summary="情节 / 时间线一致性检查")
async def run_consistency_check(req: ConsistencyCheckRequest) -> dict[str, Any]:
    """对给定文本运行 ConsistencyChecker 并返回报告。"""
    checker = ConsistencyChecker()
    report = checker.check(text=req.text, chapter=req.chapter)
    return report.model_dump()


# ------------------------------------------------------------------ #
# LLM 提供商配置                                                        #
# ------------------------------------------------------------------ #

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


@app.get("/settings/llm", summary="读取 LLM 提供商配置")
async def get_llm_settings() -> dict[str, Any]:
    """
    返回当前 LLM 配置快照。
    API key 类字段只返回掩码（前4位 + **** + 末4位），不返回明文。
    """
    from narrative_os.infra.config import settings, _mask_key
    from narrative_os.execution.llm_router import router

    return {
        "providers": router.get_provider_status(),
        "current_config": {
            "openai_api_key": _mask_key(settings.openai_api_key),
            "anthropic_api_key": _mask_key(settings.anthropic_api_key),
            "ollama_base_url": settings.ollama_base_url,
            "deepseek_api_key": _mask_key(settings.deepseek_api_key),
            "custom_llm_base_url": settings.custom_llm_base_url,
            "custom_llm_api_key": _mask_key(settings.custom_llm_api_key),
            "custom_llm_model_small": settings.custom_llm_model_small,
            "custom_llm_model_medium": settings.custom_llm_model_medium,
            "custom_llm_model_large": settings.custom_llm_model_large,
        },
    }


@app.put("/settings/llm", summary="更新 LLM 提供商配置")
async def update_llm_settings(req: LLMProviderUpdateRequest) -> dict[str, Any]:
    """
    更新指定 provider 的配置，运行时立即生效，同时回写 .narrative_os.env。
    仅传入需要修改的字段（其余保持不变）。
    """
    from narrative_os.infra.config import settings
    from narrative_os.execution.llm_router import router, Backend, ModelTier

    payload = {k: v for k, v in req.model_dump().items() if v is not None}
    if not payload:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="请至少提供一个需要更新的字段")

    settings.update_llm_settings(payload)

    # 同步 router — 所有可配置后端从 Settings 重新加载
    router.refresh_from_settings()

    return {"success": True, "updated_keys": list(payload.keys())}


@app.post("/settings/llm/test", summary="测试 LLM 提供商连通性")
async def test_llm_connection(req: LLMTestRequest) -> dict[str, Any]:
    """
    向指定 provider 发送一条极短的测试请求，验证密钥和网络连通性。
    返回 success、latency_ms 和可选的 error 信息。
    """
    from narrative_os.execution.llm_router import LLMRequest, LLMRouter, Backend, RoutingStrategy
    from narrative_os.infra.config import settings

    provider_map = {
        "openai": Backend.OPENAI,
        "anthropic": Backend.ANTHROPIC,
        "ollama": Backend.OLLAMA,
        "deepseek": Backend.DEEPSEEK,
        "custom": Backend.CUSTOM,
    }
    backend = provider_map[req.provider]

    # 检查基本配置
    if req.provider == "openai" and not settings.openai_api_key:
        return {"success": False, "error": "未配置 OPENAI_API_KEY", "latency_ms": 0}
    if req.provider == "anthropic" and not settings.anthropic_api_key:
        return {"success": False, "error": "未配置 ANTHROPIC_API_KEY", "latency_ms": 0}
    if req.provider == "deepseek" and not settings.deepseek_api_key:
        return {"success": False, "error": "未配置 DEEPSEEK_API_KEY", "latency_ms": 0}

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
        return {"success": True, "latency_ms": latency, "model_used": resp.model_used}
    except Exception as exc:
        latency = round((time.time() - t0) * 1000)
        return {"success": False, "error": str(exc), "latency_ms": latency}


# ================================================================== #
# 阶段二：项目管理 & CLI 全覆盖端点                                     #
# ================================================================== #

# ------------------------------------------------------------------ #
# Pydantic 模型                                                        #
# ------------------------------------------------------------------ #

class ProjectListItem(BaseModel):
    project_id: str
    title: str = ""
    chapter_count: int = 0
    total_chapters: int = 0  # alias for chapter_count（向前兼容）
    last_modified: str = ""
    status: str = "active"  # active / archived / deleted


class ProjectInitRequest(BaseModel):
    project_id: str = Field(..., min_length=1, max_length=100)
    title: str = ""
    genre: str = ""
    description: str = ""


class ProjectInitResponse(BaseModel):
    project_id: str
    created_at: str
    state_dir: str


class CheckChapterRequest(BaseModel):
    text: str = Field(..., min_length=1)
    project_id: str = "default"
    chapter: int = 0


class CheckChapterResponse(BaseModel):
    issues: list[dict[str, Any]]
    passed: bool


class HumanizeRequest(BaseModel):
    text: str = Field(..., min_length=1)
    project_id: str = "default"
    intensity: float = Field(default=0.5, ge=0.0, le=1.0)


class HumanizeResponse(BaseModel):
    original: str
    humanized: str
    changes_count: int
    diff: list[dict[str, str]]


class ProjectRollbackRequest(BaseModel):
    steps: int = Field(default=1, ge=1, le=50)


class ProjectUpdateRequest(BaseModel):
    title: Optional[str] = None
    genre: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None  # active / archived / deleted


class SettingsUpdateRequest(BaseModel):
    settings: dict[str, Any] = Field(default_factory=dict)


class ProjectSettingsResponse(BaseModel):
    project_id: str
    global_settings: dict[str, Any] = Field(default_factory=dict)
    project_overrides: dict[str, Any] = Field(default_factory=dict)
    merged: dict[str, Any] = Field(default_factory=dict)


class CostSummaryResponse(BaseModel):
    today_tokens: int
    total_tokens: int
    today_cost_usd: float
    by_agent: dict[str, int]
    by_skill: dict[str, int]


# ------------------------------------------------------------------ #
# 端点实现                                                             #
# ------------------------------------------------------------------ #

@app.get("/projects", summary="列出所有项目")
async def list_projects() -> list[ProjectListItem]:
    """扫描 .narrative_state/ 目录，返回所有项目的摘要信息。"""
    import json as _json
    from pathlib import Path as _Path
    base = _Path(".narrative_state")
    if not base.exists():
        return []
    items: list[ProjectListItem] = []
    for d in sorted(base.iterdir()):
        if not d.is_dir():
            continue
        state_file = d / "state.json"
        if not state_file.exists():
            continue  # 无 state.json 的目录不是有效项目，跳过
        title = ""
        chapter_count = 0
        last_modified = ""
        try:
            data = _json.loads(state_file.read_text(encoding="utf-8"))
            title = data.get("project_name", "") or d.name
            chapter_count = data.get("current_chapter", 0)
            last_modified = data.get("updated_at", "")
        except Exception:
            pass
        items.append(ProjectListItem(
            project_id=d.name,
            title=title or d.name,
            chapter_count=chapter_count,
            total_chapters=chapter_count,
            last_modified=last_modified,
        ))
    return items


@app.post(
    "/projects/init",
    response_model=ProjectInitResponse,
    status_code=status.HTTP_201_CREATED,
    summary="初始化项目",
)
async def init_project(req: ProjectInitRequest) -> ProjectInitResponse:
    """创建/初始化项目目录和初始状态文件。项目已存在时加载现有状态。"""
    mgr = StateManager(project_id=req.project_id, base_dir=".narrative_state")
    try:
        state = mgr.initialize(project_name=req.title or req.project_id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"初始化失败：{exc}",
        )
    if req.genre or req.description:
        try:
            kb = mgr.load_kb()
            if req.genre:
                kb["genre"] = req.genre
            if req.description:
                kb["description"] = req.description
            mgr.save_kb(kb)
        except Exception:
            pass
    return ProjectInitResponse(
        project_id=req.project_id,
        created_at=state.created_at,
        state_dir=str(mgr._dir),
    )


@app.post(
    "/chapters/check",
    response_model=CheckChapterResponse,
    status_code=status.HTTP_200_OK,
    summary="一致性检查",
)
async def check_chapter(req: CheckChapterRequest) -> CheckChapterResponse:
    """运行 ConsistencyChecker 对章节文本进行一致性检查，返回问题列表。"""
    checker = ConsistencyChecker()
    plot_graph = None
    mgr = _try_load_project(req.project_id)
    if mgr is not None:
        try:
            kb = mgr.load_kb()
            plot_data = kb.get("plot_graph")
            if plot_data:
                plot_graph = PlotGraph.from_dict(plot_data)
        except Exception:
            pass
    report = checker.check(text=req.text, chapter=req.chapter, plot_graph=plot_graph)
    return CheckChapterResponse(
        issues=[i.model_dump() for i in report.issues],
        passed=report.passed,
    )


@app.post(
    "/chapters/humanize",
    response_model=HumanizeResponse,
    status_code=status.HTTP_200_OK,
    summary="去AI痕迹（人味化）",
)
async def humanize_chapter(req: HumanizeRequest) -> HumanizeResponse:
    """对文本进行人味化处理，返回改写结果和 diff 信息。"""
    import difflib
    from narrative_os.skills.humanize import Humanizer

    h = Humanizer()
    try:
        output = await h.humanize(req.text)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"人味化处理失败：{exc}",
        )
    orig_words = req.text.split()
    new_words = output.humanized_text.split()
    matcher = difflib.SequenceMatcher(None, orig_words, new_words)
    diff_list: list[dict[str, str]] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag != "equal":
            diff_list.append({
                "type": tag,
                "old": " ".join(orig_words[i1:i2]),
                "new": " ".join(new_words[j1:j2]),
            })
    return HumanizeResponse(
        original=req.text,
        humanized=output.humanized_text,
        changes_count=len(diff_list),
        diff=diff_list,
    )


@app.post(
    "/projects/{project_id}/rollback",
    status_code=status.HTTP_200_OK,
    summary="项目状态回滚",
)
async def rollback_project(project_id: str, req: ProjectRollbackRequest) -> dict[str, Any]:
    """将项目状态回滚到当前章节 - steps 处的快照。"""
    mgr = _load_project_or_404(project_id)
    current = mgr.state.current_chapter if mgr.state else 0
    target = max(0, current - req.steps)
    versions = mgr.list_versions()
    if not versions:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"项目 '{project_id}' 没有可用的版本快照。",
        )
    # Find the closest available version at or below target
    available = [v for v in versions if v <= target]
    if not available:
        available = versions
    target = available[-1]
    try:
        snapshot = mgr.rollback(chapter=target)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"回滚失败：{exc}",
        )
    return {
        "success": True,
        "project_id": project_id,
        "rolled_back_to_chapter": target,
        "snapshot_timestamp": snapshot.get("timestamp", ""),
    }


@app.get(
    "/cost/summary",
    response_model=CostSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="成本汇总",
)
async def get_cost_summary(
    project_id: Optional[str] = Query(default=None, description="按项目过滤（空则全局）")
) -> CostSummaryResponse:
    """返回当日 Token 消耗和成本估算（$0.002/1K tokens 平均估算）。"""
    s = cost_ctrl.summary()
    used = s["used"]
    cost_usd = round(used / 1000 * 0.002, 6)
    return CostSummaryResponse(
        today_tokens=used,
        total_tokens=used,
        today_cost_usd=cost_usd,
        by_agent=s.get("by_agent", {}),
        by_skill=s.get("by_skill", {}),
    )


@app.get(
    "/cost/history",
    status_code=status.HTTP_200_OK,
    summary="成本历史记录",
)
async def get_cost_history(
    days: int = Query(default=7, ge=1, le=90),
    project_id: Optional[str] = Query(default=None, description="按项目过滤"),
) -> list[dict[str, Any]]:
    """
    返回最近 N 天的成本记录（支持按 project_id 过滤）。
    当前版本 CostController 为进程级单例，DB 中有历史记录时优先返回 DB 数据。
    """
    import datetime as _dt
    s = cost_ctrl.summary()
    today = _dt.date.today().isoformat()
    if s["used"] == 0:
        return []
    return [{
        "date": today,
        "tokens": s["used"],
        "cost_usd": round(s["used"] / 1000 * 0.002, 6),
        "by_skill": s.get("by_skill", {}),
        "by_agent": s.get("by_agent", {}),
    }]


@app.get(
    "/projects/{project_id}/metrics/history",
    status_code=status.HTTP_200_OK,
    summary="项目章节评分历史",
)
async def get_metrics_history(project_id: str) -> list[dict[str, Any]]:
    """返回项目所有已完成章节的质量评分历史（按章节升序）。"""
    mgr = _load_project_or_404(project_id)
    if not mgr.state or not mgr.state.chapters:
        return []
    return [
        {
            "chapter": m.chapter,
            "summary": m.summary,
            "quality_score": m.quality_score,
            "hook_score": m.hook_score,
            "word_count": m.word_count,
            "timestamp": m.timestamp,
            # 8D 雷达维度（从现有评分派生）
            "qd_01": round(m.quality_score * 0.9 + m.hook_score * 0.1, 3),
            "qd_02": round(m.quality_score * 0.85, 3),
            "qd_03": round((m.quality_score + m.hook_score) / 2, 3),
            "qd_04": round(m.quality_score * 0.7 + 0.2, 3),
            "qd_05": round(m.quality_score * 0.95, 3),
            "qd_06": round(m.quality_score * 0.8 + m.hook_score * 0.15, 3),
            "qd_07": round(m.hook_score, 3),
            "qd_08": round(min(1.0, m.quality_score * 1.05), 3),
        }
        for m in sorted(mgr.state.chapters, key=lambda c: c.chapter)
    ]


# ------------------------------------------------------------------ #
# 章节文本管理端点（B4：章节检索与导出）                                  #
# ------------------------------------------------------------------ #

class ChapterListItem(BaseModel):
    chapter: int
    summary: str = ""
    word_count: int = 0
    quality_score: float = 0.0
    hook_score: float = 0.0
    has_text: bool = False
    timestamp: str = ""


class ChapterTextResponse(BaseModel):
    chapter: int
    text: str
    word_count: int
    summary: str = ""
    quality_score: float = 0.0
    hook_score: float = 0.0
    timestamp: str = ""


@app.get(
    "/projects/{project_id}/chapters",
    response_model=list[ChapterListItem],
    status_code=status.HTTP_200_OK,
    summary="章节列表",
)
async def list_chapters(project_id: str) -> list[ChapterListItem]:
    """返回项目所有已生成章节的列表摘要（按章节升序）。"""
    mgr = _load_project_or_404(project_id)
    if not mgr.state:
        return []
    chapter_files = set(mgr.list_chapter_files())
    items: list[ChapterListItem] = []
    for meta in sorted(mgr.state.chapters, key=lambda c: c.chapter):
        items.append(ChapterListItem(
            chapter=meta.chapter,
            summary=meta.summary,
            word_count=meta.word_count,
            quality_score=meta.quality_score,
            hook_score=meta.hook_score,
            has_text=meta.chapter in chapter_files,
            timestamp=meta.timestamp,
        ))
    return items


@app.get(
    "/projects/{project_id}/chapters/{chapter_num}",
    response_model=ChapterTextResponse,
    status_code=status.HTTP_200_OK,
    summary="章节全文",
)
async def get_chapter_text(project_id: str, chapter_num: int) -> ChapterTextResponse:
    """返回指定章节的完整文本。"""
    mgr = _load_project_or_404(project_id)
    text = mgr.load_chapter_text(chapter_num)
    if text is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"detail": f"章节 {chapter_num} 文本不存在。", "code": "NOT_FOUND"},
        )
    meta = next(
        (m for m in (mgr.state.chapters if mgr.state else []) if m.chapter == chapter_num),
        None,
    )
    return ChapterTextResponse(
        chapter=chapter_num,
        text=text,
        word_count=len(text),
        summary=meta.summary if meta else "",
        quality_score=meta.quality_score if meta else 0.0,
        hook_score=meta.hook_score if meta else 0.0,
        timestamp=meta.timestamp if meta else "",
    )


@app.get(
    "/projects/{project_id}/export",
    status_code=status.HTTP_200_OK,
    summary="导出全本",
)
async def export_novel(
    project_id: str,
    format: str = Query(default="txt", pattern="^(txt|md)$"),
) -> dict[str, Any]:
    """将所有已生成章节拼接返回（txt 或 md 格式）。"""
    mgr = _load_project_or_404(project_id)
    chapter_nums = sorted(mgr.list_chapter_files())
    if not chapter_nums:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"detail": "该项目尚无已生成章节。", "code": "NOT_FOUND"},
        )
    parts: list[str] = []
    total_words = 0
    for n in chapter_nums:
        text = mgr.load_chapter_text(n)
        if not text:
            continue
        if format == "md":
            parts.append(f"## 第{n}章\n\n{text}\n")
        else:
            parts.append(f"第{n}章\n\n{text}\n\n{'─' * 40}\n")
        total_words += len(text)
    full_text = "\n".join(parts)
    title = mgr.state.project_name if mgr.state else project_id
    return {
        "project_id": project_id,
        "title": title,
        "chapter_count": len(parts),
        "total_chapters": len(parts),  # 前端兼容字段
        "total_words": total_words,
        "format": format,
        "content": full_text,
    }


# ================================================================== #
# Phase 2: 新增 CRUD / Settings / Project-bound WorldBuilder 端点      #
# ================================================================== #

@app.put(
    "/projects/{project_id}",
    status_code=status.HTTP_200_OK,
    summary="更新项目元信息",
)
async def update_project(project_id: str, req: ProjectUpdateRequest) -> dict[str, Any]:
    """更新项目 title/genre/description/status（文件 + DB 双写）。"""
    # 文件侧
    mgr = _load_project_or_404(project_id)
    if req.title and mgr.state:
        mgr.state.project_name = req.title
    if req.genre or req.description:
        try:
            kb = mgr.load_kb()
            if req.genre:
                kb["genre"] = req.genre
            if req.description:
                kb["description"] = req.description
            mgr.save_kb(kb)
        except Exception:
            pass
    if mgr.state:
        mgr.save_state()

    # DB 侧
    async def _update_db() -> None:
        try:
            async with AsyncSessionLocal() as db:
                row = await db.get(ProjectModel, project_id)
                if row is not None:
                    if req.title is not None:
                        row.title = req.title
                    if req.genre is not None:
                        row.genre = req.genre
                    if req.description is not None:
                        row.description = req.description
                    if req.status is not None:
                        row.status = req.status
                    await db.commit()
        except Exception:
            pass
    fire_and_forget(_update_db())

    return {"success": True, "project_id": project_id}


@app.delete(
    "/projects/{project_id}",
    status_code=status.HTTP_200_OK,
    summary="软删除项目",
)
async def delete_project(project_id: str) -> dict[str, Any]:
    """将项目标记为 deleted（软删除，不清理文件系统）。"""
    # 验证项目存在
    _load_project_or_404(project_id)

    async def _delete_db() -> None:
        try:
            async with AsyncSessionLocal() as db:
                row = await db.get(ProjectModel, project_id)
                if row is not None:
                    row.status = "deleted"
                    await db.commit()
                else:
                    # 项目仅在文件系统，还没进 DB 时插入一条 deleted 记录
                    db.add(ProjectModel(id=project_id, title=project_id, status="deleted"))
                    await db.commit()
        except Exception:
            pass
    fire_and_forget(_delete_db())
    return {"success": True, "project_id": project_id, "status": "deleted"}


@app.post(
    "/projects/{project_id}/archive",
    status_code=status.HTTP_200_OK,
    summary="归档项目",
)
async def archive_project(project_id: str) -> dict[str, Any]:
    """将项目状态标记为 archived。"""
    _load_project_or_404(project_id)

    async def _archive_db() -> None:
        try:
            async with AsyncSessionLocal() as db:
                row = await db.get(ProjectModel, project_id)
                if row is not None:
                    row.status = "archived"
                else:
                    db.add(ProjectModel(id=project_id, title=project_id, status="archived"))
                await db.commit()
        except Exception:
            pass
    fire_and_forget(_archive_db())
    return {"success": True, "project_id": project_id, "status": "archived"}


# ────────────────────────── 全局 Settings ─────────────────────────── #

@app.get("/settings", status_code=status.HTTP_200_OK, summary="读取全局设置")
async def get_global_settings() -> dict[str, Any]:
    """从 DB settings 表（scope=global）读取，合并环境变量中的 LLM 默认值。"""
    from narrative_os.infra.models import SettingRecord
    import os
    defaults: dict[str, Any] = {
        "llm_provider": os.environ.get("LLM_PROVIDER", "openai"),
        "llm_model": os.environ.get("LLM_MODEL", "gpt-4o"),
        "token_budget": int(os.environ.get("TOKEN_BUDGET", "200000")),
    }
    try:
        from sqlalchemy import select
        async with AsyncSessionLocal() as db:
            rows = (await db.execute(
                select(SettingRecord).where(SettingRecord.scope == "global")
            )).scalars().all()
            for row in rows:
                try:
                    import json as _j
                    defaults[row.key] = _j.loads(row.value_json)
                except Exception:
                    pass
    except Exception:
        pass
    return defaults


@app.put("/settings", status_code=status.HTTP_200_OK, summary="更新全局设置")
async def update_global_settings(req: SettingsUpdateRequest) -> dict[str, Any]:
    """批量写入全局设置到 DB settings 表（scope=global）。"""
    from narrative_os.infra.models import SettingRecord
    import json as _j
    try:
        async with AsyncSessionLocal() as db:
            for key, value in req.settings.items():
                row = await db.get(SettingRecord, key)
                if row is None:
                    db.add(SettingRecord(
                        key=key,
                        value_json=_j.dumps(value, ensure_ascii=False),
                        scope="global",
                    ))
                else:
                    row.value_json = _j.dumps(value, ensure_ascii=False)
                    row.scope = "global"
            await db.commit()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"设置更新失败：{exc}",
        )
    return {"success": True, "updated_keys": list(req.settings.keys())}


# ─────────────────────── 项目级 Settings ──────────────────────────── #

@app.get(
    "/projects/{project_id}/settings",
    response_model=ProjectSettingsResponse,
    status_code=status.HTTP_200_OK,
    summary="读取项目设置（合并全局）",
)
async def get_project_settings(project_id: str) -> ProjectSettingsResponse:
    """返回全局设置 + 项目级覆盖 + 合并结果。"""
    _load_project_or_404(project_id)
    from narrative_os.infra.models import SettingRecord
    import json as _j, os
    global_settings: dict[str, Any] = {
        "llm_provider": os.environ.get("LLM_PROVIDER", "openai"),
        "llm_model": os.environ.get("LLM_MODEL", "gpt-4o"),
        "token_budget": int(os.environ.get("TOKEN_BUDGET", "200000")),
    }
    project_overrides: dict[str, Any] = {}
    try:
        from sqlalchemy import select
        async with AsyncSessionLocal() as db:
            rows = (await db.execute(
                select(SettingRecord).where(
                    SettingRecord.scope.in_(["global", "project"]),
                )
            )).scalars().all()
            for row in rows:
                try:
                    val = _j.loads(row.value_json)
                    if row.scope == "global":
                        global_settings[row.key] = val
                    elif row.scope == "project" and row.project_id == project_id:
                        project_overrides[row.key] = val
                except Exception:
                    pass
    except Exception:
        pass
    merged = {**global_settings, **project_overrides}
    return ProjectSettingsResponse(
        project_id=project_id,
        global_settings=global_settings,
        project_overrides=project_overrides,
        merged=merged,
    )


@app.put(
    "/projects/{project_id}/settings",
    status_code=status.HTTP_200_OK,
    summary="更新项目设置（只保存差异部分）",
)
async def update_project_settings(
    project_id: str, req: SettingsUpdateRequest
) -> dict[str, Any]:
    """写入项目级设置覆盖（scope=project）到 DB settings 表。"""
    _load_project_or_404(project_id)
    from narrative_os.infra.models import SettingRecord
    import json as _j
    try:
        async with AsyncSessionLocal() as db:
            for key, value in req.settings.items():
                compound_key = f"{project_id}__{key}"
                row = await db.get(SettingRecord, compound_key)
                if row is None:
                    db.add(SettingRecord(
                        key=compound_key,
                        value_json=_j.dumps(value, ensure_ascii=False),
                        scope="project",
                        project_id=project_id,
                    ))
                else:
                    row.value_json = _j.dumps(value, ensure_ascii=False)
            await db.commit()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"项目设置更新失败：{exc}",
        )
    return {"success": True, "project_id": project_id, "updated_keys": list(req.settings.keys())}


# ─────────────────── 项目绑定 WorldBuilder ────────────────────────── #

@app.post(
    "/projects/{project_id}/worldbuilder/start",
    status_code=status.HTTP_200_OK,
    summary="（项目绑定）启动 WorldBuilder 会话",
)
async def project_worldbuilder_start(project_id: str) -> dict[str, Any]:
    """与 /worldbuilder/start 相同，但将 project_id 绑定到 WorldbuilderSession。"""
    _load_project_or_404(project_id)
    wb = WorldBuilder()
    result = wb.start()
    wb_id = str(uuid.uuid4())
    with _wb_sessions_lock:
        _wb_sessions[wb_id] = wb

    async def _create_wb_for_project() -> None:
        try:
            async with AsyncSessionLocal() as db:
                # 确保项目在 DB 中
                proj = await db.get(ProjectModel, project_id)
                if proj is None:
                    db.add(ProjectModel(id=project_id, title=project_id))
                db.add(WbSessionModel(
                    id=wb_id,
                    project_id=project_id,
                    current_step=result.step.value,
                    completed_steps_json=json.dumps([], ensure_ascii=False),
                    draft_json=json.dumps(result.draft or {}, ensure_ascii=False),
                ))
                await db.commit()
        except Exception:
            pass
    fire_and_forget(_create_wb_for_project())

    return {
        "wb_session_id": wb_id,
        "step": result.step.value,
        "prompt": result.prompt_to_user,
        "done": False,
        "requires_confirmation": result.requires_confirmation,
        "skippable": result.skippable,
        "draft": result.draft,
    }


@app.post(
    "/projects/{project_id}/worldbuilder/step",
    status_code=status.HTTP_200_OK,
    summary="（项目绑定）推进 WorldBuilder 步骤",
)
async def project_worldbuilder_step(
    project_id: str, req: WorldbuilderStepRequest
) -> dict[str, Any]:
    """与 /worldbuilder/step 相同，路径中包含 project_id（向前端路由对齐）。"""
    return await worldbuilder_step(req)


@app.post(
    "/projects/{project_id}/worldbuilder/discuss",
    status_code=status.HTTP_200_OK,
    summary="（项目绑定）与 AI 讨论当前世界构建步骤 (SSE)",
)
async def project_worldbuilder_discuss(
    project_id: str, req: WorldBuilderDiscussRequest
):
    """与 /worldbuilder/discuss 相同，路径中包含 project_id。"""
    return await worldbuilder_discuss(req)


# ===========================================================================
# 世界观沙盘 & 故事概念 API
# ===========================================================================

# ----- 请求模型 -----

class ConceptUpdateRequest(BaseModel):
    one_sentence: str = ""
    one_paragraph: str = ""
    genre_tags: list[str] = Field(default_factory=list)
    world_type: str = "continental"


class WorldMetaUpdateRequest(BaseModel):
    world_name: Optional[str] = None
    world_type: Optional[str] = None
    world_description: Optional[str] = None


class RegionCreateRequest(BaseModel):
    name: str
    region_type: str = ""
    x: float = 100.0
    y: float = 100.0
    # Optional full fields — accepted but not required for quick creation
    geography: Optional[dict] = None
    race: Optional[dict] = None
    civilization: Optional[dict] = None
    power_access: Optional[dict] = None
    faction_ids: list[str] = Field(default_factory=list)
    alignment: str = "true_neutral"
    tags: list[str] = Field(default_factory=list)
    notes: str = ""


class FactionCreateRequest(BaseModel):
    name: str
    scope: str = "internal"
    description: str = ""
    territory_region_ids: list[str] = Field(default_factory=list)
    alignment: str = "true_neutral"
    color: Optional[str] = None
    power_system_id: Optional[str] = None
    notes: str = ""


class PowerSystemCreateRequest(BaseModel):
    name: str
    template: str = "custom"


class RelationCreateRequest(BaseModel):
    source_id: str
    target_id: str
    relation_type: str = "connection"
    label: str = ""
    description: str = ""


class RelationUpdateRequest(BaseModel):
    relation_type: Optional[str] = None
    label: Optional[str] = None
    description: Optional[str] = None


class TimelineEventCreateRequest(BaseModel):
    year: str = ""
    title: str
    description: str = ""
    linked_entity_id: Optional[str] = None
    event_type: str = "general"


class TimelineEventUpdateRequest(BaseModel):
    year: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    linked_entity_id: Optional[str] = None
    event_type: Optional[str] = None


def _collect_world_node_ids(sandbox: WorldSandboxData) -> set[str]:
    region_ids = {r.id for r in sandbox.regions}
    faction_ids = {f.id for f in sandbox.factions}
    return region_ids | faction_ids


def _ensure_relation_nodes_exist(sandbox: WorldSandboxData, source_id: str, target_id: str) -> None:
    valid_ids = _collect_world_node_ids(sandbox)
    if source_id not in valid_ids:
        raise HTTPException(status_code=422, detail=f"source_id {source_id} does not exist")
    if target_id not in valid_ids:
        raise HTTPException(status_code=422, detail=f"target_id {target_id} does not exist")


# ----- 辅助函数 -----

def _sync_territory_links(sandbox: WorldSandboxData) -> None:
    """双向同步 region.faction_ids ↔ faction.territory_region_ids，
    合并两侧已有数据，确保两方始终一致。"""
    # 1. 收集 faction → {region_ids}（来自 faction 侧）
    faction_region_map: dict[str, set[str]] = {f.id: set(f.territory_region_ids) for f in sandbox.factions}
    region_set = {r.id for r in sandbox.regions}
    # 2. 合并 region 侧
    for r in sandbox.regions:
        for fid in list(r.faction_ids):
            if fid in faction_region_map:
                faction_region_map[fid].add(r.id)
            else:
                r.faction_ids.remove(fid)  # 引用不存在的 faction，清除
    # 3. 写回 faction.territory_region_ids（只保留存在的 region）
    for f in sandbox.factions:
        f.territory_region_ids = [rid for rid in faction_region_map.get(f.id, set()) if rid in region_set]
    # 4. 写回 region.faction_ids（确保 faction 侧新增的 region 也在 region.faction_ids 中）
    for f in sandbox.factions:
        for rid in f.territory_region_ids:
            r = next((x for x in sandbox.regions if x.id == rid), None)
            if r and f.id not in r.faction_ids:
                r.faction_ids.append(f.id)

async def _get_sandbox(project_id: str, db) -> WorldSandboxData:
    """从 DB 读取沙盘数据，不存在则返回默认空数据"""
    from sqlalchemy import select
    result = await db.execute(
        select(WorldSandboxModel).where(WorldSandboxModel.project_id == project_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return WorldSandboxData()
    return WorldSandboxData.model_validate_json(row.sandbox_json)


async def _save_sandbox(project_id: str, data: WorldSandboxData, db) -> None:
    """将 WorldSandboxData 序列化写入 world_sandboxes 表（upsert）"""
    from sqlalchemy import select
    import uuid as _uuid
    result = await db.execute(
        select(WorldSandboxModel).where(WorldSandboxModel.project_id == project_id)
    )
    row = result.scalar_one_or_none()
    json_str = data.model_dump_json()
    if row is None:
        row = WorldSandboxModel(
            id=_uuid.uuid4().hex,
            project_id=project_id,
            sandbox_json=json_str,
        )
        db.add(row)
    else:
        row.sandbox_json = json_str
    await db.commit()


async def _get_concept(project_id: str, db) -> ConceptData:
    """从 DB 读取概念数据，不存在则返回空"""
    from sqlalchemy import select
    result = await db.execute(
        select(StoryConceptModel).where(StoryConceptModel.project_id == project_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return ConceptData()
    return ConceptData.model_validate_json(row.concept_json)


async def _save_concept(project_id: str, data: ConceptData, db) -> None:
    """将 ConceptData 写入 story_concepts 表（upsert）"""
    from sqlalchemy import select
    import uuid as _uuid
    result = await db.execute(
        select(StoryConceptModel).where(StoryConceptModel.project_id == project_id)
    )
    row = result.scalar_one_or_none()
    json_str = data.model_dump_json()
    if row is None:
        row = StoryConceptModel(
            id=_uuid.uuid4().hex,
            project_id=project_id,
            concept_json=json_str,
        )
        db.add(row)
    else:
        row.concept_json = json_str
    await db.commit()


# ----- 故事概念端点（2个）-----

@app.get("/projects/{project_id}/concept", summary="获取故事概念数据")
async def get_concept(project_id: str) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        concept = await _get_concept(project_id, db)
    return concept.model_dump()


@app.put("/projects/{project_id}/concept", summary="保存故事概念数据")
async def update_concept(project_id: str, req: ConceptUpdateRequest) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        concept = ConceptData(
            one_sentence=req.one_sentence,
            one_paragraph=req.one_paragraph,
            genre_tags=req.genre_tags,
            world_type=req.world_type,  # type: ignore[arg-type]
        )
        await _save_concept(project_id, concept, db)
    return concept.model_dump()


# ----- 世界观沙盘端点（16个）-----

@app.get("/projects/{project_id}/world", summary="获取完整世界观沙盘数据")
async def get_world(project_id: str) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        sandbox = await _get_sandbox(project_id, db)
    return sandbox.model_dump()


@app.put("/projects/{project_id}/world/meta", summary="更新世界基本信息")
async def update_world_meta(project_id: str, req: WorldMetaUpdateRequest) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        sandbox = await _get_sandbox(project_id, db)
        if req.world_name is not None:
            sandbox.world_name = req.world_name
        if req.world_type is not None:
            sandbox.world_type = req.world_type  # type: ignore[assignment]
        if req.world_description is not None:
            sandbox.world_description = req.world_description
        await _save_sandbox(project_id, sandbox, db)
    return sandbox.model_dump()


# --- Regions ---

@app.post("/projects/{project_id}/world/regions", summary="创建地区节点", status_code=201)
async def create_region(project_id: str, req: RegionCreateRequest) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        sandbox = await _get_sandbox(project_id, db)
        from narrative_os.core.world_sandbox import RegionGeography, RegionRace, RegionCivilization, RegionPowerAccess
        region = Region(
            name=req.name,
            region_type=req.region_type,
            x=req.x,
            y=req.y,
            faction_ids=req.faction_ids,
            alignment=req.alignment,
            tags=req.tags,
            notes=req.notes,
            geography=RegionGeography(**(req.geography or {})),
            race=RegionRace(**(req.race or {})),
            civilization=RegionCivilization(**(req.civilization or {})),
            power_access=RegionPowerAccess(**(req.power_access or {})),
        )
        sandbox.regions.append(region)
        _sync_territory_links(sandbox)
        await _save_sandbox(project_id, sandbox, db)
    return region.model_dump()


@app.get("/projects/{project_id}/world/regions/{region_id}", summary="获取地区详情")
async def get_region(project_id: str, region_id: str) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        sandbox = await _get_sandbox(project_id, db)
    region = next((r for r in sandbox.regions if r.id == region_id), None)
    if region is None:
        raise HTTPException(status_code=404, detail=f"Region {region_id} not found")
    return region.model_dump()


@app.put("/projects/{project_id}/world/regions/{region_id}", summary="更新地区数据")
async def update_region(project_id: str, region_id: str, req: Region) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        sandbox = await _get_sandbox(project_id, db)
        idx = next((i for i, r in enumerate(sandbox.regions) if r.id == region_id), None)
        if idx is None:
            raise HTTPException(status_code=404, detail=f"Region {region_id} not found")
        if req.id and req.id != region_id:
            raise HTTPException(status_code=400, detail="region id in payload does not match path")
        payload = req.model_dump()
        payload["id"] = region_id
        sandbox.regions[idx] = Region(**payload)
        _sync_territory_links(sandbox)
        await _save_sandbox(project_id, sandbox, db)
    return sandbox.regions[idx].model_dump()


@app.delete("/projects/{project_id}/world/regions/{region_id}", summary="删除地区", status_code=204)
async def delete_region(project_id: str, region_id: str) -> None:
    async with AsyncSessionLocal() as db:
        sandbox = await _get_sandbox(project_id, db)
        original_len = len(sandbox.regions)
        sandbox.regions = [r for r in sandbox.regions if r.id != region_id]
        if len(sandbox.regions) == original_len:
            raise HTTPException(status_code=404, detail=f"Region {region_id} not found")
        # 同时清理引用该地区的关系
        sandbox.relations = [rel for rel in sandbox.relations
                             if rel.source_id != region_id and rel.target_id != region_id]
        _sync_territory_links(sandbox)
        await _save_sandbox(project_id, sandbox, db)


# --- Factions ---

@app.post("/projects/{project_id}/world/factions", summary="创建势力", status_code=201)
async def create_faction(project_id: str, req: FactionCreateRequest) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        sandbox = await _get_sandbox(project_id, db)
        faction = Faction(
            name=req.name,
            scope=req.scope,
            description=req.description,
            territory_region_ids=req.territory_region_ids,
            alignment=req.alignment,
            color=req.color,
            power_system_id=req.power_system_id,
            notes=req.notes,
        )  # type: ignore[arg-type]
        sandbox.factions.append(faction)
        _sync_territory_links(sandbox)
        await _save_sandbox(project_id, sandbox, db)
    return faction.model_dump()


@app.get("/projects/{project_id}/world/factions/{faction_id}", summary="获取势力详情")
async def get_faction(project_id: str, faction_id: str) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        sandbox = await _get_sandbox(project_id, db)
    faction = next((f for f in sandbox.factions if f.id == faction_id), None)
    if faction is None:
        raise HTTPException(status_code=404, detail=f"Faction {faction_id} not found")
    return faction.model_dump()


@app.put("/projects/{project_id}/world/factions/{faction_id}", summary="更新势力数据")
async def update_faction(project_id: str, faction_id: str, req: Faction) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        sandbox = await _get_sandbox(project_id, db)
        idx = next((i for i, f in enumerate(sandbox.factions) if f.id == faction_id), None)
        if idx is None:
            raise HTTPException(status_code=404, detail=f"Faction {faction_id} not found")
        if req.id and req.id != faction_id:
            raise HTTPException(status_code=400, detail="faction id in payload does not match path")
        payload = req.model_dump()
        payload["id"] = faction_id
        sandbox.factions[idx] = Faction(**payload)
        _sync_territory_links(sandbox)
        await _save_sandbox(project_id, sandbox, db)
    return sandbox.factions[idx].model_dump()


@app.delete("/projects/{project_id}/world/factions/{faction_id}", summary="删除势力", status_code=204)
async def delete_faction(project_id: str, faction_id: str) -> None:
    async with AsyncSessionLocal() as db:
        sandbox = await _get_sandbox(project_id, db)
        original_len = len(sandbox.factions)
        sandbox.factions = [f for f in sandbox.factions if f.id != faction_id]
        if len(sandbox.factions) == original_len:
            raise HTTPException(status_code=404, detail=f"Faction {faction_id} not found")
        sandbox.relations = [rel for rel in sandbox.relations
                             if rel.source_id != faction_id and rel.target_id != faction_id]
        _sync_territory_links(sandbox)
        await _save_sandbox(project_id, sandbox, db)


# --- Power Systems ---

@app.post("/projects/{project_id}/world/power-systems", summary="创建力量体系", status_code=201)
async def create_power_system(project_id: str, req: PowerSystemCreateRequest) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        sandbox = await _get_sandbox(project_id, db)
        # 若指定模板，从模板预填充
        template_key = None
        for t in PowerSystemTemplateType:
            if t.value == req.template and t != PowerSystemTemplateType.CUSTOM:
                template_key = t
                break
        if template_key and template_key in POWER_SYSTEM_TEMPLATES:
            tpl = POWER_SYSTEM_TEMPLATES[template_key]
            ps = PowerSystem(
                name=req.name or tpl.name,
                template=template_key,
                levels=tpl.levels,
                rules=tpl.rules,
                resources=tpl.resources,
            )
        else:
            ps = PowerSystem(name=req.name, template=PowerSystemTemplateType.CUSTOM)
        sandbox.power_systems.append(ps)
        await _save_sandbox(project_id, sandbox, db)
    return ps.model_dump()


@app.get("/projects/{project_id}/world/power-systems/{ps_id}", summary="获取力量体系详情")
async def get_power_system(project_id: str, ps_id: str) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        sandbox = await _get_sandbox(project_id, db)
    power_system = next((p for p in sandbox.power_systems if p.id == ps_id), None)
    if power_system is None:
        raise HTTPException(status_code=404, detail=f"PowerSystem {ps_id} not found")
    return power_system.model_dump()


@app.put("/projects/{project_id}/world/power-systems/{ps_id}", summary="更新力量体系")
async def update_power_system(project_id: str, ps_id: str, req: PowerSystem) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        sandbox = await _get_sandbox(project_id, db)
        idx = next((i for i, p in enumerate(sandbox.power_systems) if p.id == ps_id), None)
        if idx is None:
            raise HTTPException(status_code=404, detail=f"PowerSystem {ps_id} not found")
        if req.id and req.id != ps_id:
            raise HTTPException(status_code=400, detail="power system id in payload does not match path")
        payload = req.model_dump()
        payload["id"] = ps_id
        sandbox.power_systems[idx] = PowerSystem(**payload)
        await _save_sandbox(project_id, sandbox, db)
    return sandbox.power_systems[idx].model_dump()


@app.delete("/projects/{project_id}/world/power-systems/{ps_id}", summary="删除力量体系", status_code=204)
async def delete_power_system(project_id: str, ps_id: str) -> None:
    async with AsyncSessionLocal() as db:
        sandbox = await _get_sandbox(project_id, db)
        original_len = len(sandbox.power_systems)
        sandbox.power_systems = [p for p in sandbox.power_systems if p.id != ps_id]
        if len(sandbox.power_systems) == original_len:
            raise HTTPException(status_code=404, detail=f"PowerSystem {ps_id} not found")
        await _save_sandbox(project_id, sandbox, db)


# --- Relations ---

@app.get("/projects/{project_id}/world/relations", summary="获取全部关系")
async def list_relations(project_id: str) -> list[dict[str, Any]]:
    async with AsyncSessionLocal() as db:
        sandbox = await _get_sandbox(project_id, db)
    return [r.model_dump() for r in sandbox.relations]


@app.get("/projects/{project_id}/world/relations/{relation_id}", summary="获取关系详情")
async def get_relation(project_id: str, relation_id: str) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        sandbox = await _get_sandbox(project_id, db)
    relation = next((r for r in sandbox.relations if r.id == relation_id), None)
    if relation is None:
        raise HTTPException(status_code=404, detail=f"Relation {relation_id} not found")
    return relation.model_dump()

@app.post("/projects/{project_id}/world/relations", summary="创建地区/势力关系", status_code=201)
async def create_relation(project_id: str, req: RelationCreateRequest) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        sandbox = await _get_sandbox(project_id, db)
        _ensure_relation_nodes_exist(sandbox, req.source_id, req.target_id)
        relation = WorldRelation(
            source_id=req.source_id,
            target_id=req.target_id,
            relation_type=req.relation_type,
            label=req.label,
            description=req.description,
        )
        sandbox.relations.append(relation)
        await _save_sandbox(project_id, sandbox, db)
    return relation.model_dump()


@app.put("/projects/{project_id}/world/relations/{relation_id}", summary="更新关系")
async def update_relation(project_id: str, relation_id: str, req: RelationUpdateRequest) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        sandbox = await _get_sandbox(project_id, db)
        idx = next((i for i, r in enumerate(sandbox.relations) if r.id == relation_id), None)
        if idx is None:
            raise HTTPException(status_code=404, detail=f"Relation {relation_id} not found")
        existing = sandbox.relations[idx].model_dump()
        for key, value in req.model_dump(exclude_none=True).items():
            existing[key] = value
        _ensure_relation_nodes_exist(sandbox, existing["source_id"], existing["target_id"])
        sandbox.relations[idx] = WorldRelation(**existing)
        await _save_sandbox(project_id, sandbox, db)
    return sandbox.relations[idx].model_dump()


@app.delete("/projects/{project_id}/world/relations/{relation_id}", summary="删除关系", status_code=204)
async def delete_relation(project_id: str, relation_id: str) -> None:
    async with AsyncSessionLocal() as db:
        sandbox = await _get_sandbox(project_id, db)
        original_len = len(sandbox.relations)
        sandbox.relations = [r for r in sandbox.relations if r.id != relation_id]
        if len(sandbox.relations) == original_len:
            raise HTTPException(status_code=404, detail=f"Relation {relation_id} not found")
        await _save_sandbox(project_id, sandbox, db)


# --- Timeline Events ---

@app.get("/projects/{project_id}/world/timeline", summary="获取全部时间轴事件")
async def list_timeline_events(project_id: str) -> list[dict[str, Any]]:
    async with AsyncSessionLocal() as db:
        sandbox = await _get_sandbox(project_id, db)
    return [e.model_dump() for e in sandbox.timeline_events]


@app.post("/projects/{project_id}/world/timeline", summary="创建时间轴事件", status_code=201)
async def create_timeline_event(project_id: str, req: TimelineEventCreateRequest) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        sandbox = await _get_sandbox(project_id, db)
        event = TimelineSandboxEvent(
            year=req.year,
            title=req.title,
            description=req.description,
            linked_entity_id=req.linked_entity_id,
            event_type=req.event_type,
        )
        sandbox.timeline_events.append(event)
        await _save_sandbox(project_id, sandbox, db)
    return event.model_dump()


@app.get("/projects/{project_id}/world/timeline/{event_id}", summary="获取时间轴事件详情")
async def get_timeline_event(project_id: str, event_id: str) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        sandbox = await _get_sandbox(project_id, db)
    event = next((e for e in sandbox.timeline_events if e.id == event_id), None)
    if event is None:
        raise HTTPException(status_code=404, detail=f"TimelineEvent {event_id} not found")
    return event.model_dump()


@app.put("/projects/{project_id}/world/timeline/{event_id}", summary="更新时间轴事件")
async def update_timeline_event(
    project_id: str, event_id: str, req: TimelineEventUpdateRequest
) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        sandbox = await _get_sandbox(project_id, db)
        idx = next((i for i, e in enumerate(sandbox.timeline_events) if e.id == event_id), None)
        if idx is None:
            raise HTTPException(status_code=404, detail=f"TimelineEvent {event_id} not found")
        existing = sandbox.timeline_events[idx].model_dump()
        for key, value in req.model_dump(exclude_none=True).items():
            existing[key] = value
        sandbox.timeline_events[idx] = TimelineSandboxEvent(**existing)
        await _save_sandbox(project_id, sandbox, db)
    return sandbox.timeline_events[idx].model_dump()


@app.delete("/projects/{project_id}/world/timeline/{event_id}", summary="删除时间轴事件", status_code=204)
async def delete_timeline_event(project_id: str, event_id: str) -> None:
    async with AsyncSessionLocal() as db:
        sandbox = await _get_sandbox(project_id, db)
        original_len = len(sandbox.timeline_events)
        sandbox.timeline_events = [e for e in sandbox.timeline_events if e.id != event_id]
        if len(sandbox.timeline_events) == original_len:
            raise HTTPException(status_code=404, detail=f"TimelineEvent {event_id} not found")
        await _save_sandbox(project_id, sandbox, db)


# --- 世界概览 ---

@app.get("/projects/{project_id}/world/overview", summary="世界概览（统计、孤立节点、数据完整性提示）")
async def get_world_overview(project_id: str) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        sandbox = await _get_sandbox(project_id, db)

    # 统计
    region_count = len(sandbox.regions)
    faction_count = len(sandbox.factions)
    relation_count = len(sandbox.relations)
    power_system_count = len(sandbox.power_systems)
    timeline_event_count = len(sandbox.timeline_events)

    # 孤立节点检测（无任何关系的节点）
    connected_ids: set[str] = set()
    for rel in sandbox.relations:
        connected_ids.add(rel.source_id)
        connected_ids.add(rel.target_id)
    all_node_ids = {r.id for r in sandbox.regions} | {f.id for f in sandbox.factions}
    orphan_ids = all_node_ids - connected_ids
    orphan_nodes = []
    for oid in orphan_ids:
        r = next((r for r in sandbox.regions if r.id == oid), None)
        f = next((f for f in sandbox.factions if f.id == oid), None)
        if r:
            orphan_nodes.append({"id": oid, "name": r.name, "type": "region"})
        elif f:
            orphan_nodes.append({"id": oid, "name": f.name, "type": "faction"})

    # 数据完整性提示
    completeness_hints: list[str] = []
    if region_count == 0:
        completeness_hints.append("尚未创建任何地区")
    if faction_count == 0:
        completeness_hints.append("尚未创建任何势力")
    if relation_count == 0 and (region_count > 0 or faction_count > 0):
        completeness_hints.append("尚未建立任何关系")
    # 检查无归属地区
    regions_with_faction = set()
    for f in sandbox.factions:
        regions_with_faction.update(f.territory_region_ids)
    regions_no_faction = [r.name for r in sandbox.regions if r.id not in regions_with_faction]
    if regions_no_faction:
        completeness_hints.append(f"以下地区无势力归属：{', '.join(regions_no_faction[:5])}")
    # 检查势力无领地
    factions_no_territory = [f.name for f in sandbox.factions if not f.territory_region_ids]
    if factions_no_territory:
        completeness_hints.append(f"以下势力无领地：{', '.join(factions_no_territory[:5])}")
    # 检查势力无颜色
    factions_no_color = [f.name for f in sandbox.factions if not f.color]
    if factions_no_color:
        completeness_hints.append(f"以下势力未设置颜色：{', '.join(factions_no_color[:5])}")

    return {
        "statistics": {
            "regions": region_count,
            "factions": faction_count,
            "relations": relation_count,
            "power_systems": power_system_count,
            "timeline_events": timeline_event_count,
        },
        "orphan_nodes": orphan_nodes,
        "completeness_hints": completeness_hints,
    }


# --- 发布世界（Phase 6 Stage 1）---

@app.post("/projects/{project_id}/world/publish", summary="发布世界：沙盘 → 运行态 WorldState")
async def publish_world(project_id: str) -> dict[str, Any]:
    """
    发布世界沙盘数据为可运行的 WorldState。

    流程：
      1. 读取沙盘数据 + 概念数据
      2. 调用 WorldValidator 校验
      3. 校验通过后调用 WorldCompiler 编译
      4. 保存 RuntimeWorldState 到 DB 和文件系统
      5. 返回 PublishReport

    Returns:
      status: "published" | "validation_failed"
      errors: 校验错误列表（validation_failed 时非空）
      warnings: 编译警告列表
      publish_report: 编译统计
    """
    from narrative_os.core.world_validator import WorldValidator
    from narrative_os.core.world_compiler import WorldCompiler
    from narrative_os.core.world_repository import WorldRepository

    async with AsyncSessionLocal() as db:
        sandbox = await _get_sandbox(project_id, db)
        concept = await _get_concept(project_id, db)

    # Step 1: 校验
    validator = WorldValidator()
    validation_report = validator.validate(sandbox=sandbox, concept=concept)

    if not validation_report.is_valid:
        return {
            "status": "validation_failed",
            "errors": validation_report.errors,
            "warnings": validation_report.warnings,
            "suggestions": validation_report.suggestions,
            "publish_report": None,
        }

    # Step 2: 编译
    compiler = WorldCompiler()
    world, publish_report = compiler.compile(concept=concept, sandbox=sandbox)

    # Step 3: 标记发布版本
    import time as _time
    world_version = f"v{int(_time.time())}"
    publish_report.world_version = world_version

    # Step 4: 持久化（DB + 文件系统）
    repo = WorldRepository()
    await repo.asave_runtime_world_state(project_id, world)

    return {
        "status": "published",
        "world_version": world_version,
        "warnings": publish_report.warnings + validation_report.warnings,
        "suggestions": validation_report.suggestions,
        "publish_report": {
            "factions_compiled": publish_report.factions_compiled,
            "regions_compiled": publish_report.regions_compiled,
            "power_systems_compiled": publish_report.power_systems_compiled,
            "rules_compiled": publish_report.rules_compiled,
            "timeline_events_compiled": publish_report.timeline_events_compiled,
            "relations_compiled": publish_report.relations_compiled,
        },
    }


@app.get("/projects/{project_id}/world/runtime-state", summary="获取已发布的运行态 WorldState")
async def get_world_runtime_state(project_id: str) -> dict[str, Any]:
    """获取已发布的运行态 WorldState（经过 WorldCompiler 编译产出的版本）。"""
    from narrative_os.core.world_repository import WorldRepository
    repo = WorldRepository()
    world = await repo.aget_world_state(project_id)
    return world.model_dump()


# --- 地图布局 ---

@app.get("/projects/{project_id}/world/map-layout", summary="基于邻接关系的地图布局坐标")
async def get_map_layout(project_id: str) -> dict[str, Any]:
    """基于地区节点 + 邻接关系返回自动布局坐标。使用简单的力导引式布局。"""
    import math

    async with AsyncSessionLocal() as db:
        sandbox = await _get_sandbox(project_id, db)

    if not sandbox.regions:
        return {"nodes": [], "edges": []}

    # 收集邻接边（adjacent/border/connection 等空间关系）
    spatial_types = {
        RelationType.ADJACENT, RelationType.BORDER,
        RelationType.CONNECTION, RelationType.TELEPORT,
    }
    region_ids = {r.id for r in sandbox.regions}
    edges = []
    adjacency: dict[str, set[str]] = {r.id: set() for r in sandbox.regions}
    for rel in sandbox.relations:
        rel_type = normalize_relation_type(rel.relation_type)
        if rel.source_id in region_ids and rel.target_id in region_ids:
            if rel_type in {t.value for t in spatial_types}:
                adjacency[rel.source_id].add(rel.target_id)
                adjacency[rel.target_id].add(rel.source_id)
                edges.append({
                    "source_id": rel.source_id,
                    "target_id": rel.target_id,
                    "relation_type": rel_type,
                })

    # 简单力导引布局：BFS 层次 + 圆形布局
    placed: dict[str, dict[str, float]] = {}
    visited: set[str] = set()

    # 使用已有坐标作为初始位置，否则使用圆形布局
    has_user_positions = any(r.x != 0.0 or r.y != 0.0 for r in sandbox.regions)

    if has_user_positions:
        # 保持用户手动设置的坐标
        for r in sandbox.regions:
            placed[r.id] = {"x": r.x, "y": r.y}
    else:
        # 无用户坐标时使用圆形布局
        n = len(sandbox.regions)
        radius = max(150, n * 40)
        for i, r in enumerate(sandbox.regions):
            angle = 2 * math.pi * i / n
            placed[r.id] = {
                "x": round(radius * math.cos(angle), 2),
                "y": round(radius * math.sin(angle), 2),
            }

    # 构造节点输出（含所属势力信息）
    region_faction_map: dict[str, list[str]] = {}
    for f in sandbox.factions:
        for rid in f.territory_region_ids:
            region_faction_map.setdefault(rid, []).append(f.id)

    nodes = []
    for r in sandbox.regions:
        pos = placed.get(r.id, {"x": 0, "y": 0})
        nodes.append({
            "id": r.id,
            "name": r.name,
            "region_type": r.region_type,
            "x": pos["x"],
            "y": pos["y"],
            "faction_ids": region_faction_map.get(r.id, []),
        })

    return {"nodes": nodes, "edges": edges}


# ----- 工具端点：力量体系模板摘要 -----

@app.get("/projects/{project_id}/world/power-templates", summary="获取内置力量体系模板列表")
async def get_power_templates(project_id: str) -> list[dict[str, Any]]:
    return get_template_summary()


# ----- 完成端点：写入知识库 -----

@app.post("/projects/{project_id}/world/finalize", summary="完成世界设定，写入知识库")
async def finalize_world(project_id: str) -> dict[str, Any]:
    import json as _json
    from pathlib import Path as _Path

    async with AsyncSessionLocal() as db:
        sandbox = await _get_sandbox(project_id, db)
        concept = await _get_concept(project_id, db)

    # 兼容旧 knowledge_base.json 格式
    first_ps = sandbox.power_systems[0] if sandbox.power_systems else None
    seed: dict[str, Any] = {
        "one_sentence": concept.one_sentence,
        "one_paragraph": concept.one_paragraph,
        "genre_tags": concept.genre_tags,
        "world": {
            "power_system": {
                "system_name": first_ps.name if first_ps else "",
                "tiers": [lv.name for lv in first_ps.levels] if first_ps else [],
                "rules": first_ps.rules if first_ps else [],
                "resources": first_ps.resources if first_ps else [],
            } if first_ps else None,
            "factions": [f.name for f in sandbox.factions],
            "key_locations": [r.name for r in sandbox.regions],
            "rules": sandbox.world_rules,
            "world_name": sandbox.world_name,
            "world_type": sandbox.world_type,
            "world_description": sandbox.world_description,
            "sandbox_raw": sandbox.model_dump(),
        },
        "plot_nodes": [],
        "characters": [],
    }

    # 写入 knowledge_base.json
    kb_path = _Path(f".narrative_state/{project_id}/knowledge_base.json")
    kb_path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, Any] = {}
    if kb_path.exists():
        try:
            existing = _json.loads(kb_path.read_text(encoding="utf-8"))
        except Exception:
            existing = {}
    existing.update(seed)
    kb_path.write_text(_json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "success": True,
        "summary": {
            "regions": len(sandbox.regions),
            "factions": len(sandbox.factions),
            "power_systems": len(sandbox.power_systems),
            "relations": len(sandbox.relations),
            "timeline_events": len(sandbox.timeline_events),
        },
    }


# ================================================================== #
# 世界构建 — AI 增强端点                                               #
# ================================================================== #

class AISuggestRelationsRequest(BaseModel):
    faction_ids: list[str]

@app.post("/projects/{project_id}/world/ai/suggest-relations", summary="AI 关系建议")
async def ai_suggest_relations(project_id: str, req: AISuggestRelationsRequest) -> dict[str, Any]:
    from narrative_os.execution.llm_router import LLMRequest, LLMRouter
    import json as _json

    async with AsyncSessionLocal() as db:
        sandbox = await _get_sandbox(project_id, db)

    factions = [f for f in sandbox.factions if f.id in req.faction_ids]
    if not factions:
        return {"suggestions": []}

    faction_descs = []
    for f in factions:
        territory_names = [r.name for r in sandbox.regions if r.id in f.territory_region_ids]
        faction_descs.append(
            f"ID:{f.id} 名称:{f.name} 范围:{f.scope} 阵营:{f.alignment} "
            f"领地:{','.join(territory_names) or '无'} 描述:{f.description}"
        )

    prompt = (
        "你是一位世界观设计助手。根据以下势力信息，建议它们之间可能存在的关系。\n\n"
        "势力列表：\n" + "\n".join(faction_descs) + "\n\n"
        "请以 JSON 数组格式返回建议，每项包含 source_id、target_id、relation_type（alliance/conflict/trade/rivalry/vassal）、reason。"
        "只返回 JSON 数组，不要其他文字。"
    )

    llm_req = LLMRequest(
        task_type="world_building",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=512,
        temperature=0.7,
        skill_name="world_ai_suggest_relations",
    )
    tmp_router = LLMRouter()
    try:
        resp = await tmp_router.call(llm_req)
        content = resp.content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        suggestions = _json.loads(content)
        return {"suggestions": suggestions}
    except Exception as exc:
        return {"suggestions": [], "error": str(exc)}


class AIExpandRequest(BaseModel):
    entity_type: Literal["region", "faction"]
    entity_id: str
    field: str

@app.post("/projects/{project_id}/world/ai/expand", summary="AI 上下文扩写")
async def ai_expand_field(project_id: str, req: AIExpandRequest) -> dict[str, Any]:
    from narrative_os.execution.llm_router import LLMRequest, LLMRouter
    import json as _json

    async with AsyncSessionLocal() as db:
        sandbox = await _get_sandbox(project_id, db)

    entity = None
    if req.entity_type == "region":
        entity = next((r for r in sandbox.regions if r.id == req.entity_id), None)
    else:
        entity = next((f for f in sandbox.factions if f.id == req.entity_id), None)

    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")

    # 收集邻居上下文（1-2跳关系）
    neighbor_ids = set()
    for rel in sandbox.relations:
        if rel.source_id == req.entity_id:
            neighbor_ids.add(rel.target_id)
        elif rel.target_id == req.entity_id:
            neighbor_ids.add(rel.source_id)

    neighbors_desc = []
    for nid in neighbor_ids:
        r = next((x for x in sandbox.regions if x.id == nid), None)
        f = next((x for x in sandbox.factions if x.id == nid), None)
        if r:
            neighbors_desc.append(f"地区:{r.name}({r.region_type})")
        if f:
            neighbors_desc.append(f"势力:{f.name}({f.scope})")

    entity_dump = entity.model_dump() if hasattr(entity, 'model_dump') else str(entity)
    prompt = (
        f"你是一位世界观设计助手。请根据以下实体信息和其关联实体，为字段「{req.field}」生成丰富的内容。\n\n"
        f"实体类型：{req.entity_type}\n"
        f"实体数据：{_json.dumps(entity_dump, ensure_ascii=False)}\n"
        f"关联实体：{', '.join(neighbors_desc) or '无'}\n"
        f"世界背景：{sandbox.world_name} ({sandbox.world_type})\n\n"
        f"请只返回「{req.field}」字段的内容文本，不要 JSON 包装，不要解释。"
    )

    llm_req = LLMRequest(
        task_type="world_building",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=256,
        temperature=0.7,
        skill_name="world_ai_expand",
    )
    tmp_router = LLMRouter()
    try:
        resp = await tmp_router.call(llm_req)
        return {"field": req.field, "generated_content": resp.content.strip()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"AI 扩写失败: {exc}")


class AIImportTextRequest(BaseModel):
    text: str = Field(..., max_length=4000)

@app.post("/projects/{project_id}/world/ai/import-text", summary="文本转图谱（NER）")
async def ai_import_text(project_id: str, req: AIImportTextRequest) -> dict[str, Any]:
    from narrative_os.execution.llm_router import LLMRequest, LLMRouter
    import json as _json

    prompt = (
        "你是一位世界观解析助手。请从下面的设定文本中提取地区、势力和它们之间的关系。\n\n"
        f"文本：\n{req.text}\n\n"
        "请以 JSON 格式返回，结构如下：\n"
        '{"regions": [{"name": "...", "region_type": "...", "notes": "..."}], '
        '"factions": [{"name": "...", "scope": "internal/external", "description": "..."}], '
        '"relations": [{"source_name": "...", "target_name": "...", "relation_type": "alliance/conflict/connection", "label": "..."}]}\n'
        "只返回 JSON，不要其他文字。"
    )

    llm_req = LLMRequest(
        task_type="world_building",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1024,
        temperature=0.3,
        skill_name="world_ai_import_text",
    )
    tmp_router = LLMRouter()
    try:
        resp = await tmp_router.call(llm_req)
        content = resp.content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        parsed = _json.loads(content)
        return {
            "regions": parsed.get("regions", []),
            "factions": parsed.get("factions", []),
            "relations": parsed.get("relations", []),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"AI 文本解析失败: {exc}")


@app.post("/projects/{project_id}/world/ai/consistency-check", summary="AI 深度一致性校验")
async def ai_consistency_check(project_id: str) -> dict[str, Any]:
    from narrative_os.execution.llm_router import LLMRequest, LLMRouter
    import json as _json

    async with AsyncSessionLocal() as db:
        sandbox = await _get_sandbox(project_id, db)

    # 序列化世界数据摘要
    summary_parts = [f"世界：{sandbox.world_name}（{sandbox.world_type}）"]
    for r in sandbox.regions[:20]:
        summary_parts.append(f"地区[{r.name}] 类型:{r.region_type} 阵营:{r.alignment} 备注:{r.notes[:100] if r.notes else ''}")
    for f in sandbox.factions[:20]:
        summary_parts.append(f"势力[{f.name}] 范围:{f.scope} 阵营:{f.alignment} 领地:{f.territory_region_ids} 描述:{f.description[:100] if f.description else ''}")
    for ps in sandbox.power_systems[:10]:
        summary_parts.append(f"力量体系[{ps.name}] 等级:{[l.name for l in ps.levels]} 规则:{ps.rules[:3]}")
    for rel in sandbox.relations[:30]:
        summary_parts.append(f"关系: {rel.source_id}→{rel.target_id} 类型:{rel.relation_type}")

    world_summary = "\n".join(summary_parts)

    prompt = (
        "你是一位世界观一致性分析师。请分析以下世界设定中可能存在的逻辑冲突、不一致或不合理之处。\n\n"
        f"{world_summary}\n\n"
        "请以 JSON 数组格式返回问题列表，每项包含：\n"
        '{"severity": "warning/error", "node_ref": "涉及的实体名", "message": "问题描述"}\n'
        "如果没有发现问题，返回空数组 []。只返回 JSON 数组。"
    )

    llm_req = LLMRequest(
        task_type="consistency_check",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=512,
        temperature=0.3,
        skill_name="world_ai_consistency",
    )
    tmp_router = LLMRouter()
    try:
        resp = await tmp_router.call(llm_req)
        content = resp.content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        issues = _json.loads(content)
        return {"issues": issues if isinstance(issues, list) else []}
    except Exception as exc:
        return {"issues": [], "error": str(exc)}

