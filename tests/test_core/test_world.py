"""tests/test_core/test_world.py — WorldState + FactionState + Sandbox Backend 单元测试"""
import pytest
from narrative_os.core.world import FactionState, WorldState, PowerSystem


# ------------------------------------------------------------------ #
# Fixtures                                                             #
# ------------------------------------------------------------------ #

@pytest.fixture
def world() -> WorldState:
    w = WorldState(
        factions={},
        power_system=PowerSystem(name="修炼等级制度"),
        geography={"地域": "东域修真界"},
        rules_of_world=["修士不得伤害凡人", "不得泄露宗门秘技"],
    )
    w.add_faction("九天宗", hostility_map={"魔道": 0.8})
    w.add_faction("魔道", hostility_map={"九天宗": 0.8})
    return w


# ------------------------------------------------------------------ #
# FactionState                                                          #
# ------------------------------------------------------------------ #

class TestFactionState:
    def test_update_hostility(self, world: WorldState):
        world.factions["九天宗"].update_hostility("魔道", 0.9)
        assert world.factions["九天宗"].hostility_map["魔道"] == pytest.approx(0.9)

    def test_hostility_clamp(self, world: WorldState):
        world.factions["九天宗"].update_hostility("魔道", 1.5)
        assert world.factions["九天宗"].hostility_map["魔道"] == pytest.approx(1.0)

    def test_hidden_plans(self, world: WorldState):
        world.factions["魔道"].add_hidden_plan("暗中渗透九天宗内部")
        world.factions["魔道"].add_hidden_plan("收集九天宗秘技")
        plans = world.factions["魔道"].pop_hidden_plans()
        assert len(plans) == 2
        # After pop, plans should be cleared
        assert world.factions["魔道"].hidden_plans == []


# ------------------------------------------------------------------ #
# WorldState                                                            #
# ------------------------------------------------------------------ #

class TestWorldState:
    def test_add_faction(self, world: WorldState):
        world.add_faction("散修联盟")
        assert "散修联盟" in world.factions

    def test_advance_timeline(self, world: WorldState):
        world.advance_timeline(1, "林风加入九天宗")
        assert len(world.timeline) == 1
        assert world.timeline[0].description == "林风加入九天宗"

    def test_sandbox_backend_returns_all_hidden_plans(self, world: WorldState):
        world.factions["九天宗"].add_hidden_plan("准备秘密行动")
        world.factions["魔道"].add_hidden_plan("布置内奸")
        backend = world.get_sandbox_backend()
        # 两个派系都有隐藏计划
        assert "九天宗" in backend
        assert "魔道" in backend
        assert len(backend["九天宗"]) == 1
        assert len(backend["魔道"]) == 1

    def test_sandbox_backend_empty_factions_omitted(self, world: WorldState):
        backend = world.get_sandbox_backend()
        # 没有 hidden_plans 的派系不应出现
        assert backend == {}

    def test_world_consistency_check_passes(self, world: WorldState):
        result = world.check_world_consistency("林风在九天宗修炼")
        assert result.consistent

    def test_world_consistency_check_fails_on_rule_violation(self, world: WorldState):
        result = world.check_world_consistency("修士故意伤害凡人村民")
        assert not result.consistent
        assert len(result.violations) > 0

    def test_snapshot_rollback(self, world: WorldState):
        world.advance_timeline(1, "大战爆发")
        world.snapshot(chapter=1)

        world.advance_timeline(2, "宗门覆灭")
        assert len(world.timeline) == 2

        world.rollback_to_chapter(1)
        assert len(world.timeline) == 1

    def test_rollback_missing_chapter_raises(self, world: WorldState):
        with pytest.raises(KeyError):
            world.rollback_to_chapter(999)


# ------------------------------------------------------------------ #
# Additional API coverage                                               #
# ------------------------------------------------------------------ #

class TestWorldStateAdditional:
    def test_update_faction(self, world: WorldState):
        world.update_faction("九天宗", description="古老宗门")
        assert world.factions["九天宗"].description == "古老宗门"

    def test_update_faction_missing_raises(self, world: WorldState):
        with pytest.raises(KeyError):
            world.update_faction("不存在的门派", description="x")

    def test_advance_timeline_object_form(self, world: WorldState):
        from narrative_os.core.world import TimelineEvent
        te = TimelineEvent(id="ev1", chapter=2, description="大战开始")
        result = world.advance_timeline(te)
        assert result.id == "ev1"
        assert world.current_chapter == 2

    def test_add_world_rule(self, world: WorldState):
        world.add_world_rule("不得勾连外族")
        assert "不得勾结外族" in world.rules_of_world or "不得勾连外族" in world.rules_of_world

    def test_add_world_rule_no_duplicate(self, world: WorldState):
        n_before = len(world.rules_of_world)
        world.add_world_rule("修士不得伤害凡人")  # already exists
        assert len(world.rules_of_world) == n_before

    def test_execute_sandbox_plans(self, world: WorldState):
        world.factions["魔道"].add_hidden_plan("渗透内部")
        plans = world.execute_sandbox_plans("魔道")
        assert "渗透内部" in plans
        assert world.factions["魔道"].hidden_plans == []

    def test_execute_sandbox_plans_unknown_faction(self, world: WorldState):
        result = world.execute_sandbox_plans("不存在")
        assert result == []

    def test_to_json_roundtrip(self, world: WorldState, tmp_path):
        j = world.to_json()
        assert "九天宗" in j
        loaded = WorldState.from_json(tmp_path / "world.json") if False else None
        # At minimum, to_json returns valid JSON string
        import json
        data = json.loads(j)
        assert "factions" in data

    def test_to_json_writes_file(self, world: WorldState, tmp_path):
        p = tmp_path / "world.json"
        world.to_json(path=p)
        assert p.exists()

    def test_from_json_roundtrip(self, world: WorldState, tmp_path):
        p = tmp_path / "world.json"
        world.to_json(path=p)
        w2 = WorldState.from_json(p)
        assert "九天宗" in w2.factions

    def test_to_dict(self, world: WorldState):
        d = world.to_dict()
        assert isinstance(d, dict)
        assert "factions" in d

    def test_repr(self, world: WorldState):
        r = repr(world)
        assert "WorldState" in r
