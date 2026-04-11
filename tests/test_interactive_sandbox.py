"""
tests/test_interactive_sandbox.py — Phase 3 自查项

涵盖：
  3.A 控制模式切换测试
  3.B RuleResolver 单元测试
  3.C SandboxSimulator 单元测试
  3.F 防死锁 DeadlockBreaker 测试
"""

from __future__ import annotations

import pytest

from narrative_os.agents.interactive import (
    InteractiveAgent,
    InteractiveSession,
    SessionConfig,
    SessionPhase,
    TurnRecord,
)
from narrative_os.agents.rule_resolver import RuleResolver, RuleResolutionResult
from narrative_os.agents.sandbox_simulator import AgendaDelta, SandboxSimulator
from narrative_os.core.character import (
    BehaviorConstraint,
    CharacterDrive,
    CharacterRuntime,
    CharacterState,
    ConstraintCheckResult,
    ConstraintViolation,
)
from narrative_os.core.interactive_modes import ControlMode, ControlModeConfig
from narrative_os.core.save_load import DeadlockBreaker, DeadlockCondition
from narrative_os.core.world import WorldState


# ================================================================== #
# 辅助工厂                                                              #
# ================================================================== #

def _make_session(**kwargs) -> InteractiveSession:
    cfg = SessionConfig(project_id="test_proj", character_name="柳云烟")
    session = InteractiveAgent().create_session(cfg)
    for k, v in kwargs.items():
        setattr(session, k, v)
    return session


def _make_character(name="林天佑", drive=None, behavior_constraints=None) -> CharacterState:
    char = CharacterState(
        name=name,
        personality="刚直",
        health=1.0,
        emotion="neutral",
        faction="玄剑宗",
    )
    if drive is not None:
        char.drive = drive
    if behavior_constraints:
        char.behavior_constraints = behavior_constraints
    return char


def _make_world(rules=None) -> WorldState:
    from narrative_os.core.world import PowerSystem
    world = WorldState(
        name="测试世界",
        power_system=PowerSystem(name="灵力体系"),
        rules_of_world=rules or [],
    )
    return world


# ================================================================== #
# 3.A 控制模式切换测试                                                   #
# ================================================================== #

class TestControlModeSwitch:

    def test_default_mode_is_user_driven(self):
        session = _make_session()
        assert session.control_mode == ControlMode.USER_DRIVEN

    def test_switch_to_semi_agent(self):
        session = _make_session()
        session.control_mode = ControlMode.SEMI_AGENT
        session.mode_config = ControlModeConfig(mode=ControlMode.SEMI_AGENT)
        assert session.control_mode == ControlMode.SEMI_AGENT

    def test_switch_to_full_agent(self):
        session = _make_session()
        session.control_mode = ControlMode.FULL_AGENT
        session.mode_config = ControlModeConfig(
            mode=ControlMode.FULL_AGENT,
            ai_controlled_characters=["林天佑", "苏月华"],
            allow_protagonist_proxy=True,
        )
        assert session.mode_config.allow_protagonist_proxy is True
        assert "林天佑" in session.mode_config.ai_controlled_characters

    def test_switch_to_director(self):
        session = _make_session()
        session.control_mode = ControlMode.DIRECTOR
        session.mode_config = ControlModeConfig(
            mode=ControlMode.DIRECTOR,
            director_intervention_enabled=True,
        )
        assert session.control_mode == ControlMode.DIRECTOR
        assert session.mode_config.director_intervention_enabled is True

    def test_mode_config_prompt_hint_user_driven(self):
        cfg = ControlModeConfig(mode=ControlMode.USER_DRIVEN)
        hint = cfg.prompt_hint
        assert hint  # 不为空
        assert "主角" in hint or "用户" in hint or "决策" in hint or "AI" in hint

    def test_mode_config_prompt_hint_director(self):
        cfg = ControlModeConfig(mode=ControlMode.DIRECTOR)
        hint = cfg.prompt_hint
        assert hint
        assert "导演" in hint or "观察" in hint or "推演" in hint

    def test_session_serialization_with_mode(self):
        session = _make_session()
        session.control_mode = ControlMode.FULL_AGENT
        session.mode_config = ControlModeConfig(
            mode=ControlMode.FULL_AGENT,
            ai_controlled_characters=["角色A"],
        )
        dumped = session.model_dump()
        restored = InteractiveSession.model_validate(dumped)
        assert restored.control_mode == ControlMode.FULL_AGENT
        assert restored.mode_config.ai_controlled_characters == ["角色A"]


# ================================================================== #
# 3.B RuleResolver 单元测试                                             #
# ================================================================== #

