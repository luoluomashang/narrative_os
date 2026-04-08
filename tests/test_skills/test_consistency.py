"""tests/test_skills/test_consistency.py — ConsistencyChecker 单元测试"""
from __future__ import annotations

import pytest

from narrative_os.core.character import ArcStage, BehaviorConstraint, CharacterState
from narrative_os.core.plot import NodeType, PlotGraph
from narrative_os.core.world import PowerSystem, WorldState
from narrative_os.skills.consistency import ConsistencyChecker, ConsistencyReport


# ------------------------------------------------------------------ #
# Fixtures                                                             #
# ------------------------------------------------------------------ #

@pytest.fixture
def checker() -> ConsistencyChecker:
    return ConsistencyChecker()


@pytest.fixture
def hero() -> CharacterState:
    return CharacterState(
        name="林风",
        traits=["侠义"],
        goal="复仇",
        behavior_constraints=[
            BehaviorConstraint(rule="不出卖同伴", severity="hard"),
            BehaviorConstraint(rule="不随意杀戮", severity="soft"),
        ],
    )


@pytest.fixture
def world() -> WorldState:
    w = WorldState(
        factions={},
        power_system=PowerSystem(name="修炼体系"),
        geography={},
        rules_of_world=["修士不得伤害凡人"],
    )
    return w


@pytest.fixture
def graph() -> PlotGraph:
    g = PlotGraph()
    g.create_event("setup", type=NodeType.SETUP, summary="林风入宗")
    return g


# ------------------------------------------------------------------ #
# Basic checks                                                         #
# ------------------------------------------------------------------ #

class TestBasicChecks:
    def test_clean_text_passes(self, checker, hero):
        report = checker.check("林风帮助村民搬运物资，悄然离开。", characters=[hero])
        assert report.passed
        assert report.score == pytest.approx(1.0)

    def test_hard_violation_fails(self, checker, hero):
        report = checker.check("林风决定出卖同伴换取逃跑机会。", characters=[hero])
        assert not report.passed
        hard = report.hard_issues
        assert len(hard) >= 1

    def test_soft_violation_does_not_fail(self, checker, hero):
        report = checker.check("他随意杀了几个路人。", characters=[hero])
        # soft警告不导致 passed=False，只降分
        assert len(report.soft_issues) >= 1
        # score降低
        assert report.score < 1.0

    def test_report_score_decreases_with_issues(self, checker, hero):
        clean = checker.check("林风点了点头。", characters=[hero])
        bad = checker.check("林风出卖同伴，随意杀戮了路人。", characters=[hero])
        assert bad.score < clean.score


# ------------------------------------------------------------------ #
# Dimensions                                                           #
# ------------------------------------------------------------------ #

class TestDimensions:
    def test_world_rule_violation_detected(self, checker, world):
        # 文本包含世界规则中的违禁行为
        report = checker.check("他伤害凡人，无人阻拦。", world=world)
        world_issues = [i for i in report.issues if i.dimension == "world"]
        assert len(world_issues) >= 1

    def test_timeline_retro_word_detected(self, checker):
        report = checker.check("他回到了三年前的家门口。", chapter=5)
        tl_issues = [i for i in report.issues if i.dimension == "timeline"]
        assert len(tl_issues) >= 1
        assert tl_issues[0].severity == "soft"

    def test_no_false_positive_on_normal_text(self, checker, hero, world):
        text = "林风走进大殿，向长老行礼。长老满意地点头。"
        report = checker.check(text, characters=[hero], world=world, chapter=2)
        assert report.passed


# ------------------------------------------------------------------ #
# ConsistencyReport                                                     #
# ------------------------------------------------------------------ #

class TestConsistencyReport:
    def test_summary_passed(self):
        r = ConsistencyReport(passed=True, score=1.0)
        assert "通过" in r.summary()

    def test_summary_failed(self, checker, hero):
        report = checker.check("出卖同伴", characters=[hero])
        assert "硬冲突" in report.summary() or "soft" in report.summary() or not report.passed

    def test_issue_has_suggestion(self, checker, hero):
        report = checker.check("林风出卖了同伴。", characters=[hero])
        for issue in report.issues:
            assert isinstance(issue.suggestion, str)
            assert len(issue.suggestion) > 0
