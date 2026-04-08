"""tests/test_execution/test_context_builder.py — ContextBuilder 单元测试"""
from __future__ import annotations

import pytest

from narrative_os.core.character import ArcStage, BehaviorConstraint, CharacterState
from narrative_os.core.plot import NodeType, PlotGraph
from narrative_os.core.world import PowerSystem, WorldState
from narrative_os.execution.context_builder import (
    ChapterTarget,
    ConstraintPack,
    ContextBuilder,
    WriteContext,
)


# ------------------------------------------------------------------ #
# Fixtures                                                             #
# ------------------------------------------------------------------ #

@pytest.fixture
def target() -> ChapterTarget:
    return ChapterTarget(
        chapter=3,
        volume=1,
        target_summary="主角被围攻，以一敌百",
        word_count_target=2000,
        tension_target=0.8,
        hook_type="cliffhanger",
    )


@pytest.fixture
def hero() -> CharacterState:
    return CharacterState(
        name="林风",
        traits=["冷静", "隐忍"],
        goal="复仇",
        emotion="愤怒",
        arc_stage=ArcStage.DEFENSIVE,
        behavior_constraints=[
            BehaviorConstraint(rule="不出卖同伴", severity="hard"),
        ],
    )


@pytest.fixture
def world() -> WorldState:
    w = WorldState(
        factions={},
        power_system=PowerSystem(name="修炼等级制度"),
        geography={},
        rules_of_world=["修士不得伤害凡人"],
    )
    w.add_faction("九天宗", hostility_map={"魔道": 0.9})
    w.advance_timeline(1, "林风加入九天宗")
    return w


@pytest.fixture
def graph() -> PlotGraph:
    g = PlotGraph()
    g.create_event("A", type=NodeType.SETUP, summary="林风入宗", tension=0.2)
    g.create_event("B", type=NodeType.CONFLICT, summary="被长老针对", tension=0.7)
    g.link_events("A", "B", relation="causal")
    return g


# ------------------------------------------------------------------ #
# ChapterTarget                                                         #
# ------------------------------------------------------------------ #

class TestChapterTarget:
    def test_defaults(self):
        ct = ChapterTarget(chapter=1)
        assert ct.word_count_target == 2000
        assert ct.tension_target == 0.6
        assert ct.hook_type == "suspense"

    def test_full_fields(self, target):
        assert target.chapter == 3
        assert target.tension_target == pytest.approx(0.8)


# ------------------------------------------------------------------ #
# ContextBuilder.build()                                               #
# ------------------------------------------------------------------ #

class TestContextBuilderBuild:
    def test_builds_without_optional_params(self, target):
        cb = ContextBuilder()
        ctx = cb.build(chapter_target=target)
        assert ctx.chapter_target.chapter == 3
        assert ctx.characters == []
        assert ctx.active_plot_nodes == []

    def test_gate2_plot_nodes(self, target, graph):
        cb = ContextBuilder()
        ctx = cb.build(chapter_target=target, plot_graph=graph)
        assert len(ctx.active_plot_nodes) >= 1
        # 高张力节点排在前面
        tensions = [n["tension"] for n in ctx.active_plot_nodes]
        assert tensions == sorted(tensions, reverse=True)

    def test_gate3_character_snapshot(self, target, hero):
        cb = ContextBuilder()
        ctx = cb.build(chapter_target=target, characters=[hero])
        assert len(ctx.characters) == 1
        snap = ctx.characters[0]
        assert snap.name == "林风"
        assert snap.emotion == "愤怒"
        assert snap.goal == "复仇"

    def test_gate4_world_snapshot(self, target, world):
        cb = ContextBuilder()
        ctx = cb.build(chapter_target=target, world=world)
        assert "九天宗" in ctx.world.active_factions
        assert len(ctx.world.recent_timeline) >= 1
        assert ctx.world.power_system_name == "修炼等级制度"
        assert "修士不得伤害凡人" in ctx.world.key_rules

    def test_gate7_constraints_populated(self, target):
        cb = ContextBuilder()
        ctx = cb.build(chapter_target=target)
        # human_touch_hints always populated (fallback)
        assert len(ctx.constraints.human_touch_hints) >= 1

    def test_gate9_style_summary(self, target):
        cb = ContextBuilder()
        ctx = cb.build(chapter_target=target)
        assert isinstance(ctx.style_summary, str)


# ------------------------------------------------------------------ #
# to_system_prompt()                                                    #
# ------------------------------------------------------------------ #

class TestToSystemPrompt:
    def test_contains_chapter_info(self, target, hero, world, graph):
        cb = ContextBuilder()
        ctx = cb.build(chapter_target=target, characters=[hero], world=world, plot_graph=graph)
        prompt = ctx.to_system_prompt()
        assert "第3章" in prompt or "章 3" in prompt
        assert "2000" in prompt
        assert "主角被围攻" in prompt

    def test_contains_character_name(self, target, hero):
        cb = ContextBuilder()
        ctx = cb.build(chapter_target=target, characters=[hero])
        prompt = ctx.to_system_prompt()
        assert "林风" in prompt

    def test_contains_world_faction(self, target, world):
        cb = ContextBuilder()
        ctx = cb.build(chapter_target=target, world=world)
        prompt = ctx.to_system_prompt()
        assert "九天宗" in prompt

    def test_contains_hook_type(self, target):
        cb = ContextBuilder()
        ctx = cb.build(chapter_target=target)
        prompt = ctx.to_system_prompt()
        assert "cliffhanger" in prompt

    def test_prompt_is_nonempty(self, target):
        cb = ContextBuilder()
        ctx = cb.build(chapter_target=target)
        prompt = ctx.to_system_prompt()
        assert len(prompt) > 100