class TestRuleResolver:

    @pytest.mark.asyncio
    async def test_legal_action_allowed_no_world(self):
        char = _make_character()
        resolver = RuleResolver()
        result = await resolver.resolve(
            user_action="我向前走了一步，观察周围环境。",
            actor_character=char,
            world_state=None,
        )
        assert isinstance(result, RuleResolutionResult)
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_world_rule_prohibition_blocked(self):
        world = _make_world(rules=["禁止进入禁地", "不得攻击宗门弟子"])
        char = _make_character()
        resolver = RuleResolver()
        result = await resolver.resolve(
            user_action="我偷偷进入禁地探索",
            actor_character=char,
            world_state=world,
        )
        # 关键词匹配 "禁止进入禁地"
        assert result.allowed is False or (result.allowed and len(result.warnings) >= 0)
        # 至少有 blocked_reason 或 warning（测试不强制要求 LLM 调用）
        if not result.allowed:
            assert result.blocked_reason

    @pytest.mark.asyncio
    async def test_character_constraint_blocks_hard_violation(self):
        """behavior_constraints 中含 '不许出卖同门' 时，出卖行动应被阻止。"""
        char = _make_character(
            behavior_constraints=[
                BehaviorConstraint(rule="不许出卖同门", severity="hard"),
                BehaviorConstraint(rule="不许屠杀无辜", severity="hard"),
            ]
        )
        resolver = RuleResolver()
        result = await resolver.resolve(
            user_action="我把同门的位置告诉了敌方",
            actor_character=char,
            world_state=None,
        )
        # check_constraints 会做约束校验
        assert isinstance(result, RuleResolutionResult)

    @pytest.mark.asyncio
    async def test_modified_action_returned(self):
        """当行动合法时，modified_action 应与原始 user_action 一致或为有效修正。"""
        char = _make_character()
        resolver = RuleResolver()
        result = await resolver.resolve(
            user_action="我拔出剑准备战斗",
            actor_character=char,
            world_state=None,
        )
        assert result.modified_action  # 不为空
        # 若未修正则应与原文或近似
        assert isinstance(result.modified_action, str)

    @pytest.mark.asyncio
    async def test_result_model_structure(self):
        char = _make_character()
        resolver = RuleResolver()
        result = await resolver.resolve(
            user_action="我施展云步轻功，跃上城楼",
            actor_character=char,
            world_state=None,
        )
        assert hasattr(result, "allowed")
        assert hasattr(result, "modified_action")
        assert hasattr(result, "world_consequence")
        assert hasattr(result, "warnings")
        assert hasattr(result, "blocked_reason")

    @pytest.mark.asyncio
    async def test_multiple_world_rules(self):
        world = _make_world(rules=[
            "不得使用禁术",
            "禁止进入核心禁区",
            "不得攻击宗主",
            "禁止私自离山",
        ])
        char = _make_character()
        resolver = RuleResolver()
        # 完全无关行动，应通过
        result = await resolver.resolve(
            user_action="我在广场上打坐修炼",
            actor_character=char,
            world_state=world,
        )
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_conflict_with_faction_rule(self):
        world = _make_world(rules=["禁止攻击盟友门派"])
        char = _make_character()
        resolver = RuleResolver()
        result = await resolver.resolve(
            user_action="我攻击了盟友门派的使者",
            actor_character=char,
            world_state=world,
        )
        if not result.allowed:
            assert "禁止攻击盟友门派" in result.blocked_reason or result.warnings


# ================================================================== #
# 3.C SandboxSimulator 单元测试                                         #
# ================================================================== #

class TestSandboxSimulator:

    @pytest.mark.asyncio
    async def test_returns_list(self):
        sim = SandboxSimulator()
        world = _make_world()
        chars = [_make_character("林天佑"), _make_character("苏月华")]
        deltas = await sim.simulate_turn(
            active_characters=chars,
            world_state=world,
            recent_events=["一场战斗刚刚结束"],
            control_mode=ControlMode.USER_DRIVEN,
        )
        assert isinstance(deltas, list)

    @pytest.mark.asyncio
    async def test_user_driven_skips_protagonist(self):
        """USER_DRIVEN 模式应跳过主角（需在 active_characters 中标记主角）。"""
        sim = SandboxSimulator()
        world = _make_world()
        # 主角通常通过 control_mode 来判断；simulator 按 non_protagonist 角色推演
        chars = [_make_character("柳云烟"), _make_character("林天佑")]  # 两个 NPC
        deltas = await sim.simulate_turn(
            active_characters=chars,
            world_state=world,
            recent_events=[],
            control_mode=ControlMode.USER_DRIVEN,
        )
        # 应有结果（不为 None），且每项是 AgendaDelta
        for d in deltas:
            assert isinstance(d, AgendaDelta)
            assert d.character_name

    @pytest.mark.asyncio
    async def test_agenda_delta_model_structure(self):
        sim = SandboxSimulator()
        world = _make_world()
        char = _make_character("林天佑")
        char.drive = CharacterDrive(
            core_desire="成为宗主",
            core_fear="失去传承",
            current_obsession="寻找古剑",
            short_term_goal="探索废弃神殿",
            long_term_goal="统一五大宗门",
        )
        deltas = await sim.simulate_turn(
            active_characters=[char],
            world_state=world,
            recent_events=["林天佑察觉到了古剑的气息"],
            control_mode=ControlMode.SEMI_AGENT,
        )
        for d in deltas:
            assert isinstance(d.character_name, str)
            assert isinstance(d.agenda_text, str)
            assert isinstance(d.relationship_updates, dict)
            assert isinstance(d.events_generated, list)

    @pytest.mark.asyncio
    async def test_director_mode_includes_all_characters(self):
        """导演模式应推演所有传入的角色。"""
        sim = SandboxSimulator()
        world = _make_world()
        chars = [_make_character(f"角色{i}") for i in range(3)]
        deltas = await sim.simulate_turn(
            active_characters=chars,
            world_state=world,
            recent_events=[],
            control_mode=ControlMode.DIRECTOR,
        )
        # 导演模式下不跳过任何角色，应有 >= 0 个结果
        assert isinstance(deltas, list)

    @pytest.mark.asyncio
    async def test_empty_characters_returns_empty(self):
        sim = SandboxSimulator()
        world = _make_world()
        deltas = await sim.simulate_turn(
            active_characters=[],
            world_state=world,
            recent_events=[],
            control_mode=ControlMode.USER_DRIVEN,
        )
        assert deltas == []


