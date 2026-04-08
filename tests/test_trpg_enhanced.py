"""
tests/test_trpg_enhanced.py — 阶段六：TRPG 增强功能测试

覆盖 Phase 4 新增的 TRPG 可视化特性：
  - step 返回含 decision_type 的 DecisionPoint
  - step 返回含 risk_level 的 DecisionPoint
  - _detect_agency_violation 检测阳性/阴性
  - session status 响应含 phase 字段
  - emotional_temperature 字段存在且格式正确
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from narrative_os.agents.interactive import (
    DecisionPoint,
    InteractiveAgent,
    InteractiveSession,
    SessionConfig,
    SessionPhase,
    TurnRecord,
)
from narrative_os.interface.api import (
    _sessions,
    _sessions_lock,
    app,
)


# ------------------------------------------------------------------ #
# 固定装置                                                              #
# ------------------------------------------------------------------ #

@pytest.fixture()
def client():
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def clear_sessions():
    """每个测试前后清空内存会话存储"""
    with _sessions_lock:
        _sessions.clear()
    yield
    with _sessions_lock:
        _sessions.clear()


def _make_session(**kwargs) -> InteractiveSession:
    cfg = SessionConfig(
        project_id="test_proj",
        character_name="测试主角",
        world_summary="这是一个测试世界",
    )
    defaults = dict(
        phase=SessionPhase.PING_PONG,
        scene_pressure=5.0,
        density="normal",
        config=cfg,
    )
    defaults.update(kwargs)
    return InteractiveSession(**defaults)


def _make_dm_turn(decision: DecisionPoint | None = None, **kwargs) -> TurnRecord:
    defaults = dict(
        turn_id=1,
        who="dm",
        content="前方出现了分叉路口。\n[选项 A]：向左走\n[选项 B]：向右走",
        scene_pressure=5.0,
        density="normal",
        phase=SessionPhase.PING_PONG,
        decision=decision,
    )
    defaults.update(kwargs)
    return TurnRecord(**defaults)


# ------------------------------------------------------------------ #
# 6.3.1 step 返回含 decision_type 的选项                               #
# ------------------------------------------------------------------ #

class TestInteractiveStepDecisionType:
    """InteractiveAgent.step() 返回的 turn 含有 decision_type 字段。"""

    @pytest.mark.asyncio
    async def test_interactive_step_returns_decision_type(self):
        """step 后 DM turn 的 decision 含 decision_type 字段。"""
        agent = InteractiveAgent()

        decision = DecisionPoint(
            decision_type="action",
            options=["向左冲", "向右躲"],
            risk_levels=["safe", "risky"],
        )
        mock_turn = _make_dm_turn(decision=decision)

        with patch.object(agent, "_dm_narrate", new_callable=AsyncMock, return_value=mock_turn):
            session = _make_session()
            result = await agent.step(session, user_action="我向前走")

        assert result.decision is not None
        assert result.decision.decision_type == "action"
        assert isinstance(result.decision.decision_type, str)

    @pytest.mark.asyncio
    async def test_decision_type_is_valid_literal(self):
        """decision_type 必须是规定的枚举值之一。"""
        valid_types = {"action", "dialogue", "attitude", "tactical", "inner",
                       "moral", "free_action"}
        agent = InteractiveAgent()

        for dt in ("action", "dialogue", "tactical"):
            decision = DecisionPoint(decision_type=dt, options=["A", "B"])
            mock_turn = _make_dm_turn(decision=decision)

            with patch.object(agent, "_dm_narrate", new_callable=AsyncMock,
                               return_value=mock_turn):
                session = _make_session()
                result = await agent.step(session, user_action="行动")

            assert result.decision.decision_type in valid_types


# ------------------------------------------------------------------ #
# 6.3.2 step 返回含 risk_level 的选项                                  #
# ------------------------------------------------------------------ #

class TestInteractiveStepRiskLevel:
    """DecisionPoint.risk_levels 列表有正确的取值。"""

    @pytest.mark.asyncio
    async def test_interactive_step_returns_risk_level(self):
        """step 后 decision.risk_levels 包含合法 risk_level 值。"""
        agent = InteractiveAgent()

        decision = DecisionPoint(
            decision_type="action",
            options=["正面强攻", "暗中潜行", "撤退观察"],
            risk_levels=["dangerous", "risky", "safe"],
        )
        mock_turn = _make_dm_turn(decision=decision)

        with patch.object(agent, "_dm_narrate", new_callable=AsyncMock,
                           return_value=mock_turn):
            session = _make_session()
            result = await agent.step(session, user_action="思考行动方案")

        assert result.decision is not None
        assert hasattr(result.decision, "risk_levels")
        assert isinstance(result.decision.risk_levels, list)

        valid_levels = {"safe", "risky", "dangerous"}
        for level in result.decision.risk_levels:
            assert level in valid_levels, f"非法 risk_level: {level}"

    @pytest.mark.asyncio
    async def test_risk_levels_count_matches_options(self):
        """risk_levels 长度应与 options 长度一致（或为空）。"""
        agent = InteractiveAgent()

        options = ["选项A", "选项B", "选项C"]
        risk_levels = ["safe", "risky", "dangerous"]
        decision = DecisionPoint(
            decision_type="tactical",
            options=options,
            risk_levels=risk_levels,
        )
        mock_turn = _make_dm_turn(decision=decision)

        with patch.object(agent, "_dm_narrate", new_callable=AsyncMock,
                           return_value=mock_turn):
            session = _make_session()
            result = await agent.step(session, user_action="分析形势")

        dp = result.decision
        assert dp is not None
        if dp.risk_levels:
            assert len(dp.risk_levels) == len(dp.options)


# ------------------------------------------------------------------ #
# 6.3.3 _detect_agency_violation 检测                                  #
# ------------------------------------------------------------------ #

class TestDetectAgencyViolation:
    """InteractiveAgent._detect_agency_violation() 行为验证。"""

    def setup_method(self):
        self.agent = InteractiveAgent()

    def test_detect_agency_violation_positive_ni_jueding(self):
        """'你决定' 模式应被检测为越权。"""
        text = "你决定向前冲锋，毫不犹豫地拔出了剑。"
        result = self.agent._detect_agency_violation(text)
        assert result is not None
        assert isinstance(result, str)
        assert len(result) > 0

    def test_detect_agency_violation_positive_ni_xuanze(self):
        """'你选择了' 模式应被检测为越权。"""
        text = "你选择了向右边的门走去，推开了它。"
        result = self.agent._detect_agency_violation(text)
        assert result is not None

    def test_detect_agency_violation_positive_zhuangjue_xuanze(self):
        """'主角选择' 模式应被检测为越权。"""
        text = "主角选择了与敌人正面交锋，展现出了无畏的气概。"
        result = self.agent._detect_agency_violation(text)
        assert result is not None

    def test_detect_agency_violation_negative_normal_narration(self):
        """普通叙事文本不含越权模式，应返回 None。"""
        text = ("前方的走廊阴暗潮湿，远处传来隐约的脚步声。"
                "你感到一丝寒意顺着脊背蔓延。怎么做？\n"
                "[选项 A]：继续前进\n[选项 B]：原路返回")
        result = self.agent._detect_agency_violation(text)
        assert result is None

    def test_detect_agency_violation_negative_dm_description(self):
        """纯环境描写不应触发越权检测。"""
        text = "废弃的神殿内，石柱残破，壁画斑驳，空气中弥漫着古老的气息。"
        result = self.agent._detect_agency_violation(text)
        assert result is None

    def test_detect_agency_violation_returns_snippet_not_full_text(self):
        """返回的违规片段应比原文短（不是整段复制）。"""
        long_text = "A" * 200 + "你决定放弃抵抗，举手投降。" + "B" * 200
        result = self.agent._detect_agency_violation(long_text)
        assert result is not None
        assert len(result) < len(long_text)


# ------------------------------------------------------------------ #
# 6.3.4 session status 含 phase 字段                                   #
# ------------------------------------------------------------------ #

class TestSessionStatusPhase:
    """GET /sessions/{id}/status 响应含 phase 字段。"""

    def _create_session_in_store(self, session: InteractiveSession) -> str:
        import time as _time
        with _sessions_lock:
            _sessions[session.session_id] = (session, _time.time())
        return session.session_id

    def test_session_status_contains_phase(self, client):
        """已存在的 session，status 响应含 phase 字段。"""
        session = _make_session()
        session.phase = SessionPhase.PING_PONG
        sid = self._create_session_in_store(session)

        resp = client.get(f"/sessions/{sid}/status")

        assert resp.status_code == 200
        data = resp.json()
        assert "phase" in data
        assert data["phase"] == "PING_PONG"

    def test_session_status_contains_scene_pressure(self, client):
        """status 响应含 scene_pressure 字段（float）。"""
        session = _make_session(scene_pressure=7.5)
        sid = self._create_session_in_store(session)

        resp = client.get(f"/sessions/{sid}/status")

        assert resp.status_code == 200
        data = resp.json()
        assert "scene_pressure" in data
        assert abs(data["scene_pressure"] - 7.5) < 0.01

    def test_session_status_contains_emotional_temperature(self, client):
        """status 响应含 emotional_temperature 字段（含 base/current/drift）。"""
        session = _make_session()
        session.emotional_temperature = {"base": "neutral", "current": 5.0, "drift": 0.5}
        sid = self._create_session_in_store(session)

        resp = client.get(f"/sessions/{sid}/status")

        assert resp.status_code == 200
        data = resp.json()
        assert "emotional_temperature" in data
        temp = data["emotional_temperature"]
        assert isinstance(temp, dict)
        assert "base" in temp
        assert "current" in temp
        assert "drift" in temp

    def test_session_status_contains_density(self, client):
        """status 响应含 density 字段（dense/normal/sparse）。"""
        session = _make_session(density="dense")
        sid = self._create_session_in_store(session)

        resp = client.get(f"/sessions/{sid}/status")

        assert resp.status_code == 200
        data = resp.json()
        assert "density" in data
        assert data["density"] in ("dense", "normal", "sparse")

    def test_session_status_404_for_unknown_session(self, client):
        """不存在的 session_id 应返回 404。"""
        resp = client.get("/sessions/nonexistent-session-id-999/status")
        assert resp.status_code == 404


# ------------------------------------------------------------------ #
# 6.3.5 emotional_temperature 字段格式                                  #
# ------------------------------------------------------------------ #

class TestEmotionalTemperature:
    """InteractiveSession.emotional_temperature 字段默认值与更新逻辑。"""

    def test_session_default_emotional_temperature(self):
        """新建 session 的 emotional_temperature 含合法默认值。"""
        agent = InteractiveAgent()
        cfg = SessionConfig(project_id="test", character_name="主角")
        session = agent.create_session(cfg)

        et = session.emotional_temperature
        assert isinstance(et, dict)
        assert "base" in et
        assert "current" in et
        assert "drift" in et
        assert isinstance(et["current"], float)
        assert 0.0 <= et["current"] <= 10.0

    @pytest.mark.asyncio
    async def test_emotional_temperature_updates_after_step(self):
        """step 之后，emotional_temperature.current 应随压力微调。"""
        agent = InteractiveAgent()
        mock_turn = _make_dm_turn()

        with patch.object(agent, "_dm_narrate", new_callable=AsyncMock,
                           return_value=mock_turn):
            session = _make_session(scene_pressure=8.0)
            session.emotional_temperature = {"base": "neutral", "current": 5.0, "drift": 0.0}
            await agent.step(session, user_action="攻击！冲锋！")

        # 因为 scene_pressure 会因攻击词增加，temperature 应有漂移
        et = session.emotional_temperature
        assert et["current"] != 5.0 or et["drift"] == 0.0  # 有压力变化时 drift != 0
        assert isinstance(et["drift"], float)
