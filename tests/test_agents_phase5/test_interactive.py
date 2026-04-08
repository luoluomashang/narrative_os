"""tests/test_agents_phase5/test_interactive.py — InteractiveAgent 测试组。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from narrative_os.agents.interactive import (
    DecisionPoint,
    InteractiveAgent,
    InteractiveSession,
    SessionConfig,
    SessionPhase,
    TurnRecord,
)


# ------------------------------------------------------------------ #
# Fixtures                                                              #
# ------------------------------------------------------------------ #

@pytest.fixture
def mock_router():
    router = MagicMock()
    resp = MagicMock()
    resp.content = "夜色深沉，你站在神殿入口。\n[选项 A]：举起火把走进去\n[选项 B]：原地等待"
    resp.model_used = "gpt-4o-mini"
    router.call = AsyncMock(return_value=resp)
    return router


@pytest.fixture
def agent(mock_router) -> InteractiveAgent:
    return InteractiveAgent(router=mock_router)


@pytest.fixture
def session(agent) -> InteractiveSession:
    cfg = SessionConfig(
        project_id="test",
        character_name="林枫",
        opening_prompt="一座古老神殿矗立在荒野中。",
        initial_pressure=5.0,
    )
    return agent.create_session(cfg)


# ------------------------------------------------------------------ #
# create_session                                                        #
# ------------------------------------------------------------------ #

class TestCreateSession:
    def test_initial_phase_is_init(self, agent):
        s = agent.create_session(SessionConfig())
        assert s.phase == SessionPhase.INIT

    def test_session_id_is_unique(self, agent):
        s1 = agent.create_session(SessionConfig())
        s2 = agent.create_session(SessionConfig())
        assert s1.session_id != s2.session_id

    def test_config_copied(self, agent):
        cfg = SessionConfig(character_name="陈伟", initial_pressure=8.0)
        s = agent.create_session(cfg)
        assert s.character_name == "陈伟"
        assert s.scene_pressure == 8.0

    def test_density_override(self, agent):
        cfg = SessionConfig(density_override="dense")
        s = agent.create_session(cfg)
        assert s.density == "dense"

    def test_default_density_normal(self, agent):
        s = agent.create_session(SessionConfig(initial_pressure=5.0))
        assert s.density == "normal"


# ------------------------------------------------------------------ #
# start                                                                 #
# ------------------------------------------------------------------ #

class TestStart:
    async def test_transitions_to_ping_pong(self, agent, session):
        await agent.start(session)
        assert session.phase == SessionPhase.PING_PONG

    async def test_returns_dm_turn(self, agent, session):
        turn = await agent.start(session)
        assert isinstance(turn, TurnRecord)
        assert turn.who == "dm"

    async def test_history_grows(self, agent, session):
        assert len(session.history) == 0
        await agent.start(session)
        assert len(session.history) == 1

    async def test_cannot_start_twice(self, agent, session):
        await agent.start(session)
        with pytest.raises(AssertionError):
            await agent.start(session)


# ------------------------------------------------------------------ #
# step                                                                  #
# ------------------------------------------------------------------ #

class TestStep:
    async def test_records_user_and_dm_turns(self, agent, session):
        await agent.start(session)
        initial_len = len(session.history)
        await agent.step(session, "我举起火把走进去。")
        assert len(session.history) == initial_len + 2  # user + dm

    async def test_turn_counter_increments(self, agent, session):
        await agent.start(session)
        t0 = session.turn
        await agent.step(session, "行动")
        assert session.turn == t0 + 2  # user + dm each increment once

    async def test_high_pressure_action_increases_pressure(self, agent, session):
        await agent.start(session)
        p0 = session.scene_pressure
        await agent.step(session, "我猛攻敌人，刺出长剑！")
        assert session.scene_pressure >= p0

    async def test_rest_action_decreases_pressure(self, agent, session):
        session.scene_pressure = 7.0
        await agent.start(session)
        await agent.step(session, "我们先回营地休息。")
        assert session.scene_pressure <= 7.0

    async def test_decision_extracted_from_dm_response(self, agent, session):
        await agent.start(session)
        turn = await agent.step(session, "继续前进")
        # mock_router returns content with [选项 A] and [选项 B]
        assert session.open_decision is not None
        assert len(session.open_decision.options) == 2


# ------------------------------------------------------------------ #
# rollback                                                              #
# ------------------------------------------------------------------ #

class TestRollback:
    async def test_rollback_one_step(self, agent, session):
        await agent.start(session)
        await agent.step(session, "行动1")
        history_before = len(session.history)
        agent.rollback(session, steps=1)
        assert len(session.history) == history_before - 2  # remove user+dm pair

    async def test_rollback_clears_open_decision(self, agent, session):
        await agent.start(session)
        await agent.step(session, "行动")
        session.open_decision = DecisionPoint(options=["A", "B"])
        agent.rollback(session, steps=1)
        assert session.open_decision is None

    async def test_rollback_phase_returns_ping_pong(self, agent, session):
        await agent.start(session)
        agent.rollback(session, steps=0)
        assert session.phase == SessionPhase.PING_PONG

    async def test_rollback_more_than_history_caps(self, agent, session):
        await agent.start(session)
        # 只有 1 条历史，rollback 5 步不崩
        agent.rollback(session, steps=5)
        assert session.history == []
        assert session.turn == 0


# ------------------------------------------------------------------ #
# interrupt (bangui)                                                    #
# ------------------------------------------------------------------ #

class TestInterrupt:
    async def test_interrupt_returns_to_ping_pong(self, agent, session):
        await agent.start(session)
        await agent.interrupt(session, "帮回主动1")
        assert session.phase == SessionPhase.PING_PONG

    async def test_interrupt_returns_turn_record(self, agent, session):
        await agent.start(session)
        turn = await agent.interrupt(session, "帮回推进1")
        assert isinstance(turn, TurnRecord)
        assert turn.who == "dm"

    async def test_normalize_bangui_with_slash(self, agent):
        assert agent._normalize_bangui("/帮回主动1") == "帮回主动1"

    async def test_normalize_unknown_passthrough(self, agent):
        assert agent._normalize_bangui("unknown_cmd") == "unknown_cmd"


# ------------------------------------------------------------------ #
# land                                                                  #
# ------------------------------------------------------------------ #

class TestLand:
    async def test_land_ends_session(self, agent, session):
        await agent.start(session)
        output = agent.land(session)
        assert session.phase == SessionPhase.ENDED

    async def test_land_returns_dict(self, agent, session):
        await agent.start(session)
        out = agent.land(session)
        assert "session_id" in out
        assert "turns" in out
        assert "user_actions" in out

    async def test_land_captures_turn_count(self, agent, session):
        await agent.start(session)
        await agent.step(session, "行动")
        turns_before = session.turn
        out = agent.land(session)
        assert out["turns"] == turns_before


# ------------------------------------------------------------------ #
# density auto-switching                                                #
# ------------------------------------------------------------------ #

class TestDensityAutoSwitch:
    def test_high_pressure_switches_to_dense(self, agent):
        cfg = SessionConfig(initial_pressure=9.0)
        s = agent.create_session(cfg)
        # manually trigger pressure update
        agent._update_pressure(s, "攻击！")
        assert s.density == "dense"

    def test_low_pressure_switches_to_sparse(self, agent):
        cfg = SessionConfig(initial_pressure=2.0)
        s = agent.create_session(cfg)
        agent._update_pressure(s, "回营地休息")
        assert s.density == "sparse"

    def test_density_override_respected(self, agent):
        cfg = SessionConfig(density_override="dense", initial_pressure=1.0)
        s = agent.create_session(cfg)
        # Even with low pressure update, override stays
        agent._update_pressure(s, "回营地休息")
        assert s.density == "dense"


# ------------------------------------------------------------------ #
# _extract_decision                                                     #
# ------------------------------------------------------------------ #

class TestExtractDecision:
    def test_extracts_two_options(self, agent):
        text = "敌人逼近。\n[选项 A]：拔剑迎战\n[选项 B]：向后撤退"
        dp = agent._extract_decision(text)
        assert dp is not None
        assert len(dp.options) == 2
        assert "拔剑迎战" in dp.options

    def test_no_options_returns_none(self, agent):
        text = "主角沿着小路走去，四周寂静。"
        dp = agent._extract_decision(text)
        assert dp is None

    def test_three_options(self, agent):
        text = "[选项 A]：攻击\n[选项 B]：防御\n[选项 C]：逃跑"
        dp = agent._extract_decision(text)
        assert dp is not None
        assert len(dp.options) == 3