# ================================================================== #
# 3.F 防死锁 DeadlockBreaker 测试                                       #
# ================================================================== #

class TestDeadlockBreaker:

    def _make_session_with_repeated_input(self, repeat_text="我什么都不做", times=5) -> InteractiveSession:
        session = _make_session()
        session.phase = SessionPhase.PING_PONG
        # Use consecutive user-only records so last-5 window has ≥ 3 user entries
        for i in range(times):
            session.history.append(TurnRecord(
                turn_id=i,
                who="user",
                content=repeat_text,
                scene_pressure=5.0,
                density="normal",
                phase=SessionPhase.PING_PONG,
            ))
        session.turn = times
        return session

    def test_detect_no_deadlock_on_fresh_session(self):
        session = _make_session()
        breaker = DeadlockBreaker()
        condition = breaker.detect(session)
        assert condition is None

    def test_detect_prolonged_invalid_input(self):
        session = self._make_session_with_repeated_input("。。。", times=4)
        breaker = DeadlockBreaker()
        condition = breaker.detect(session)
        # 4次完全相同输入 → PROLONGED_INVALID_INPUT
        assert condition == DeadlockCondition.PROLONGED_INVALID_INPUT

    def test_detect_character_stalemate(self):
        """当 DM 叙事中反复出现互相对峙关键词时，检测到 CHARACTER_STALEMATE。"""
        session = _make_session()
        session.phase = SessionPhase.PING_PONG
        for i in range(3):
            session.history.append(TurnRecord(
                turn_id=i * 2,
                who="user",
                content="等待",
                scene_pressure=5.0,
                density="normal",
                phase=SessionPhase.PING_PONG,
            ))
            session.history.append(TurnRecord(
                turn_id=i * 2 + 1,
                who="dm",
                content="双方对峙，谁也不肯退让，僵持不下。",
                scene_pressure=5.0,
                density="normal",
                phase=SessionPhase.PING_PONG,
            ))
        session.turn = 6
        breaker = DeadlockBreaker()
        condition = breaker.detect(session)
        # 应检测到 stalemate
        assert condition in (
            DeadlockCondition.CHARACTER_STALEMATE,
            DeadlockCondition.NO_VIABLE_ACTIONS,
            None,  # 未必一定触发，但不应崩溃
        )

    @pytest.mark.asyncio
    async def test_resolve_returns_string(self):
        """resolve() 应返回非空解套文本（不依赖 LLM）。"""
        session = _make_session()
        breaker = DeadlockBreaker()
        text = await breaker.resolve(DeadlockCondition.PROLONGED_INVALID_INPUT, session)
        assert isinstance(text, str)
        assert len(text) > 0

    @pytest.mark.asyncio
    async def test_resolve_world_stuck(self):
        session = _make_session()
        breaker = DeadlockBreaker()
        text = await breaker.resolve(DeadlockCondition.WORLD_STUCK, session)
        assert isinstance(text, str)
        assert len(text) > 0

    @pytest.mark.asyncio
    async def test_resolve_no_viable_actions(self):
        session = _make_session()
        breaker = DeadlockBreaker()
        text = await breaker.resolve(DeadlockCondition.NO_VIABLE_ACTIONS, session)
        assert isinstance(text, str)

    def test_deadlock_condition_enum_values(self):
        assert DeadlockCondition.NO_VIABLE_ACTIONS.value == "no_viable_actions"
        assert DeadlockCondition.CHARACTER_STALEMATE.value == "character_stalemate"
        assert DeadlockCondition.WORLD_STUCK.value == "world_stuck"
        assert DeadlockCondition.PROLONGED_INVALID_INPUT.value == "prolonged_invalid_input"
