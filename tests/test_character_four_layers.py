"""
tests/test_character_four_layers.py — Phase 2 自查测试套件

覆盖：
  2.A  四层模型序列化/反序列化（旧格式能无损升级读取）
  2.B  RelationshipProfile 多维字段范围校验、认知标签增删
  2.C  CharacterRepository 读取/保存/合并 memory 逻辑
  2.D  Gate3 升级后 CharacterSnapshot 包含 drive 摘要和关系矩阵片段
  2.E  （回归）现有 CharacterState API 无 regression
  2.F  API 端点：drive / runtime / social-matrix 正常响应
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from narrative_os.core.character import (
    CharacterDrive,
    CharacterRuntime,
    CharacterState,
    RelationshipProfile,
)
from narrative_os.core.character_repository import CharacterRepository
from narrative_os.execution.context_builder import (
    ChapterTarget,
    ContextBuilder,
    CharacterSnapshot,
)
from narrative_os.interface.api import app


# ------------------------------------------------------------------ #
# 2.A 四层模型序列化/反序列化                                           #
# ------------------------------------------------------------------ #

class TestFourLayerSerialization:
    """旧格式角色能无损升级读取（向后兼容）。"""

    def test_old_format_loads_without_error(self):
        """不含四层字段的旧 dict 能正常 validate 为 CharacterState。"""
        old = {
            "name": "旧角色",
            "traits": ["勇敢"],
            "goal": "复仇",
            "emotion": "愤怒",
            "relationships": {"敌人甲": -0.8},
            "arc_stage": "防御",
        }
        char = CharacterState.model_validate(old)
        assert char.name == "旧角色"
        assert char.drive is None
        assert char.social_matrix == {}
        assert char.runtime.current_location == ""
        assert char.worldview == ""
        assert char.character_tags == []

    def test_new_format_roundtrip(self):
        """四层完整模型序列化 → 反序列化无损。"""
        char = CharacterState(
            name="新角色",
            drive=CharacterDrive(core_desire="变强", core_fear="孤独", long_term_goal="统一"),
            social_matrix={
                "友军": RelationshipProfile(target_name="友军", affinity=0.9, trust=0.8)
            },
            runtime=CharacterRuntime(current_location="城墙", current_agenda="防御"),
            worldview="强者为尊",
            character_tags=["主角", "修炼者"],
        )
        raw = char.model_dump_json()
        loaded = CharacterState.model_validate_json(raw)
        assert loaded.drive is not None
        assert loaded.drive.core_desire == "变强"
        assert "友军" in loaded.social_matrix
        assert loaded.social_matrix["友军"].trust == 0.8
        assert loaded.runtime.current_location == "城墙"
        assert loaded.worldview == "强者为尊"
        assert "修炼者" in loaded.character_tags

    def test_partial_four_layers_loads(self):
        """仅含 drive 字段的 dict 也能正确读取，social_matrix 和 runtime 使用默认值。"""
        data = {
            "name": "哑女",
            "drive": {"core_desire": "找回声音", "core_fear": "永远沉默"},
        }
        char = CharacterState.model_validate(data)
        assert char.drive is not None
        assert char.drive.core_desire == "找回声音"
        assert char.social_matrix == {}
        assert char.runtime.can_advance_plot is True


# ------------------------------------------------------------------ #
# 2.B RelationshipProfile 字段范围校验                                  #
# ------------------------------------------------------------------ #

class TestRelationshipProfile:
    """多维字段范围校验、认知标签增删。"""

    def test_affinity_range(self):
        p = RelationshipProfile(target_name="A", affinity=0.5)
        assert -1.0 <= p.affinity <= 1.0

    def test_affinity_out_of_range_raises(self):
        with pytest.raises(ValidationError):
            RelationshipProfile(target_name="A", affinity=2.0)

    def test_trust_out_of_range_raises(self):
        with pytest.raises(ValidationError):
            RelationshipProfile(target_name="A", trust=-0.1)

    def test_debt_sense_negative(self):
        """debt_sense 可以是负值（表示对方欠我）。"""
        p = RelationshipProfile(target_name="B", debt_sense=-0.7)
        assert p.debt_sense == pytest.approx(-0.7)

    def test_cognitive_tags_add_remove(self):
        p = RelationshipProfile(target_name="C", cognitive_tags=["可利用"])
        p.cognitive_tags.append("值得追随")
        assert "值得追随" in p.cognitive_tags
        p.cognitive_tags.remove("可利用")
        assert "可利用" not in p.cognitive_tags

    def test_default_values(self):
        p = RelationshipProfile(target_name="D")
        assert p.affinity == 0.0
        assert p.trust == 0.5
        assert p.cognitive_tags == []
        assert p.notes == ""

    def test_all_fields_valid(self):
        p = RelationshipProfile(
            target_name="E",
            affinity=-0.3, trust=0.6, dependency=0.4,
            fear=0.8, jealousy=0.2, control_desire=0.5,
            debt_sense=0.1, cognitive_tags=["危险"], notes="小心此人",
        )
        assert p.fear == pytest.approx(0.8)
        assert p.notes == "小心此人"


# ------------------------------------------------------------------ #
# 2.C CharacterRepository 读取/保存                                     #
# ------------------------------------------------------------------ #

class TestCharacterRepository:
    """读取/保存/合并 memory 逻辑正确。"""

    def _make_repo(self, tmp_path: Path) -> CharacterRepository:
        repo = CharacterRepository.__new__(CharacterRepository)
        repo._state_root = tmp_path
        return repo

    def test_list_empty_project(self, tmp_path):
        repo = self._make_repo(tmp_path)
        assert repo.list_characters("proj1") == []

    def test_save_and_get(self, tmp_path):
        repo = self._make_repo(tmp_path)
        char = CharacterState(
            name="李白",
            drive=CharacterDrive(core_desire="天下第一", core_fear="平庸"),
        )
        repo.save_character("proj1", char)
        loaded = repo.get_character("proj1", "李白")
        assert loaded is not None
        assert loaded.name == "李白"
        assert loaded.drive is not None
        assert loaded.drive.core_desire == "天下第一"

    def test_update_existing(self, tmp_path):
        repo = self._make_repo(tmp_path)
        char = CharacterState(name="杜甫", goal="忧国忧民")
        repo.save_character("proj1", char)
        char.goal = "致君尧舜上"
        repo.save_character("proj1", char)
        loaded = repo.get_character("proj1", "杜甫")
        assert loaded is not None
        assert loaded.goal == "致君尧舜上"

    def test_get_nonexistent_returns_none(self, tmp_path):
        repo = self._make_repo(tmp_path)
        assert repo.get_character("proj1", "不存在") is None

    def test_list_multiple(self, tmp_path):
        repo = self._make_repo(tmp_path)
        for name in ["甲", "乙", "丙"]:
            repo.save_character("proj1", CharacterState(name=name))
        chars = repo.list_characters("proj1")
        assert len(chars) == 3
        assert {c.name for c in chars} == {"甲", "乙", "丙"}

    def test_save_with_social_matrix(self, tmp_path):
        repo = self._make_repo(tmp_path)
        char = CharacterState(
            name="主角",
            social_matrix={
                "伙伴": RelationshipProfile(target_name="伙伴", affinity=0.8, trust=0.9)
            },
        )
        repo.save_character("proj1", char)
        loaded = repo.get_character("proj1", "主角")
        assert loaded is not None
        assert "伙伴" in loaded.social_matrix
        assert loaded.social_matrix["伙伴"].affinity == pytest.approx(0.8)

    def test_save_with_runtime(self, tmp_path):
        repo = self._make_repo(tmp_path)
        char = CharacterState(
            name="NPC",
            runtime=CharacterRuntime(current_location="酒馆", current_pressure=0.6),
        )
        repo.save_character("proj1", char)
        loaded = repo.get_character("proj1", "NPC")
        assert loaded is not None
        assert loaded.runtime.current_location == "酒馆"
        assert loaded.runtime.current_pressure == pytest.approx(0.6)


# ------------------------------------------------------------------ #
# 2.D Gate3 升级：CharacterSnapshot 包含 drive 摘要和关系矩阵片段        #
# ------------------------------------------------------------------ #

class TestGate3Upgrade:
    """修改 Gate3 后，CharacterSnapshot 包含角色动机信息。"""

    def _build_char(self, name: str = "主角") -> CharacterState:
        return CharacterState(
            name=name,
            emotion="平静",
            goal="闯荡江湖",
            arc_stage="防御",
            drive=CharacterDrive(
                core_desire="自由", core_fear="囚禁", current_obsession="寻找师父"
            ),
            social_matrix={
                "副角": RelationshipProfile(target_name="副角", affinity=0.7, trust=0.9, fear=0.1)
            },
            relationships={"副角": 0.7},
        )

    def test_snapshot_has_top_drives(self):
        cb = ContextBuilder()
        char = self._build_char()
        companion = CharacterState(name="副角", emotion="平静", goal="辅佐主角")
        snaps = cb._gate3_characters([char, companion])
        main_snap = next(s for s in snaps if s.name == "主角")
        assert isinstance(main_snap, CharacterSnapshot)
        assert len(main_snap.top_drives) > 0
        assert any("自由" in d or "囚禁" in d or "寻找" in d for d in main_snap.top_drives)

    def test_snapshot_has_key_relationships(self):
        cb = ContextBuilder()
        char = self._build_char()
        companion = CharacterState(name="副角", emotion="平静", goal="辅佐主角")
        snaps = cb._gate3_characters([char, companion])
        main_snap = next(s for s in snaps if s.name == "主角")
        assert len(main_snap.key_relationships) > 0
        rel = main_snap.key_relationships[0]
        assert rel["target"] == "副角"
        assert "affinity" in rel

    def test_snapshot_without_drive(self):
        """没有 drive 字段的旧格式角色，top_drives 为空列表。"""
        cb = ContextBuilder()
        char = CharacterState(name="旧格式角色", emotion="平静", goal="无目标")
        snaps = cb._gate3_characters([char])
        assert snaps[0].top_drives == []
        assert snaps[0].key_relationships == []

    def test_snapshot_relationships_intersect_scene(self):
        """key_relationships 只包含本次出场角色的关系。"""
        cb = ContextBuilder()
        char = CharacterState(
            name="主角",
            social_matrix={
                "A": RelationshipProfile(target_name="A", affinity=0.5),
                "B": RelationshipProfile(target_name="B", affinity=-0.5),
            },
        )
        # 此场景只有 A，没有 B
        scene_char = CharacterState(name="A", emotion="平静", goal="")
        snaps = cb._gate3_characters([char, scene_char])
        main_snap = next(s for s in snaps if s.name == "主角")
        targets = [r["target"] for r in main_snap.key_relationships]
        assert "A" in targets
        assert "B" not in targets

    def test_system_prompt_includes_drives(self):
        """to_system_prompt 输出含角色驱动。"""
        from narrative_os.execution.context_builder import WriteContext
        cb = ContextBuilder()
        char = self._build_char()
        ct = ChapterTarget(chapter=1, target_summary="测试章节")
        ctx = WriteContext(chapter_target=ct)
        ctx.characters = cb._gate3_characters([char])
        prompt = ctx.to_system_prompt()
        assert "驱动" in prompt or "自由" in prompt or "囚禁" in prompt


# ------------------------------------------------------------------ #
# 2.E 回归：CharacterState 现有接口无 regression                        #
# ------------------------------------------------------------------ #

class TestCharacterStateRegression:
    """确保新增四层字段不影响现有方法。"""

    def test_check_constraints(self):
        char = CharacterState(
            name="剑客",
            behavior_constraints=[
                {"rule": "不能主动认输", "severity": "hard"},
            ],
        )
        result = char.check_constraints("选择放弃，不认输")
        assert result is not None

    def test_snapshot_still_works(self):
        char = CharacterState(name="老角色", drive=CharacterDrive(core_desire="逃脱"))
        snap = char.snapshot(chapter=3)
        assert snap["chapter"] == 3

    def test_rollback_still_works(self):
        char = CharacterState(name="可回滚角色", emotion="愤怒", health=1.0)
        char.snapshot(chapter=1)
        char.update_emotion("悲伤")
        char.rollback_to_chapter(chapter=1)
        assert char.emotion == "愤怒"

    def test_update_relationship_syncs_social_matrix(self):
        """update_relationship 同时更新 social_matrix.affinity。"""
        char = CharacterState(
            name="主角",
            relationships={"对手": 0.0},
            social_matrix={"对手": RelationshipProfile(target_name="对手", affinity=0.0)},
        )
        char.update_relationship("对手", -0.5)
        assert char.relationships["对手"] == pytest.approx(-0.5)
        assert char.social_matrix["对手"].affinity == pytest.approx(-0.5)

    def test_get_relationship_fallback(self):
        """get_relationship 在 social_matrix 无记录时使用 relationships 兼容值。"""
        char = CharacterState(name="A", relationships={"B": 0.6})
        profile = char.get_relationship("B")
        assert profile.affinity == pytest.approx(0.6)

    def test_get_relationship_uses_social_matrix_first(self):
        """social_matrix 中有记录时优先返回多维数据。"""
        char = CharacterState(
            name="A",
            relationships={"B": 0.3},
            social_matrix={"B": RelationshipProfile(target_name="B", affinity=0.8, trust=0.9)},
        )
        profile = char.get_relationship("B")
        assert profile.trust == pytest.approx(0.9)
        assert profile.affinity == pytest.approx(0.8)


# ------------------------------------------------------------------ #
# 2.F API 端点测试                                                      #
# ------------------------------------------------------------------ #

client_app = TestClient(app)


class TestCharacterFourLayerAPI:
    """新增 drive/runtime/social-matrix 端点正常响应。"""

    def _create_project_with_char(self, project_id: str, char_name: str, tmp_path: Path) -> None:
        """直接写入 KB 建立测试角色。"""
        kb_dir = tmp_path / project_id
        kb_dir.mkdir(parents=True, exist_ok=True)
        char_data = {
            "name": char_name,
            "emotion": "平静",
            "health": 1.0,
            "arc_stage": "防御",
            "is_alive": True,
            "relationships": {},
            "behavior_constraints": [],
            "voice_fingerprint": {},
            "memory": [],
            "snapshot_history": [],
            "traits": [],
            "goal": "",
            "backstory": "",
            "drive": None,
            "social_matrix": {},
            "runtime": {"current_location": "", "current_pressure": 0.0, "can_advance_plot": True, "stance_mode": "normal", "current_companions": [], "current_agenda": "", "emotion_trigger_source": "", "recent_key_events": []},
        }
        kb = {"characters": [char_data]}
        (kb_dir / "knowledge_base.json").write_text(
            json.dumps(kb, ensure_ascii=False), encoding="utf-8"
        )

    def test_get_drive_no_drive(self, tmp_path, monkeypatch):
        """角色没有 drive 时返回空对象。"""
        from narrative_os.core import character_repository as cr_mod
        repo = CharacterRepository.__new__(CharacterRepository)
        repo._state_root = tmp_path
        monkeypatch.setattr(cr_mod, "_repo", repo)
        self._create_project_with_char("p1", "角色甲", tmp_path)
        resp = client_app.get("/projects/p1/characters/%E8%A7%92%E8%89%B2%E7%94%B2/drive")
        assert resp.status_code == 200
        assert resp.json() == {}

    def test_put_drive(self, tmp_path, monkeypatch):
        """PUT drive 端点能正常保存。"""
        from narrative_os.core import character_repository as cr_mod
        repo = CharacterRepository.__new__(CharacterRepository)
        repo._state_root = tmp_path
        monkeypatch.setattr(cr_mod, "_repo", repo)
        self._create_project_with_char("p2", "角色乙", tmp_path)
        payload = {"core_desire": "称霸", "core_fear": "被遗忘"}
        resp = client_app.put("/projects/p2/characters/%E8%A7%92%E8%89%B2%E4%B9%99/drive", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["core_desire"] == "称霸"
        assert data["core_fear"] == "被遗忘"

    def test_put_runtime(self, tmp_path, monkeypatch):
        """PUT runtime 端点能正常更新状态。"""
        from narrative_os.core import character_repository as cr_mod
        repo = CharacterRepository.__new__(CharacterRepository)
        repo._state_root = tmp_path
        monkeypatch.setattr(cr_mod, "_repo", repo)
        self._create_project_with_char("p3", "角色丙", tmp_path)
        payload = {"current_location": "禁地", "current_pressure": 0.7}
        resp = client_app.put("/projects/p3/characters/%E8%A7%92%E8%89%B2%E4%B8%99/runtime", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["current_location"] == "禁地"
        assert abs(data["current_pressure"] - 0.7) < 0.01

    def test_get_social_matrix_empty(self, tmp_path, monkeypatch):
        """无 social_matrix 时返回空字典。"""
        from narrative_os.core import character_repository as cr_mod
        repo = CharacterRepository.__new__(CharacterRepository)
        repo._state_root = tmp_path
        monkeypatch.setattr(cr_mod, "_repo", repo)
        self._create_project_with_char("p4", "角色丁", tmp_path)
        resp = client_app.get("/projects/p4/characters/%E8%A7%92%E8%89%B2%E4%B8%81/social-matrix")
        assert resp.status_code == 200
        assert resp.json() == {}

    def test_put_social_matrix(self, tmp_path, monkeypatch):
        """PUT social-matrix 端点能保存多维关系。"""
        from narrative_os.core import character_repository as cr_mod
        repo = CharacterRepository.__new__(CharacterRepository)
        repo._state_root = tmp_path
        monkeypatch.setattr(cr_mod, "_repo", repo)
        self._create_project_with_char("p5", "角色戊", tmp_path)
        payload = {
            "对手": {
                "target_name": "对手",
                "affinity": -0.8,
                "trust": 0.1,
                "dependency": 0.0,
                "fear": 0.9,
                "jealousy": 0.3,
                "control_desire": 0.0,
                "debt_sense": 0.0,
                "cognitive_tags": ["不能惹"],
            }
        }
        resp = client_app.put("/projects/p5/characters/%E8%A7%92%E8%89%B2%E6%88%8A/social-matrix", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert "对手" in data
        assert abs(data["对手"]["fear"] - 0.9) < 0.01
        assert "不能惹" in data["对手"]["cognitive_tags"]

    def test_drive_404_for_unknown_character(self, tmp_path, monkeypatch):
        """未知角色返回 404。"""
        from narrative_os.core import character_repository as cr_mod
        repo = CharacterRepository.__new__(CharacterRepository)
        repo._state_root = tmp_path
        monkeypatch.setattr(cr_mod, "_repo", repo)
        resp = client_app.get("/projects/px/characters/%E4%B8%8D%E5%AD%98%E5%9C%A8/drive")
        assert resp.status_code == 404
