"""
orchestrator/graph.py — Phase 3: LangGraph 多 Agent 编排图

拓扑：
  planner_node → writer_node → critic_node ─┬→ editor_node → memory_update_node → END
                                             └→ writer_node  （最多重试 MAX_RETRIES 次）

AgentGraphState 是 LangGraph StateGraph 的状态 TypedDict。
所有节点函数接收 state，返回 state 的局部更新（dict）。

流程说明：
  1. planner_node     — 生成章节骨架（PlannerOutput）
  2. writer_node      — 逐场景生成文本（ChapterDraft）
  3. critic_node      — 审查质量 + 一致性（CriticReport）
  4. router           — 条件路由：通过→editor，重试→writer，超限→editor（强制通过）
  5. editor_node      — 润色去 AI 痕迹（EditedChapter）
  6. memory_update_node — 更新记忆（MemorySystem）

公共入口：
    result = await run_chapter(chapter, volume, target_summary, config_overrides)
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any, Literal, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.types import interrupt

from narrative_os.agents.critic import CriticAgent, CriticReport
from narrative_os.agents.editor import EditedChapter, EditorAgent
from narrative_os.agents.interactive import InteractiveAgent, InteractiveSession, SessionConfig, SessionPhase
from narrative_os.agents.planner import PlannerAgent, PlannerInput, PlannerOutput
from narrative_os.agents.rule_resolver import RuleResolver
from narrative_os.agents.sandbox_simulator import SandboxSimulator
from narrative_os.agents.writer import ChapterDraft, WriterAgent
from narrative_os.core.character import CharacterState
from narrative_os.core.memory import MemorySystem
from narrative_os.core.plot import PlotGraph
from narrative_os.core.save_load import DeadlockBreaker, get_save_store
from narrative_os.core.world import WorldState
from narrative_os.execution.context_builder import (
    ChapterTarget,
    ContextBuilder,
    WriteContext,
)
from narrative_os.execution.llm_router import (
    LLMRouter,
    RoutingStrategy,
    get_default_routing_strategy,
    router as default_router,
)
from narrative_os.infra.logging import logger

# ------------------------------------------------------------------ #
# 交互模式会话注册表（session_id → InteractiveSession）               #
# ------------------------------------------------------------------ #

_session_registry: dict[str, InteractiveSession] = {}
_session_registry_lock = threading.Lock()
MAX_SESSIONS = 100  # 最大并发会话数，防止内存无限增长
_interactive_agent_singleton = InteractiveAgent()

MAX_RETRIES = 3   # critic 最多让 writer 重试次数


# ------------------------------------------------------------------ #
# InteractiveGraphState                                                 #
# ------------------------------------------------------------------ #

class InteractiveGraphState(TypedDict, total=False):
    """交互（TRPG）编排模式的共享状态容器。"""
    # 基础输入（与 pipeline 共用）
    chapter: int
    volume: int
    strategy: str
    plot_graph: PlotGraph | None
    characters: list[CharacterState]
    world: WorldState | None
    memory: MemorySystem | None
    error_message: str

    # 交互模式专有字段
    session_id: str
    session_phase: str            # SessionPhase.value
    user_action: str              # 本轮玩家输入
    turn_records: list[dict]      # 历史 TurnRecord.model_dump()
    density: str                  # dense / normal / sparse
    scene_pressure: float
    lite_plan: dict               # planner_lite 输出（轻量上下文）
    session_summary: dict         # agent.land() 输出


# ------------------------------------------------------------------ #
# 交互模式节点函数                                                       #
# ------------------------------------------------------------------ #

async def planner_lite_node(state: InteractiveGraphState) -> dict[str, Any]:
    """
    交互模式精简规划节点。
    生成最小场景上下文供 InteractiveAgent 使用。
    不调用完整 PlannerAgent.plan()，避免高延迟。
    """
    chapter = state.get("chapter", 1)
    volume = state.get("volume", 1)
    characters = state.get("characters", [])
    world = state.get("world")

    char_names = [c.name for c in characters] if characters else []
    world_rules: list[str] = []
    if world is not None and hasattr(world, "rules"):
        world_rules = world.rules or []

    lite_plan = {
        "chapter": chapter,
        "volume": volume,
        "active_characters": char_names,
        "world_rules": world_rules,
        "world_summary": str(world) if world is not None else "",
        "context_summary": f"第 {volume} 卷第 {chapter} 章交互场景",
    }
    return {"lite_plan": lite_plan}


# ------------------------------------------------------------------ #
# Phase 3 新增节点                                                      #
# ------------------------------------------------------------------ #

async def rule_resolution_node(state: InteractiveGraphState) -> dict[str, Any]:
    """
    Phase 3.6: 世界裁定节点。
    在 interactive_node 前对 user_action 进行 RuleResolver 三层校验。
    若行动被阻止，写入 error_message 并将 user_action 替换为提示文本。
    """
    user_action: str = state.get("user_action", "")
    if not user_action:
        return {}  # 没有用户输入（开幕轮），跳过

    session_id: str = state.get("session_id", "")
    session: InteractiveSession | None = _session_registry.get(session_id)
    if session is None:
        return {}

    characters = state.get("characters", [])
    world = state.get("world")

    # 找到主角角色状态
    actor: CharacterState | None = None
    for c in characters:
        if c.name == session.character_name:
            actor = c
            break

    if actor is None and characters:
        actor = characters[0]
    if actor is None:
        return {}  # 无角色信息，跳过裁定

    resolver = RuleResolver()
    try:
        result = await resolver.resolve(
            user_action=user_action,
            actor_character=actor,
            world_state=world,
        )
    except Exception:
        return {}  # 裁定失败，放行

    if not result.allowed:
        # 将阻止信息写入 error_message，并用系统提示替换 user_action
        blocked_msg = (
            f"[裁定系统] 行动被阻止：{result.blocked_reason}\n"
            + ("提示：" + "；".join(result.warnings) if result.warnings else "")
        )
        return {
            "error_message": blocked_msg,
            "user_action": f"[行动被世界规则阻止] {result.blocked_reason}",
        }

    # 行动允许但有警告/修正
    updates: dict[str, Any] = {}
    if result.modified_action != user_action:
        updates["user_action"] = result.modified_action
    if result.warnings:
        updates["error_message"] = "警告：" + "；".join(result.warnings)
    return updates


async def agenda_simulation_node(state: InteractiveGraphState) -> dict[str, Any]:
    """
    Phase 3.6: Agenda 推演节点。
    在 interactive_node 后推演非玩家受控角色本轮 agenda。
    结果写入 session.last_agenda（用于 5 层 prompt 第 3 层）。
    """
    session_id: str = state.get("session_id", "")
    session: InteractiveSession | None = _session_registry.get(session_id)
    if session is None:
        return {}

    characters = state.get("characters", [])
    world = state.get("world")
    if not characters or world is None:
        return {}

    recent_turn_records: list[dict] = state.get("turn_records", [])
    recent_events = [
        r.get("content", "")[:80]
        for r in recent_turn_records[-4:]
        if r.get("who") == "dm" and r.get("content")
    ]

    sim = SandboxSimulator()
    try:
        deltas = await sim.simulate_turn(
            active_characters=characters,
            world_state=world,
            recent_events=recent_events,
            control_mode=session.control_mode,
        )
        session.last_agenda = [d.model_dump() for d in deltas]
    except Exception:
        pass  # 推演失败不影响主流程

    return {}


async def deadlock_check_node(state: InteractiveGraphState) -> dict[str, Any]:
    """
    Phase 3.6: 死锁检测节点。
    在 should_continue 路由前检查是否进入死锁，若检测到则注入解套叙事。
    """
    session_id: str = state.get("session_id", "")
    session: InteractiveSession | None = _session_registry.get(session_id)
    if session is None:
        return {}

    breaker = DeadlockBreaker()
    condition = breaker.detect(session)
    if condition is None:
        return {}

    # 注入解套文本作为 DM 系统轮
    try:
        resolve_text = await breaker.resolve(condition, session)
        from narrative_os.agents.interactive import TurnRecord
        system_turn = TurnRecord(
            turn_id=session.turn,
            who="system",
            content=f"[解套: {condition.value}] {resolve_text}",
            scene_pressure=session.scene_pressure,
            density=session.density,
            phase=session.phase,
        )
        session.history.append(system_turn)
        session.turn += 1
        prev_records: list[dict] = state.get("turn_records", [])
        return {"turn_records": [*prev_records, system_turn.model_dump()]}
    except Exception:
        return {}


async def interactive_node(state: InteractiveGraphState) -> dict[str, Any]:
    """
    交互（PING_PONG）节点。
    turn==0 时调用 agent.start() 开幕；否则用当前 user_action 推进一步。
    """
    session_id: str = state["session_id"]
    session: InteractiveSession = _session_registry[session_id]
    user_action: str = state.get("user_action", "")

    if session.turn == 0:
        turn_record = await _interactive_agent_singleton.start(session)
    else:
        if not user_action:
            # 通过 LangGraph interrupt 暂停等待外部输入
            user_action = interrupt({"reason": "awaiting_user_action", "session_id": session_id})
            session.turn  # ensure session not mutated before user responds
        turn_record = await _interactive_agent_singleton.step(session, user_action)

    prev_records: list[dict] = state.get("turn_records", [])
    return {
        "turn_records": [*prev_records, turn_record.model_dump()],
        "session_phase": session.phase.value,
        "scene_pressure": session.scene_pressure,
        "user_action": "",   # 消费后清空，等待下一轮
    }


async def landing_node(state: InteractiveGraphState) -> dict[str, Any]:
    """将 TRPG 会话落地为章节草稿摘要并清理状态。"""
    session_id: str = state.get("session_id", "")
    session: InteractiveSession | None = _session_registry.get(session_id)

    if session is None:
        logger.warn("landing_node_no_session", session_id=session_id)
        return {"session_summary": {}}

    summary = _interactive_agent_singleton.land(session)
    return {"session_summary": summary, "session_phase": SessionPhase.ENDED.value}


async def maintenance_node_interactive(state: InteractiveGraphState) -> dict[str, Any]:
    """从 session_summary 提取角色状态 delta 并写入 MemorySystem。"""
    mem: MemorySystem | None = state.get("memory")
    summary: dict = state.get("session_summary", {})

    if mem is not None and summary:
        try:
            session_text = summary.get("session_text", "")
            chapter = state.get("chapter", 1)
            volume = state.get("volume", 1)
            if session_text:
                mem.store_paragraph(
                    text=session_text,
                    chapter=chapter,
                    volume=volume,
                    layer="long_term",
                )
            logger.info("interactive_memory_updated", chapter=chapter)
        except Exception as exc:  # pylint: disable=broad-except
            logger.warn("interactive_memory_update_failed", error=str(exc))

    return {}


# ------------------------------------------------------------------ #
# 交互模式条件路由                                                       #
# ------------------------------------------------------------------ #

def should_continue(state: InteractiveGraphState) -> str:
    """
    PING_PONG 循环条件路由。
    返回值决定下一个节点：
      "user_input"    — 等待玩家输入（LangGraph interrupt→重入 interactive_node）
      "landing"       — 正常落地
      "pacing_alert"  — 节奏警报强制落地
    """
    phase_str = state.get("session_phase", SessionPhase.PING_PONG.value)

    if phase_str == SessionPhase.PACING_ALERT.value:
        return "pacing_alert"
    if phase_str in {SessionPhase.LANDING.value, SessionPhase.ENDED.value}:
        return "landing"
    # PING_PONG / INTERRUPT / OPENING / INIT → 继续等待玩家输入
    return "user_input"


# ------------------------------------------------------------------ #
# 交互模式图构建                                                         #
# ------------------------------------------------------------------ #

def build_interactive_graph() -> StateGraph:
    """
    构建 TRPG 交互模式图（未编译）。

    拓扑（Phase 3 升级后）：
      planner_lite → rule_resolution → interactive → agenda_simulation
                                                    → deadlock_check → should_continue?
                                     ├─ "user_input"   → rule_resolution（循环，经 LangGraph interrupt）
                                     ├─ "landing"      → landing → maintenance_interactive → END
                                     └─ "pacing_alert" → landing → END（跳过记忆更新）
    """
    graph: StateGraph = StateGraph(InteractiveGraphState)

    graph.add_node("planner_lite", planner_lite_node)
    graph.add_node("rule_resolution", rule_resolution_node)
    graph.add_node("interactive", interactive_node)
    graph.add_node("agenda_simulation", agenda_simulation_node)
    graph.add_node("deadlock_check", deadlock_check_node)
    graph.add_node("landing", landing_node)
    graph.add_node("maintenance_interactive", maintenance_node_interactive)

    graph.set_entry_point("planner_lite")
    graph.add_edge("planner_lite", "rule_resolution")
    graph.add_edge("rule_resolution", "interactive")
    graph.add_edge("interactive", "agenda_simulation")
    graph.add_edge("agenda_simulation", "deadlock_check")
    graph.add_conditional_edges(
        "deadlock_check",
        should_continue,
        path_map={
            "user_input": "rule_resolution",      # 循环经 rule_resolution 再入 interactive
            "landing": "landing",
            "pacing_alert": "landing",
        },
    )
    graph.add_edge("landing", "maintenance_interactive")
    graph.add_edge("maintenance_interactive", END)

    return graph


def compile_interactive_graph(checkpointer: MemorySaver | None = None) -> Any:
    """编译 TRPG 交互模式图，**必须**挂载 checkpointer 以支持 interrupt 恢复。"""
    g = build_interactive_graph()
    if checkpointer is None:
        checkpointer = MemorySaver()
    # interrupt_before rule_resolution so the graph pauses for user input on each cycle
    return g.compile(checkpointer=checkpointer, interrupt_before=["rule_resolution"])


# ------------------------------------------------------------------ #
# AgentGraphState                                                       #
# ------------------------------------------------------------------ #

class AgentGraphState(TypedDict, total=False):
    """LangGraph 共享状态容器。"""
    # 输入
    chapter: int
    volume: int
    target_summary: str
    word_count_target: int
    previous_hook: str
    existing_arc_summary: str
    character_names: list[str]
    world_rules: list[str]
    constraints: list[str]
    strategy: str              # RoutingStrategy 枚举名

    # Phase 6 Stage 1: 项目 ID，供 WorldRepository 懒加载世界状态
    project_id: str | None

    # 依赖资源（运行时注入，不序列化）
    plot_graph: PlotGraph | None
    characters: list[CharacterState]
    world: WorldState | None
    memory: MemorySystem | None

    # 中间结果
    planner_output: PlannerOutput | None
    write_context: WriteContext | None
    chapter_draft: ChapterDraft | None
    critic_report: CriticReport | None
    edited_chapter: EditedChapter | None

    # 控制
    retry_count: int
    error_message: str


# ------------------------------------------------------------------ #
# Node functions                                                        #
# ------------------------------------------------------------------ #

def _get_strategy(state: AgentGraphState) -> RoutingStrategy:
    default_name = get_default_routing_strategy().name
    name = state.get("strategy") or default_name
    try:
        return RoutingStrategy[name]
    except KeyError:
        return get_default_routing_strategy()


async def planner_node(state: AgentGraphState) -> dict[str, Any]:
    """节点 1：生成章节剧情骨架。"""
    agent = PlannerAgent()
    inp = PlannerInput(
        chapter=state["chapter"],
        volume=state.get("volume", 1),
        target_summary=state.get("target_summary", ""),
        word_count_target=state.get("word_count_target", 2000),
        previous_hook=state.get("previous_hook", ""),
        existing_arc_summary=state.get("existing_arc_summary", ""),
        character_names=state.get("character_names", []),
        world_rules=state.get("world_rules", []),
        constraints=state.get("constraints", []),
    )
    plan = await agent.plan(inp, strategy=_get_strategy(state))

    # 将规划写入 PlotGraph
    graph = state.get("plot_graph")
    if graph is not None:
        plan.apply_to_graph(graph)

    # 同时组装写前上下文
    ctx = await _build_write_context(state, plan)

    return {"planner_output": plan, "write_context": ctx}


async def writer_node(state: AgentGraphState) -> dict[str, Any]:
    """节点 2：逐场景生成章节草稿。"""
    agent = WriterAgent()
    plan: PlannerOutput = state["planner_output"]          # type: ignore[assignment]
    ctx: WriteContext = state["write_context"]              # type: ignore[assignment]
    draft = await agent.write(plan, ctx, strategy=_get_strategy(state))
    return {"chapter_draft": draft}


async def critic_node(state: AgentGraphState) -> dict[str, Any]:
    """节点 3：审查草稿质量与一致性。"""
    agent = CriticAgent()
    draft: ChapterDraft = state["chapter_draft"]           # type: ignore[assignment]
    ctx: WriteContext = state["write_context"]             # type: ignore[assignment]
    report = await agent.review(
        draft=draft,
        context=ctx,
        characters=state.get("characters", []),
        world=state.get("world"),
        plot_graph=state.get("plot_graph"),
    )
    return {"critic_report": report}


async def editor_node(state: AgentGraphState) -> dict[str, Any]:
    """节点 4：润色去 AI 痕迹。"""
    agent = EditorAgent()
    draft: ChapterDraft = state["chapter_draft"]           # type: ignore[assignment]
    report: CriticReport = state["critic_report"]          # type: ignore[assignment]
    edited = await agent.edit(draft, report, strategy=_get_strategy(state))
    return {"edited_chapter": edited}


async def memory_update_node(state: AgentGraphState) -> dict[str, Any]:
    """节点 5：将最终章节写入长期记忆。"""
    mem: MemorySystem | None = state.get("memory")
    edited: EditedChapter | None = state.get("edited_chapter")
    if mem is not None and edited is not None:
        try:
            mem.store_paragraph(
                text=edited.text,
                chapter=edited.chapter,
                volume=edited.volume,
                layer="long_term",
            )
            logger.info("memory_updated", chapter=edited.chapter)
        except Exception as exc:  # pylint: disable=broad-except
            logger.warn("memory_update_failed", error=str(exc))
    return {}   # 无状态变更，仅副作用


# ------------------------------------------------------------------ #
# 条件路由                                                              #
# ------------------------------------------------------------------ #

def should_rewrite(state: AgentGraphState) -> str:
    """Critic 后的路由决策函数。"""
    report: CriticReport | None = state.get("critic_report")
    retry_count: int = state.get("retry_count", 0)

    if report is None or report.passed:
        return "editor"
    if retry_count >= MAX_RETRIES:
        logger.warn("max_retries_reached",
                       chapter=state.get("chapter"), retries=retry_count)
        return "editor"   # 超限强行推进
    # 增加重试计数（注：LangGraph 的条件边无法直接修改状态，
    #   通过 writer_node 重进时在 writer 执行前用 retry_increment_node 更新）
    return "retry_writer"


async def retry_increment_node(state: AgentGraphState) -> dict[str, Any]:
    """将 retry_count 加 1，位于 should_rewrite → writer 的边上。"""
    return {"retry_count": state.get("retry_count", 0) + 1}


# ------------------------------------------------------------------ #
# Graph 构建与编译                                                       #
# ------------------------------------------------------------------ #

def build_graph() -> StateGraph:
    """构建 LangGraph 编排图（未编译）。"""
    graph = StateGraph(AgentGraphState)

    graph.add_node("planner", planner_node)
    graph.add_node("writer", writer_node)
    graph.add_node("critic", critic_node)
    graph.add_node("retry_increment", retry_increment_node)
    graph.add_node("editor", editor_node)
    graph.add_node("memory_update", memory_update_node)

    graph.set_entry_point("planner")
    graph.add_edge("planner", "writer")
    graph.add_edge("writer", "critic")
    graph.add_conditional_edges(
        "critic",
        should_rewrite,
        path_map={
            "editor": "editor",
            "retry_writer": "retry_increment",
        },
    )
    graph.add_edge("retry_increment", "writer")
    graph.add_edge("editor", "memory_update")
    graph.add_edge("memory_update", END)

    return graph


def compile_graph(checkpointer: MemorySaver | None = None) -> Any:
    """编译 LangGraph 图，可选挂载内存检查点。"""
    g = build_graph()
    if checkpointer is None:
        checkpointer = MemorySaver()
    return g.compile(checkpointer=checkpointer)


# ------------------------------------------------------------------ #
# 公共入口                                                              #
# ------------------------------------------------------------------ #

async def run_chapter(
    chapter: int,
    volume: int = 1,
    target_summary: str = "",
    word_count_target: int = 2000,
    strategy: str = get_default_routing_strategy().name,
    previous_hook: str = "",
    existing_arc_summary: str = "",
    character_names: list[str] | None = None,
    world_rules: list[str] | None = None,
    constraints: list[str] | None = None,
    # 运行时资源
    plot_graph: PlotGraph | None = None,
    characters: list[CharacterState] | None = None,
    world: WorldState | None = None,
    memory: MemorySystem | None = None,
    # 模式选择（pipeline = 常规生成；interactive = TRPG 交互）
    mode: Literal["pipeline", "interactive"] = "pipeline",
    session_id: str | None = None,
    user_action: str | None = None,
    # LangGraph 配置
    thread_id: str = "default",
    checkpointer: MemorySaver | None = None,
) -> AgentGraphState | InteractiveGraphState:
    """
    一键执行单章生成流程，返回最终状态。

    pipeline 模式（默认）：
        state = await run_chapter(chapter=3, target_summary="主角觉醒异能")
        print(state["edited_chapter"].text)

    interactive 模式：
        # 首先在 _session_registry 中注册 session
        state = await run_chapter(chapter=3, mode="interactive",
                                  session_id=sid, user_action="我向前走")
    """
    if mode == "interactive":
        if session_id is None:
            raise ValueError("interactive 模式需要提供 session_id")

        app = compile_interactive_graph(checkpointer)
        initial_state: InteractiveGraphState = {
            "chapter": chapter,
            "volume": volume,
            "strategy": strategy,
            "plot_graph": plot_graph,
            "characters": characters or [],
            "world": world,
            "memory": memory,
            "error_message": "",
            "session_id": session_id,
            "session_phase": SessionPhase.INIT.value,
            "user_action": user_action or "",
            "turn_records": [],
            "density": "normal",
            "scene_pressure": 5.0,
            "lite_plan": {},
            "session_summary": {},
        }
        config = {"configurable": {"thread_id": thread_id}}
        final = await app.ainvoke(initial_state, config=config)
        return final  # type: ignore[return-value]

    # ── pipeline 模式（保持原有行为不变） ──────────────────────────────
    app = compile_graph(checkpointer)

    pipeline_state: AgentGraphState = {
        "chapter": chapter,
        "volume": volume,
        "target_summary": target_summary,
        "word_count_target": word_count_target,
        "previous_hook": previous_hook,
        "existing_arc_summary": existing_arc_summary,
        "character_names": character_names or [],
        "world_rules": world_rules or [],
        "constraints": constraints or [],
        "strategy": strategy,
        "plot_graph": plot_graph,
        "characters": characters or [],
        "world": world,
        "memory": memory,
        "planner_output": None,
        "write_context": None,
        "chapter_draft": None,
        "critic_report": None,
        "edited_chapter": None,
        "retry_count": 0,
        "error_message": "",
    }

    config = {"configurable": {"thread_id": thread_id}}
    final = await app.ainvoke(pipeline_state, config=config)
    return final  # type: ignore[return-value]


# ------------------------------------------------------------------ #
# Helpers (private)                                                     #
# ------------------------------------------------------------------ #

async def _build_write_context(
    state: AgentGraphState,
    plan: PlannerOutput,
) -> WriteContext:
    """根据 state 中的资源组装 WriteContext。"""
    builder = ContextBuilder()
    target = ChapterTarget(
        chapter=state["chapter"],
        volume=state.get("volume", 1),
        target_summary=plan.chapter_outline or state.get("target_summary", ""),
        word_count_target=state.get("word_count_target", 2000),
        tension_target=float(plan.tension_curve[-1][1]) if plan.tension_curve else 0.6,
        hook_type=plan.hook_type,
    )
    # Phase 6 Stage 1: 通过 WorldRepository 统一入口获取世界状态（project_id 懒加载）
    project_id: str | None = state.get("project_id")  # type: ignore[assignment]
    ctx = builder.build(
        chapter_target=target,
        plot_graph=state.get("plot_graph"),
        characters=state.get("characters", []),
        world=state.get("world"),
        memory=state.get("memory"),
        project_id=project_id,
    )
    return ctx
