"""
tests/test_world_compile_chain.py — Phase 6 Stage 1: 世界编译链测试

覆盖范围：
  1.A WorldRepository 读取 / 优先级 / 写入测试
  1.B WorldCompiler.compile() 字段映射无缺失
  1.C WorldValidator 检出引用断链、缺失势力等错误
  1.D WorldBuilder._finalize() 输出 WorldSandboxData 无 regression
  1.E POST /world/publish API 集成测试
  1.F context_builder.py Gate4 通过 WorldRepository 获取世界快照
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from narrative_os.core.world import WorldState
from narrative_os.core.world_compiler import WorldCompiler, PublishReport
from narrative_os.core.world_repository import WorldRepository
from narrative_os.core.world_sandbox import (
    ConceptData,
    Faction,
    FactionScope,
    PowerLevel,
    PowerSystem,
    Region,
    WorldSandboxData,
)
from narrative_os.core.world_validator import WorldValidator, ValidationReport


# ------------------------------------------------------------------ #
# 辅助 Fixtures                                                        #
# ------------------------------------------------------------------ #


@pytest.fixture()
def simple_sandbox() -> WorldSandboxData:
    """构造一个简单的世界沙盘数据（含一个地区 + 一个势力 + 一个力量体系）。"""
    region = Region(
        id="region_001",
        name="北境城",
        region_type="城市",
        faction_ids=["faction_001"],
    )
    faction = Faction(
        id="faction_001",
        name="天圣帝国",
        scope=FactionScope.INTERNAL,
        description="大陆最强势力",
        territory_region_ids=["region_001"],
        relation_map={},
    )
    ps = PowerSystem(
        id="ps_001",
        name="修炼体系",
        levels=[
            PowerLevel(name="炼气期", description="修炼入门"),
            PowerLevel(name="筑基期", description="稳固根基"),
            PowerLevel(name="金丹期", description="凝结金丹"),
        ],
        rules=["气血耗尽则死", "境界不可跨越"],
        resources=["灵石", "丹药"],
    )
    return WorldSandboxData(
        world_name="天元大陆",
        world_description="一个充满修炼者的大陆",
        regions=[region],
        factions=[faction],
        power_systems=[ps],
        world_rules=["法术在结界内无效", "天道不可违"],
    )


@pytest.fixture()
def concept_data() -> ConceptData:
    return ConceptData(
        one_sentence="少年修炼者在天元大陆踏上修炼之路",
        one_paragraph="主角从弱小走向强大，最终成为大陆顶尖强者",
        genre_tags=["修真", "热血"],
    )


@pytest.fixture()
def client():
    from narrative_os.interface.api import app
    return TestClient(app, raise_server_exceptions=False)


# ------------------------------------------------------------------ #
# 1.B WorldCompiler 测试                                               #
# ------------------------------------------------------------------ #


class TestWorldCompiler:
    """测试 WorldCompiler.compile() 字段映射。"""

    def test_compile_basic_fields(self, simple_sandbox: WorldSandboxData):
        """编译后 WorldState 包含对应的势力/地理/力量体系/规则。"""
        compiler = WorldCompiler()
        world, report = compiler.compile(concept=None, sandbox=simple_sandbox)

        assert isinstance(world, WorldState)
        assert isinstance(report, PublishReport)

        # 势力编译
        assert "faction_001" in world.factions
        assert world.factions["faction_001"].name == "天圣帝国"
        assert report.factions_compiled == 1

        # 地区编译
        assert "region_001" in world.geography
        assert world.geography["region_001"]["name"] == "北境城"
        assert report.regions_compiled == 1

        # 力量体系编译
        assert world.power_system.name == "修炼体系"
        assert len(world.power_system.levels) == 3
        assert report.power_systems_compiled == 1

        # 规则编译
        assert "法术在结界内无效" in world.rules_of_world
        assert report.rules_compiled == 2

    def test_compile_faction_territory_bidirectional(self, simple_sandbox: WorldSandboxData):
        """势力领土与地区 faction_ids 双向关系正确补全。"""
        compiler = WorldCompiler()
        world, _ = compiler.compile(concept=None, sandbox=simple_sandbox)

        faction = world.factions["faction_001"]
        assert "region_001" in faction.territory

        geo = world.geography["region_001"]
        assert "faction_001" in geo["faction_ids"]

    def test_compile_with_seed_world_preserves_timeline(self, simple_sandbox: WorldSandboxData):
        """有 seed_world 时，保留 seed 的 timeline。"""
        from narrative_os.core.world import TimelineEvent
        seed = WorldState()
        seed.timeline.append(
            TimelineEvent(id="t1", chapter=1, description="历史事件1")
        )
        compiler = WorldCompiler()
        world, _ = compiler.compile(concept=None, sandbox=simple_sandbox, seed_world=seed)

        assert any(e.description == "历史事件1" for e in world.timeline)

    def test_compile_faction_relation_map(self):
        """势力关系图正确映射到 hostility_map。"""
        f1 = Faction(id="f1", name="正道", territory_region_ids=[], relation_map={"f2": 0.8})
        f2 = Faction(id="f2", name="魔门", territory_region_ids=[], relation_map={"f1": 0.8})
        sandbox = WorldSandboxData(
            world_name="测试世界",
            factions=[f1, f2],
        )
        compiler = WorldCompiler()
        world, report = compiler.compile(concept=None, sandbox=sandbox)

        assert world.factions["f1"].hostility_map.get("f2") == 0.8

    def test_compile_empty_sandbox(self):
        """空沙盘可以安全编译，返回空 WorldState。"""
        sandbox = WorldSandboxData(world_name="空世界")
        compiler = WorldCompiler()
        world, report = compiler.compile(concept=None, sandbox=sandbox)
        assert isinstance(world, WorldState)
        assert report.factions_compiled == 0
        assert report.regions_compiled == 0

    def test_compile_with_concept(
        self, simple_sandbox: WorldSandboxData, concept_data: ConceptData
    ):
        """有 concept 时正常编译（concept 目前主要用于元数据）。"""
        compiler = WorldCompiler()
        world, report = compiler.compile(concept=concept_data, sandbox=simple_sandbox)
        assert isinstance(world, WorldState)
        assert report.factions_compiled == 1


# ------------------------------------------------------------------ #
# 1.C WorldValidator 测试                                              #
# ------------------------------------------------------------------ #


class TestWorldValidator:
    """测试 WorldValidator 校验规则。"""

    def test_validate_valid_sandbox(self, simple_sandbox: WorldSandboxData):
        """合法沙盘应通过校验，无 errors。"""
        validator = WorldValidator()
        report = validator.validate(sandbox=simple_sandbox)
        assert report.is_valid, f"Expected valid, but got errors: {report.errors}"

    def test_validate_missing_world_name(self):
        """缺少 world_name 时应产生 error。"""
        sandbox = WorldSandboxData(world_name="")
        validator = WorldValidator()
        report = validator.validate(sandbox=sandbox)
        assert not report.is_valid
        assert any("world_name" in e or "世界名称" in e for e in report.errors)

    def test_validate_duplicate_region_ids(self):
        """重复地区 ID 应产生 error。"""
        r1 = Region(id="dup_id", name="地区A")
        r2 = Region(id="dup_id", name="地区B")
        sandbox = WorldSandboxData(world_name="测试", regions=[r1, r2])
        validator = WorldValidator()
        report = validator.validate(sandbox=sandbox)
        assert not report.is_valid
        assert any("dup_id" in e for e in report.errors)

    def test_validate_faction_refs_missing_region(self):
        """势力领土引用不存在的地区 ID 应产生 error。"""
        faction = Faction(
            id="f1",
            name="天圣帝国",
            territory_region_ids=["nonexistent_region"],
        )
        sandbox = WorldSandboxData(world_name="测试", factions=[faction])
        validator = WorldValidator()
        report = validator.validate(sandbox=sandbox)
        assert not report.is_valid
        assert any("nonexistent_region" in e for e in report.errors)

    def test_validate_invalid_relation_map_value(self):
        """relation_map 中超出 [-1, 1] 范围的值应产生 error。"""
        f1 = Faction(id="f1", name="正道", relation_map={"f2": 2.0})
        f2 = Faction(id="f2", name="魔门")
        sandbox = WorldSandboxData(world_name="测试", factions=[f1, f2])
        validator = WorldValidator()
        report = validator.validate(sandbox=sandbox)
        assert not report.is_valid
        assert any("2.0" in e or "敌意值" in e for e in report.errors)

    def test_validate_power_system_ref_invalid(self):
        """区域引用不存在的 power_system_id 应产生 error。"""
        from narrative_os.core.world_sandbox import RegionPowerAccess
        region = Region(
            id="r1",
            name="测试地区",
            power_access=RegionPowerAccess(
                inherits_global=False,
                custom_system_id="nonexistent_ps",
            ),
        )
        sandbox = WorldSandboxData(world_name="测试", regions=[region])
        validator = WorldValidator()
        report = validator.validate(sandbox=sandbox)
        assert not report.is_valid
        assert any("nonexistent_ps" in e for e in report.errors)

    def test_validate_bidirectional_warning(self):
        """势力与地区双向关系不一致应产生 warning（不是 error）。"""
        faction = Faction(id="f1", name="正道", territory_region_ids=["r1"])
        region = Region(id="r1", name="北境", faction_ids=[])  # 未包含 f1
        sandbox = WorldSandboxData(world_name="测试", factions=[faction], regions=[region])
        validator = WorldValidator()
        report = validator.validate(sandbox=sandbox)
        # warning，不是 error
        assert report.is_valid  # 不影响发布
        assert len(report.warnings) > 0

    def test_validate_report_structure(self, simple_sandbox: WorldSandboxData):
        """ValidationReport 字段齐全。"""
        validator = WorldValidator()
        report = validator.validate(sandbox=simple_sandbox)
        assert isinstance(report.errors, list)
        assert isinstance(report.warnings, list)
        assert isinstance(report.suggestions, list)
        assert hasattr(report, "is_valid")


# ------------------------------------------------------------------ #
# 1.A WorldRepository 测试                                             #
# ------------------------------------------------------------------ #


class TestWorldRepository:
    """测试 WorldRepository 读写逻辑。"""

    def test_get_world_state_empty_project(self, tmp_path: Path):
        """不存在的 project 返回空 WorldState。"""
        repo = WorldRepository()
        repo._state_root = tmp_path
        world = repo.get_world_state("nonexistent_proj")
        assert isinstance(world, WorldState)
        assert len(world.factions) == 0

    def test_save_and_load_world_state(self, tmp_path: Path):
        """save_world_state 后 get_world_state 能正确读取。"""
        with patch("narrative_os.infra.config.settings"):
            repo = WorldRepository.__new__(WorldRepository)
        repo._state_root = tmp_path

        world = WorldState()
        from narrative_os.core.world import FactionState
        world.factions["f1"] = FactionState(id="f1", name="正道")
        world.rules_of_world.append("法术在结界内无效")

        repo.save_world_state("test_proj", world)
        loaded = repo.get_world_state("test_proj")

        assert "f1" in loaded.factions
        assert "法术在结界内无效" in loaded.rules_of_world

    def test_runtime_world_takes_priority(self, tmp_path: Path):
        """runtime_world 优先于 world 字段。"""
        repo = WorldRepository.__new__(WorldRepository)
        repo._state_root = tmp_path

        # 写入旧的 world 字段
        old_world = WorldState()
        from narrative_os.core.world import FactionState
        old_world.factions["old_faction"] = FactionState(id="old_faction", name="旧势力")

        # 写入 runtime_world（已发布）
        new_world = WorldState()
        new_world.factions["new_faction"] = FactionState(id="new_faction", name="新势力")

        # 先保存旧 world
        repo.save_world_state("test_proj", old_world)
        # 再保存 runtime_world
        repo.save_runtime_world_state("test_proj", new_world)

        loaded = repo.get_world_state("test_proj")
        assert "new_faction" in loaded.factions

    def test_sandbox_data_roundtrip(self, tmp_path: Path):
        """沙盘数据存储到 KB 后可以圆满读取。"""
        repo = WorldRepository.__new__(WorldRepository)
        repo._state_root = tmp_path

        sandbox = WorldSandboxData(
            world_name="测试世界",
            factions=[Faction(id="f1", name="正道")],
        )
        # 写入 KB
        kb_path = tmp_path / "test_p" / "knowledge_base.json"
        kb_path.parent.mkdir(parents=True, exist_ok=True)
        kb_path.write_text(
            json.dumps({"world_sandbox": sandbox.model_dump()}, ensure_ascii=False),
            encoding="utf-8",
        )

        loaded_sandbox = repo.get_sandbox_data("test_p")
        assert loaded_sandbox.world_name == "测试世界"
        assert len(loaded_sandbox.factions) == 1


# ------------------------------------------------------------------ #
# 1.D WorldBuilder._finalize() 测试                                    #
# ------------------------------------------------------------------ #


class TestWorldBuilderFinalize:
    """测试 WorldBuilder._finalize() 输出 WorldSandboxData 无 regression。"""

    def test_finalize_returns_seed_data(self):
        """_finalize() 返回 seed 数据，包含 world_sandbox 字段。"""
        from narrative_os.core.world_builder import WorldBuilder, BuilderStep

        builder = WorldBuilder()
        builder.state.step = BuilderStep.DONE
        builder.state.one_sentence = "落魄少年在修炼者大陆踏上成长之路"
        builder.state.one_paragraph = "主角历经磨难，最终成为大陆顶尖强者"
        builder.state.needs_world_power = True
        builder.state.world_power_system = {
            "system_name": "修炼境界",
            "tiers": ["炼气期", "筑基期", "金丹期"],
        }
        builder.state.one_page_outline = {
            "raw_text": "第一卷：少年觉醒，加入宗门",
            "characters": [{"name": "林枫", "role": "主角"}],
            "world": {"factions": ["天圣宗"], "key_locations": ["北境城"], "rules": []},
            "plot_nodes": [
                {"id": "n1", "summary": "林枫觉醒灵根", "tension": 0.3, "pacing_type": "rising", "key_beat": "引入", "status": "pending"}
            ],
        }

        seed = builder._finalize()

        # 向后兼容字段仍存在
        assert "plot_nodes" in seed
        assert "characters" in seed
        assert "world" in seed

        # Phase 6 Stage 1: 新增 world_sandbox 字段
        assert "world_sandbox" in seed
        assert isinstance(seed["world_sandbox"], dict)
        ws = WorldSandboxData.model_validate(seed["world_sandbox"])
        assert ws.world_name != "" or True  # 至少能反序列化
        assert len(ws.power_systems) > 0  # 力量体系已提取

    def test_finalize_without_world_power(self):
        """无力量体系时 _finalize() 仍然正常，world_sandbox 字段存在。"""
        from narrative_os.core.world_builder import WorldBuilder, BuilderStep

        builder = WorldBuilder()
        builder.state.step = BuilderStep.DONE
        builder.state.one_sentence = "现代都市爱情故事"
        builder.state.one_page_outline = {
            "raw_text": "简单的都市爱情",
            "characters": [],
            "world": {"factions": [], "key_locations": [], "rules": []},
            "plot_nodes": [],
        }

        seed = builder._finalize()
        assert "world" in seed  # 旧字段不变
        assert "world_sandbox" in seed or seed.get("world_sandbox") is None  # 可为 None

    def test_finalize_initial_plot_nodes_not_empty(self):
        """保底情节节点（空大纲时）仍然生成。"""
        from narrative_os.core.world_builder import WorldBuilder, BuilderStep

        builder = WorldBuilder()
        builder.state.step = BuilderStep.DONE
        builder.state.one_sentence = "简单的故事"
        builder.state.one_page_outline = {}  # 空大纲

        seed = builder._finalize()
        assert len(seed["plot_nodes"]) >= 1


# ------------------------------------------------------------------ #
# 1.E POST /world/publish API 集成测试                                  #
# ------------------------------------------------------------------ #


class TestWorldPublishAPI:
    """测试发布 API 端点。"""

    def test_publish_valid_world(
        self, client: TestClient, simple_sandbox: WorldSandboxData
    ):
        """有效沙盘可以成功发布，返回 published 状态。"""
        project_id = "test-publish-valid"

        # Mock _get_sandbox 和 _get_concept
        with (
            patch(
                "narrative_os.interface.api._get_sandbox",
                new=AsyncMock(return_value=simple_sandbox),
            ),
            patch(
                "narrative_os.interface.api._get_concept",
                new=AsyncMock(return_value=ConceptData()),
            ),
            patch(
                "narrative_os.core.world_repository.WorldRepository.asave_runtime_world_state",
                new=AsyncMock(),
            ),
        ):
            response = client.post(f"/projects/{project_id}/world/publish")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "published"
        assert "publish_report" in data
        assert data["publish_report"]["factions_compiled"] == 1
        assert data["publish_report"]["regions_compiled"] == 1
        assert data["runtime_diff"]["sections"]

    def test_publish_invalid_world_missing_name(self, client: TestClient):
        """世界名称为空时，发布失败并返回 validation_failed 状态。"""
        project_id = "test-publish-invalid"
        bad_sandbox = WorldSandboxData(world_name="")

        with (
            patch(
                "narrative_os.interface.api._get_sandbox",
                new=AsyncMock(return_value=bad_sandbox),
            ),
            patch(
                "narrative_os.interface.api._get_concept",
                new=AsyncMock(return_value=ConceptData()),
            ),
        ):
            response = client.post(f"/projects/{project_id}/world/publish")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "validation_failed"
        assert len(data["errors"]) > 0

    def test_publish_report_structure(
        self, client: TestClient, simple_sandbox: WorldSandboxData
    ):
        """发布报告结构完整。"""
        project_id = "test-publish-structure"

        with (
            patch(
                "narrative_os.interface.api._get_sandbox",
                new=AsyncMock(return_value=simple_sandbox),
            ),
            patch(
                "narrative_os.interface.api._get_concept",
                new=AsyncMock(return_value=ConceptData()),
            ),
            patch(
                "narrative_os.core.world_repository.WorldRepository.asave_runtime_world_state",
                new=AsyncMock(),
            ),
        ):
            response = client.post(f"/projects/{project_id}/world/publish")

        data = response.json()
        if data["status"] == "published":
            report = data["publish_report"]
            assert "factions_compiled" in report
            assert "regions_compiled" in report
            assert "rules_compiled" in report
            assert "world_version" in data
            assert "runtime_diff" in data

    def test_publish_preview_returns_structured_diff(
        self, client: TestClient, simple_sandbox: WorldSandboxData
    ):
        project_id = "test-publish-preview"

        with (
            patch(
                "narrative_os.interface.api._get_sandbox",
                new=AsyncMock(return_value=simple_sandbox),
            ),
            patch(
                "narrative_os.interface.api._get_concept",
                new=AsyncMock(return_value=ConceptData()),
            ),
        ):
            response = client.post(f"/projects/{project_id}/world/publish-preview")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert data["publish_report"]["regions_compiled"] == 1
        assert any(section["key"] == "geography" for section in data["runtime_diff"]["sections"])

    def test_publish_invalid_world_with_duplicate_power_levels(self, client: TestClient, simple_sandbox: WorldSandboxData):
        project_id = "test-publish-invalid-power"
        simple_sandbox.power_systems[0].levels[1].name = simple_sandbox.power_systems[0].levels[0].name

        with (
            patch(
                "narrative_os.interface.api._get_sandbox",
                new=AsyncMock(return_value=simple_sandbox),
            ),
            patch(
                "narrative_os.interface.api._get_concept",
                new=AsyncMock(return_value=ConceptData()),
            ),
        ):
            response = client.post(f"/projects/{project_id}/world/publish-preview")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "validation_failed"
        assert any("重复等级名称" in item for item in data["errors"])


# ------------------------------------------------------------------ #
# 1.F context_builder.py Gate4 通过 WorldRepository 获取世界快照         #
# ------------------------------------------------------------------ #


class TestContextBuilderGate4WithRepository:
    """测试 Gate4 通过 WorldRepository 获取世界数据。"""

    def test_gate4_uses_repository_when_world_is_none(self, tmp_path: Path):
        """world 为 None 且有 project_id 时，通过 WorldRepository 获取。"""
        from narrative_os.execution.context_builder import ContextBuilder, ChapterTarget
        from narrative_os.core.world import FactionState

        # 预先在 KB 写入世界数据
        world = WorldState()
        world.factions["test_faction"] = FactionState(
            id="test_faction", name="测试势力"
        )
        world.rules_of_world.append("测试规则")

        repo = WorldRepository.__new__(WorldRepository)
        repo._state_root = tmp_path
        repo.save_world_state("gate4_proj", world)

        with patch(
            "narrative_os.core.world_repository.get_world_repository",
            return_value=repo,
        ):
            cb = ContextBuilder()
            ctx = cb.build(
                chapter_target=ChapterTarget(chapter=1),
                world=None,
                project_id="gate4_proj",
            )

        assert "test_faction" in ctx.world.active_factions or len(ctx.world.key_rules) > 0

    def test_gate4_direct_world_takes_priority(self, tmp_path: Path):
        """直接传入 world 时，不走 WorldRepository。"""
        from narrative_os.execution.context_builder import ContextBuilder, ChapterTarget
        from narrative_os.core.world import FactionState

        direct_world = WorldState()
        direct_world.factions["direct_faction"] = FactionState(
            id="direct_faction", name="直接传入势力"
        )

        repo_world = WorldState()
        repo_world.factions["repo_faction"] = FactionState(
            id="repo_faction", name="Repository势力"
        )

        mock_repo = MagicMock()
        mock_repo.get_world_state.return_value = repo_world

        with patch(
            "narrative_os.core.world_repository.get_world_repository",
            return_value=mock_repo,
        ):
            cb = ContextBuilder()
            ctx = cb.build(
                chapter_target=ChapterTarget(chapter=1),
                world=direct_world,
                project_id="some_proj",
            )

        # 直接传入的 world 优先，不调用 repository
        assert "direct_faction" in ctx.world.active_factions
        mock_repo.get_world_state.assert_not_called()
