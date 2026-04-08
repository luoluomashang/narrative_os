"""
tests/test_interactive_hardening.py — 阶段 1：InteractiveAgent 强化测试
"""

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

def _make_agent(response_content: str) -> tuple[InteractiveAgent, MagicMock]:
    router = MagicMock()
    resp = MagicMock()
    resp.content = response_content
    resp.model_used = "gpt-4o-mini"
    router.call = AsyncMock(return_value=resp)
    return InteractiveAgent(router=router), router


def _make_session(agent: InteractiveAgent, pressure: float = 5.0) -> InteractiveSession:
    cfg = SessionConfig(
        project_id="test",
        character_name="林枫",
        opening_prompt="一座古老神殿矗立在荒野中。",
        initial_pressure=pressure,
    )
    return agent.create_session(cfg)


# ------------------------------------------------------------------ #
# 测试 1 — 决策截断：超长响应被截断到 density 限制                        #
# ------------------------------------------------------------------ #

async def test_decision_truncation_normal():
    """normal 密度（上限 300 字）：超长叙事被截断，选项块保留。"""
    long_narrative = "甲" * 400  # 400字，超出 normal 300 字限制
    option_block = "\n[选项 A]：向前冲\n[选项 B]：原地等待"
    content = long_narrative + option_block

    agent, _ = _make_agent(content)
    session = _make_session(agent)
    session.density = "normal"

    result = agent._apply_truncation(content, "normal")
    # 叙事部分应被截断到 300 字 + …
    assert result.startswith("甲" * 300 + "…")
    # 选项块应保留
    assert "[选项 A]" in result
    assert "[选项 B]" in result


async def test_decision_truncation_no_option_marker():
    """无决策标记时，超长内容被截断到 density 限制。"""
    agent, _ = _make_agent("")
    long_text = "乙" * 500

    result = agent._apply_truncation(long_text, "dense")
    assert len(result) == 151  # 150 chars + "…"
    assert result.endswith("…")


async def test_decision_truncation_within_limit():
    """短内容无需截断。"""
    agent, _ = _make_agent("")
    short_text = "丙" * 50 + "\n[选项 A]：行动"

    result = agent._apply_truncation(short_text, "normal")
    assert result == short_text  # 无变化


# ------------------------------------------------------------------ #
# 测试 2 — 代理权检测：命中代理词汇时触发重试标记                          #
# ------------------------------------------------------------------ #

async def test_proxy_detection_triggers_reprompt():
    """命中代理权词汇时，应触发最多 2 次重试，第 3 次写入 metadata 警告。"""
    violation_text = "你决定冲了上去，举起剑砍向敌人。\n[选项 A]：继续"

    router = MagicMock()
    resp = MagicMock()
    resp.content = violation_text
    resp.model_used = "gpt-4o-mini"
    # 三次都返回违规内容
    router.call = AsyncMock(return_value=resp)

    agent = InteractiveAgent(router=router)
    session = _make_session(agent)
    session.phase = SessionPhase.PING_PONG
    # set low density to avoid length issues
    session.density = "sparse"

    dm_turn = await agent._dm_narrate(session, context_hint="我冲过去")

    # 应该调用了 3 次 LLM（原始 + 2 次重试）
    assert router.call.call_count == 3
    # metadata 中有警告
    assert "agency_violation_warning" in dm_turn.metadata


async def test_proxy_detection_no_violation():
    """无违规内容时，LLM 只调用 1 次。"""
    clean_text = "夜色深沉，你站在神殿入口。\n[选项 A]：举起火把\n[选项 B]：等待"

    agent, router = _make_agent(clean_text)
    session = _make_session(agent)
    session.phase = SessionPhase.PING_PONG
    session.density = "sparse"

    await agent._dm_narrate(session, context_hint="我观察周围")

    assert router.call.call_count == 1


# ------------------------------------------------------------------ #
# 测试 3 — 帮回黑暗模式调高 temperature                                  #
# ------------------------------------------------------------------ #

def test_bangui_dark_raises_temperature():
    """帮回黑暗1 应返回 temperature=0.90。"""
    agent, _ = _make_agent("")
    params = agent._bangui_llm_params("帮回黑暗1")
    assert params["temperature"] == 0.90


