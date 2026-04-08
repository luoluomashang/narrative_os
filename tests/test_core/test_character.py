"""tests/test_core/test_character.py — CharacterState + ConstraintEngine 单元测试"""
import pytest
from narrative_os.core.character import (
    ArcStage,
    BehaviorConstraint,
    CharacterState,
    VoiceFingerprint,
)


# ------------------------------------------------------------------ #
# Fixtures                                                             #
# ------------------------------------------------------------------ #

@pytest.fixture
def hero() -> CharacterState:
    return CharacterState(
        name="林风",
        traits=["坚韧", "冷静"],
        goal="将门派发扬光大",
        arc_stage=ArcStage.DEFENSIVE,
        behavior_constraints=[
            BehaviorConstraint(rule="不出卖同伴", severity="hard"),
            BehaviorConstraint(rule="避免无谓杀戮", severity="soft"),
        ],
        voice_fingerprint=VoiceFingerprint(
            under_pressure="沉默片刻后回应",
            when_lying="眼神微避",
            deflection="转移话题",
            emotional_peak="声音低沉",
            default_length="short",
        ),
    )


# ------------------------------------------------------------------ #
# BehaviorConstraint                                                   #
# ------------------------------------------------------------------ #

class TestBehaviorConstraint:
    def test_hard_constraint_triggers(self, hero: CharacterState):
        result = hero.check_constraints("他决定出卖同伴换取性命")
        assert result.violated
        hard_violations = [v for v in result.violations if v.severity == "hard"]
        assert len(hard_violations) >= 1

    def test_soft_constraint_triggers(self, hero: CharacterState):
        result = hero.check_constraints("他上前，随意杀戮了几名路人")
        assert result.violated
        soft = [v for v in result.violations if v.severity == "soft"]
        assert len(soft) >= 1

    def test_no_constraint_violated(self, hero: CharacterState):
        result = hero.check_constraints("他默默地帮助了村民，然后离开。")
        assert not result.violated

    def test_constraint_result_has_suggestion(self, hero: CharacterState):
        result = hero.check_constraints("他要抛弃队友逃跑")
        assert result.violated
        assert any(v.suggestion for v in result.violations)


# ------------------------------------------------------------------ #
# Emotion / Relationship                                               #
# ------------------------------------------------------------------ #

class TestStateOperations:
    def test_update_emotion(self, hero: CharacterState):
        hero.update_emotion("愤怒")
        assert hero.emotion == "愤怒"

    def test_update_relationship(self, hero: CharacterState):
        hero.update_relationship("elder_zhang", 0.8)
        assert hero.relationships["elder_zhang"] == pytest.approx(0.8)

    def test_relationship_clamp_positive(self, hero: CharacterState):
        hero.update_relationship("ally", 1.5)
        assert hero.relationships["ally"] == pytest.approx(1.0)

    def test_relationship_clamp_negative(self, hero: CharacterState):
        hero.update_relationship("enemy", -1.5)
        assert hero.relationships["enemy"] == pytest.approx(-1.0)


# ------------------------------------------------------------------ #
# Snapshot / Rollback                                                   #
# ------------------------------------------------------------------ #

class TestSnapshotRollback:
    def test_snapshot_and_rollback(self, hero: CharacterState):
        # chapter 1 baseline
        hero.snapshot(chapter=1)

        # mutate
        hero.update_emotion("愤怒")
        hero.update_relationship("rival", -0.9)
        hero.snapshot(chapter=2)

        # verify chapter 2
        assert hero.emotion == "愤怒"
        assert "rival" in hero.relationships

        # rollback to chapter 1
        hero.rollback_to_chapter(1)
        assert hero.emotion == "平静"  # default initial emotion
        assert "rival" not in hero.relationships

    def test_rollback_missing_chapter_raises(self, hero: CharacterState):
        with pytest.raises(KeyError):
            hero.rollback_to_chapter(999)


# ------------------------------------------------------------------ #
# Arc Progression                                                       #
# ------------------------------------------------------------------ #

class TestArcProgression:
    def test_arc_stage_names(self, hero: CharacterState):
        prog = hero.get_arc_progression()
        assert "current_stage" in prog
        assert "current_stage_name" in prog
        assert "progress_pct" in prog
        assert "completed_stages" in prog

    def test_advance_arc_stage(self, hero: CharacterState):
        hero.advance_arc()
        assert hero.arc_stage == ArcStage.CRACKING


# ------------------------------------------------------------------ #
# record_event / set_arc_stage / kill                                  #
# ------------------------------------------------------------------ #

class TestMutations:
    def test_record_event_appends(self, hero: CharacterState):
        assert len(hero.memory) == 0
        hero.record_event(chapter=1, event="遇见老者", emotion="好奇", importance=0.7)
        assert len(hero.memory) == 1
        assert hero.memory[0].event == "遇见老者"
        assert hero.memory[0].chapter == 1

    def test_record_event_default_importance(self, hero: CharacterState):
        hero.record_event(chapter=2, event="某次小事")
        assert hero.memory[0].importance == 0.5

    def test_set_arc_stage(self, hero: CharacterState):
        hero.set_arc_stage(ArcStage.ACCEPTING)
        assert hero.arc_stage == ArcStage.ACCEPTING

    def test_kill_sets_is_alive_false(self, hero: CharacterState):
        assert hero.is_alive is True
        hero.kill()
        assert hero.is_alive is False


# ------------------------------------------------------------------ #
# Serialization (to_json / from_json)                                  #
# ------------------------------------------------------------------ #

class TestSerialization:
    def test_to_json_returns_string(self, hero: CharacterState, tmp_path):
        j = hero.to_json()
        assert isinstance(j, str)
        assert "林风" in j

    def test_to_json_writes_file(self, hero: CharacterState, tmp_path):
        p = tmp_path / "char.json"
        hero.to_json(path=p)
        assert p.exists()
        assert "林风" in p.read_text(encoding="utf-8")

    def test_from_json_roundtrip(self, hero: CharacterState, tmp_path):
        p = tmp_path / "char.json"
        hero.to_json(path=p)
        loaded = CharacterState.from_json(p)
        assert loaded.name == hero.name
        assert loaded.arc_stage == hero.arc_stage

    def test_repr_contains_name(self, hero: CharacterState):
        r = repr(hero)
        assert "林风" in r
        assert "CharacterState" in r


# ------------------------------------------------------------------ #
# Arc Progression — full path                                           #
# ------------------------------------------------------------------ #

class TestArcProgressionFull:
    def test_next_stage_final_returns_done(self, hero: CharacterState):
        hero.set_arc_stage(ArcStage.TRANSFORMED)
        prog = hero.get_arc_progression()
        assert prog["next_stage"] == "完成"

    def test_progress_pct_first_stage(self, hero: CharacterState):
        prog = hero.get_arc_progression()
        assert prog["progress_pct"] == 20  # 1/5 * 100

    def test_advance_arc_last_stage_stays(self, hero: CharacterState):
        hero.set_arc_stage(ArcStage.TRANSFORMED)
        hero.advance_arc()  # should not raise or go beyond last
        assert hero.arc_stage == ArcStage.TRANSFORMED


# ------------------------------------------------------------------ #
# ConstraintCheckResult — to_issue_list                                #
# ------------------------------------------------------------------ #

class TestConstraintCheckResult:
    def test_to_issue_list(self, hero: CharacterState):
        result = hero.check_constraints("他决定出卖同伴换取性命")
        issues = result.to_issue_list()
        assert len(issues) >= 1
        assert "[OOC]" in issues[0]
