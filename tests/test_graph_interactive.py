"""
tests/test_graph_interactive.py — Phase 4: 交互模式编排图测试
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from narrative_os.agents.interactive import (
    DecisionPoint,
    InteractiveSession,
    SessionConfig,
    SessionPhase,
    TurnRecord,
)
from narrative_os.orchestrator.graph import (
    InteractiveGraphState,
    _session_registry,
    build_graph,
    build_interactive_graph,
    interactive_node,
    landing_node,
    maintenance_node_interactive,
    planner_lite_node,
    run_chapter,
    should_continue,
)


# ------------------------------------------------------------------ #
# 固定装置                                                              #
# ------------------------------------------------------------------ #

@pytest.fixture(autouse=True)
def clear_registry():
    """每个测试前后清空会话注册表。"""
    _session_registry.clear()
    yield
    _session_registry.clear()


def _make_session(phase: SessionPhase = SessionPhase.PING_PONG) -> InteractiveSession:
    cfg = SessionConfig(project_id="test")
    s = InteractiveSession(
        session_id=str(uuid.uuid4()),
        project_id="test",
        phase=phase,
        density="normal",
        scene_pressure=5.0,
        config=cfg,
    )
    return s


def _make_dm_turn(session: InteractiveSession, content: str = "DM 叙事") -> TurnRecord:
    t = TurnRecord(
        turn_id=session.turn,
        who="dm",
        content=content,
        phase=session.phase,
        density=session.density,
        scene_pressure=session.scene_pressure,
    )
    session.history.append(t)
    return t


# ------------------------------------------------------------------ #
# build_interactive_graph                                               #
# ------------------------------------------------------------------ #

def test_build_interactive_graph_returns_compiled():
    """build_interactive_graph() 应编译成功，无异常。"""
    graph = build_interactive_graph()
    assert graph is not None
    # 验证节点存在
    node_names = set(graph.nodes.keys())
    assert "planner_lite" in node_names
    assert "interactive" in node_names
    assert "landing" in node_names
    assert "maintenance_interactive" in node_names


# ------------------------------------------------------------------ #
# planner_lite_node                                                     #
# ------------------------------------------------------------------ #

async def test_planner_lite_node_output_structure():
    """planner_lite_node 应输出 lite_plan，不调用完整 PlannerAgent。"""
    state: InteractiveGraphState = {
        "chapter": 3,
        "volume": 2,
        "characters": [],
        "world": None,
    }

    # 确保 PlannerAgent.plan 未被调用
    with patch("narrative_os.orchestrator.graph.PlannerAgent") as mock_planner:
        result = await planner_lite_node(state)

    mock_planner.return_value.plan.assert_not_called()
    assert "lite_plan" in result
    plan = result["lite_plan"]
    assert plan["chapter"] == 3
    assert plan["volume"] == 2
    assert "active_characters" in plan
    assert "context_summary" in plan


async def test_planner_lite_node_includes_char_names():
    """planner_lite_node 应从 characters 列表提取角色名。"""
    char = MagicMock()
    char.name = "李明"
    state: InteractiveGraphState = {
        "chapter": 1,
        "volume": 1,
        "characters": [char],
        "world": None,
    }
    result = await planner_lite_node(state)
    assert "李明" in result["lite_plan"]["active_characters"]


# ------------------------------------------------------------------ #
# interactive_node                                                       #
# ------------------------------------------------------------------ #

async def test_interactive_node_calls_start_on_turn_0():
    """turn==0 时 interactive_node 应调用 agent.start()，不调用 step()。"""
    session = _make_session(phase=SessionPhase.INIT)
    session.turn = 0
    _session_registry[session.session_id] = session

    opening_turn = _make_dm_turn(session, "你站在废弃神殿入口。")

    with patch("narrative_os.orchestrator.graph._interactive_agent_singleton") as mock_agent:
        mock_agent.start = AsyncMock(return_value=opening_turn)
        mock_agent.step = AsyncMock()

        state: InteractiveGraphState = {
            "session_id": session.session_id,
            "user_action": "",
            "turn_records": [],
            "session_phase": SessionPhase.INIT.value,
        }
        result = await interactive_node(state)

    mock_agent.start.assert_awaited_once_with(session)
    mock_agent.step.assert_not_awaited()
    assert len(result["turn_records"]) == 1
    assert result["session_phase"] == session.phase.value


async def test_interactive_node_calls_step_on_turn_gt_0():
    """turn>0 时 interactive_node 应用 user_action 调用 agent.step()。"""
    session = _make_session(phase=SessionPhase.PING_PONG)
    session.turn = 2
    _session_registry[session.session_id] = session

    dm_turn = TurnRecord(
        turn_id=3, who="dm", content="你触碰了祭坛。",
        phase=SessionPhase.PING_PONG, density="normal", scene_pressure=6.0,
    )

    with patch("narrative_os.orchestrator.graph._interactive_agent_singleton") as mock_agent:
        mock_agent.step = AsyncMock(return_value=dm_turn)

        state: InteractiveGraphState = {
            "session_id": session.session_id,
            "user_action": "我向前走。",
            "turn_records": [],
            "session_phase": SessionPhase.PING_PONG.value,
        }
        result = await interactive_node(state)

    mock_agent.step.assert_awaited_once_with(session, "我向前走。")
    assert result["turn_records"][0]["content"] == "你触碰了祭坛。"
    assert result["user_action"] == ""  # 消费后清空


# ------------------------------------------------------------------ #
# should_continue 路由                                                   #
# ------------------------------------------------------------------ #

def test_should_continue_routes_to_landing_on_ended():
    """ENDED 相位应路由到 landing。"""
    state: InteractiveGraphState = {"session_phase": SessionPhase.ENDED.value}
    assert should_continue(state) == "landing"


def test_should_continue_routes_to_landing_on_landing():
    state: InteractiveGraphState = {"session_phase": SessionPhase.LANDING.value}
    assert should_continue(state) == "landing"


def test_should_continue_routes_to_pacing_alert():
    state: InteractiveGraphState = {"session_phase": SessionPhase.PACING_ALERT.value}
    assert should_continue(state) == "pacing_alert"


def test_should_continue_routes_to_user_input_on_ping_pong():
    state: InteractiveGraphState = {"session_phase": SessionPhase.PING_PONG.value}
    assert should_continue(state) == "user_input"


def test_should_continue_default_is_user_input():
    """未设置 session_phase 时应默认返回 user_input。"""
    state: InteractiveGraphState = {}
    assert should_continue(state) == "user_input"


# ------------------------------------------------------------------ #
# run_chapter pipeline 模式不变                                          #
# ------------------------------------------------------------------ #

async def test_run_chapter_pipeline_mode_calls_compile_graph():
    """pipeline 模式应使用 build_graph()，不使用 build_interactive_graph()。"""
    with (
        patch("narrative_os.orchestrator.graph.compile_graph") as mock_compile,
        patch("narrative_os.orchestrator.graph.compile_interactive_graph") as mock_interactive,
    ):
        compiled_mock = MagicMock()
        compiled_mock.ainvoke = AsyncMock(return_value={"edited_chapter": None})
        mock_compile.return_value = compiled_mock

        await run_chapter(chapter=1, mode="pipeline")

    mock_compile.assert_called_once()
    mock_interactive.assert_not_called()


async def test_run_chapter_interactive_mode_requires_session_id():
    """interactive 模式缺少 session_id 时应抛出 ValueError。"""
    with pytest.raises(ValueError, match="session_id"):
        await run_chapter(chapter=1, mode="interactive", session_id=None)


async def test_run_chapter_interactive_mode_calls_interactive_graph():
    """interactive 模式应使用 compile_interactive_graph()，不使用 compile_graph()。"""
    session = _make_session()
    _session_registry[session.session_id] = session

    with (
        patch("narrative_os.orchestrator.graph.compile_graph") as mock_pipeline,
        patch("narrative_os.orchestrator.graph.compile_interactive_graph") as mock_interactive,
    ):
        compiled_mock = MagicMock()
        compiled_mock.ainvoke = AsyncMock(return_value={"session_phase": "ENDED"})
        mock_interactive.return_value = compiled_mock

        await run_chapter(
            chapter=1, mode="interactive",
            session_id=session.session_id, user_action="测试行动"
        )

    mock_interactive.assert_called_once()
    mock_pipeline.assert_not_called()