def test_bangui_advance_lowers_temperature():
    """帮回推进1 应返回 temperature=0.65 且 max_tokens_multiplier=2.0。"""
    agent, _ = _make_agent("")
    params = agent._bangui_llm_params("帮回推进1")
    assert params["temperature"] == 0.65
    assert params["max_tokens_multiplier"] == 2.0


def test_bangui_active_temperature():
    """帮回主动1 应返回 temperature=0.75。"""
    agent, _ = _make_agent("")
    params = agent._bangui_llm_params("帮回主动1")
    assert params["temperature"] == 0.75


def test_bangui_passive_temperature():
    """帮回被动1 应返回 temperature=0.70。"""
    agent, _ = _make_agent("")
    params = agent._bangui_llm_params("帮回被动1")
    assert params["temperature"] == 0.70


def test_bangui_none_returns_empty():
    """bangui_id=None 返回空 dict。"""
    agent, _ = _make_agent("")
    assert agent._bangui_llm_params(None) == {}


# ------------------------------------------------------------------ #
# 测试 4 — PACING_ALERT：接近会话窗口上限时触发                          #
# ------------------------------------------------------------------ #

async def test_pacing_alert_near_context_limit():
    """turn=27/30（>=90%）时 step() 后 session.phase == PACING_ALERT。"""
    content = "夜色深沉。\n[选项 A]：向前\n[选项 B]：等待"
    agent, _ = _make_agent(content)

    cfg = SessionConfig(
        project_id="test",
        character_name="林枫",
        max_history_turns=30,
        initial_pressure=5.0,
    )
    session = agent.create_session(cfg)
    session.phase = SessionPhase.PING_PONG
    # 手动设置 turn 到 27（>=30*0.9=27）
    session.turn = 27
    # 填充历史防止 step 内部访问越界
    for i in range(27):
        session.history.append(TurnRecord(
            turn_id=i,
            who="dm" if i % 2 == 0 else "user",
            content="...",
            scene_pressure=5.0,
        ))

    await agent.step(session, user_action="我继续前进")

    assert session.phase == SessionPhase.PACING_ALERT
    # 最后一条 dm 记录应有 pacing_alert_reason
    dm_turns = [t for t in session.history if t.who == "dm"]
    assert "pacing_alert_reason" in dm_turns[-1].metadata


# ------------------------------------------------------------------ #
# 测试 5 — PACING_ALERT：连续 3 轮高压触发                               #
# ------------------------------------------------------------------ #

async def test_pacing_alert_sustained_pressure():
    """最近 3 次 DM 叙事 pressure >= 8 时触发 PACING_ALERT。"""
    content = "激战继续！\n[选项 A]：反击\n[选项 B]：撤退"
    agent, _ = _make_agent(content)

    session = _make_session(agent, pressure=9.0)
    session.phase = SessionPhase.PING_PONG
    # 填入 3 条 dm 记录，scene_pressure=9
    for i in range(3):
        session.history.append(TurnRecord(
            turn_id=i,
            who="dm",
            content="激战中...",
            scene_pressure=9.0,
        ))
    session.turn = 3

    await agent.step(session, "我发动攻击")
    assert session.phase == SessionPhase.PACING_ALERT


# ------------------------------------------------------------------ #
# 测试 6 — 决策提取降级链                                                #
# ------------------------------------------------------------------ #

def test_extract_decision_level1_standard():
    """Level 1：标准 [选项 X]：格式正确提取。"""
    agent, _ = _make_agent("")
    text = "场景描述。\n[选项 A]：举起火把\n[选项 B]：原地等待"
    d = agent._extract_decision(text)
    assert d is not None
    assert len(d.options) == 2
    assert "举起火把" in d.options[0]


def test_extract_decision_level2_variant():
    """Level 2：A. 格式被正确识别。"""
    agent, _ = _make_agent("")
    text = "你面临选择：\nA. 向前冲\nB. 原地隐蔽"
    d = agent._extract_decision(text)
    assert d is not None
    assert len(d.options) == 2


def test_extract_decision_level3_free_action():
    """Level 3：语义兜底，返回 is_free_action=True。"""
    agent, _ = _make_agent("")
    text = "四周布满了敌人，你将如何应对？"
    d = agent._extract_decision(text)
    assert d is not None
    assert d.is_free_action is True
    assert d.options == []


def test_extract_decision_fallback_returns_none():
    """无任何选择标记时返回 None。"""
    agent, _ = _make_agent("")
    text = "故事在继续，什么都没有发生。"
    d = agent._extract_decision(text)
    assert d is None
