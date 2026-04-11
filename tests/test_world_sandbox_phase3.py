"""
tests/test_world_sandbox_phase3.py — 世界构建模块优化三阶段·阶段一测试

覆盖范围：
  - 关系类型扩展与标准化（RelationType 枚举 + normalize_relation_type）
  - 势力新增字段（color, x, y）序列化
  - 时间轴事件模型与 CRUD 接口
  - 世界概览接口
  - 地图布局接口
  - 旧数据兼容性
"""
from __future__ import annotations

import json
import uuid
import pytest
from fastapi.testclient import TestClient

from narrative_os.core.world_sandbox import (
    Faction,
    FactionScope,
    Region,
    RelationType,
    TimelineSandboxEvent,
    WorldRelation,
    WorldSandboxData,
    normalize_relation_type,
)
from narrative_os.interface.api import app


# ------------------------------------------------------------------ #
# 固定装置                                                              #
# ------------------------------------------------------------------ #


@pytest.fixture()
def client():
    return TestClient(app, raise_server_exceptions=False)


# 每次测试会话使用唯一前缀，避免多次运行时 DB 状态积累
_RUN_ID = uuid.uuid4().hex[:8]
PROJECT_ID = f"test-phase3-sandbox-{_RUN_ID}"


# ------------------------------------------------------------------ #
# 1. RelationType 枚举 & normalize_relation_type                       #
# ------------------------------------------------------------------ #


class TestRelationTypeEnum:
    def test_all_standard_types_exist(self):
        expected = {
            "adjacent", "border", "trade", "war", "alliance",
            "vassal", "blockade", "teleport", "connection",
        }
        actual = {t.value for t in RelationType}
        assert expected == actual

    def test_normalize_standard_values(self):
        for t in RelationType:
            assert normalize_relation_type(t.value) == t.value

    def test_normalize_legacy_chinese_types(self):
        assert normalize_relation_type("贸易") == "trade"
        assert normalize_relation_type("战争") == "war"
        assert normalize_relation_type("联盟") == "alliance"
        assert normalize_relation_type("附属") == "vassal"
        assert normalize_relation_type("封锁") == "blockade"
        assert normalize_relation_type("传送") == "teleport"
        assert normalize_relation_type("相邻") == "adjacent"
        assert normalize_relation_type("边界") == "border"
        assert normalize_relation_type("连接") == "connection"

    def test_normalize_legacy_english_aliases(self):
        assert normalize_relation_type("conflict") == "war"
        assert normalize_relation_type("trade") == "trade"

    def test_normalize_unknown_falls_back_to_connection(self):
        assert normalize_relation_type("xyz_unknown") == "connection"
        assert normalize_relation_type("") == "connection"

    def test_normalize_case_insensitive(self):
        assert normalize_relation_type("TRADE") == "trade"
        assert normalize_relation_type("Alliance") == "alliance"
        assert normalize_relation_type("WAR") == "war"


# ------------------------------------------------------------------ #
# 2. 模型序列化：新增字段                                                #
# ------------------------------------------------------------------ #


class TestModelSerialization:
    def test_faction_color_field_optional(self):
        f = Faction(name="测试势力")
        d = f.model_dump()
        assert d["color"] is None
        assert d["x"] == 0.0
        assert d["y"] == 0.0

    def test_faction_color_field_with_value(self):
        f = Faction(name="蓝阵营", color="#3b82f6", x=100.0, y=200.0)
        d = f.model_dump()
        assert d["color"] == "#3b82f6"
        assert d["x"] == 100.0
        assert d["y"] == 200.0

    def test_faction_roundtrip_json(self):
        f = Faction(name="红阵营", color="#ef4444", x=50, y=75)
        json_str = f.model_dump_json()
        f2 = Faction.model_validate_json(json_str)
        assert f2.color == "#ef4444"
        assert f2.x == 50.0

    def test_timeline_event_defaults(self):
        e = TimelineSandboxEvent(title="建国")
        d = e.model_dump()
        assert d["year"] == ""
        assert d["event_type"] == "general"
        assert d["linked_entity_id"] is None
        assert len(d["id"]) > 0

    def test_world_sandbox_data_timeline_default_empty(self):
        sandbox = WorldSandboxData()
        assert sandbox.timeline_events == []

    def test_world_sandbox_data_timeline_roundtrip(self):
        sandbox = WorldSandboxData(
            world_name="测试世界",
            timeline_events=[
                TimelineSandboxEvent(year="元年", title="创世"),
                TimelineSandboxEvent(year="100年", title="大战", event_type="conflict"),
            ],
        )
        json_str = sandbox.model_dump_json()
        sandbox2 = WorldSandboxData.model_validate_json(json_str)
        assert len(sandbox2.timeline_events) == 2
        assert sandbox2.timeline_events[0].title == "创世"
        assert sandbox2.timeline_events[1].event_type == "conflict"

    def test_world_relation_default_type_is_connection_enum(self):
        rel = WorldRelation(source_id="a", target_id="b")
        assert rel.relation_type == RelationType.CONNECTION

    def test_old_data_without_new_fields_parses_ok(self):
        """旧数据（无 color/x/y/timeline_events）可正常反序列化。"""
        old_faction_json = '{"id":"f1","name":"旧势力","scope":"internal","description":"","territory_region_ids":[],"alignment":"true_neutral","relation_map":{},"power_system_id":null,"notes":""}'
        f = Faction.model_validate_json(old_faction_json)
        assert f.color is None
        assert f.x == 0.0
        assert f.y == 0.0

    def test_old_sandbox_without_timeline_parses_ok(self):
        """旧沙盘数据（无 timeline_events）可正常反序列化。"""
        old_sandbox = {
            "world_name": "旧世界",
            "world_type": "continental",
            "world_description": "",
            "regions": [],
            "factions": [],
            "power_systems": [],
            "world_rules": [],
            "relations": [],
            "canvas_viewport": {},
        }
        sandbox = WorldSandboxData.model_validate(old_sandbox)
        assert sandbox.timeline_events == []
        assert sandbox.world_name == "旧世界"


# ------------------------------------------------------------------ #
# 3. Timeline CRUD API                                                  #
# ------------------------------------------------------------------ #


class TestTimelineCRUDApi:
    def test_list_timeline_empty(self, client):
        resp = client.get(f"/projects/{PROJECT_ID}/world/timeline")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_create_timeline_event(self, client):
        resp = client.post(
            f"/projects/{PROJECT_ID}/world/timeline",
            json={"year": "元年", "title": "天地初开", "description": "世界诞生", "event_type": "founding"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["title"] == "天地初开"
        assert body["year"] == "元年"
        assert body["event_type"] == "founding"
        assert "id" in body

    def test_get_timeline_event(self, client):
        create = client.post(
            f"/projects/{PROJECT_ID}-get/world/timeline",
            json={"title": "大洪水"},
        )
        event_id = create.json()["id"]
        resp = client.get(f"/projects/{PROJECT_ID}-get/world/timeline/{event_id}")
        assert resp.status_code == 200
        assert resp.json()["title"] == "大洪水"

    def test_get_timeline_event_404(self, client):
        resp = client.get(f"/projects/{PROJECT_ID}/world/timeline/nonexistent")
        assert resp.status_code == 404

    def test_update_timeline_event(self, client):
        create = client.post(
            f"/projects/{PROJECT_ID}-upd/world/timeline",
            json={"title": "旧标题", "year": "1年"},
        )
        event_id = create.json()["id"]
        update = client.put(
            f"/projects/{PROJECT_ID}-upd/world/timeline/{event_id}",
            json={"title": "新标题", "year": "2年"},
        )
        assert update.status_code == 200
        assert update.json()["title"] == "新标题"
        assert update.json()["year"] == "2年"

    def test_update_timeline_event_404(self, client):
        resp = client.put(
            f"/projects/{PROJECT_ID}/world/timeline/nonexistent",
            json={"title": "test"},
        )
        assert resp.status_code == 404

    def test_delete_timeline_event(self, client):
        create = client.post(
            f"/projects/{PROJECT_ID}-del/world/timeline",
            json={"title": "将被删除"},
        )
        event_id = create.json()["id"]
        delete = client.delete(f"/projects/{PROJECT_ID}-del/world/timeline/{event_id}")
        assert delete.status_code == 204

        get_after = client.get(f"/projects/{PROJECT_ID}-del/world/timeline/{event_id}")
        assert get_after.status_code == 404

    def test_delete_timeline_event_404(self, client):
        resp = client.delete(f"/projects/{PROJECT_ID}/world/timeline/nonexistent")
        assert resp.status_code == 404

    def test_timeline_full_crud_flow(self, client):
        pid = f"{PROJECT_ID}-crud-flow"
        # Create 2 events
        e1 = client.post(f"/projects/{pid}/world/timeline", json={"title": "事件一", "year": "1年"}).json()
        e2 = client.post(f"/projects/{pid}/world/timeline", json={"title": "事件二", "year": "2年"}).json()
        # List
        events = client.get(f"/projects/{pid}/world/timeline").json()
        assert len(events) == 2
        # Update
        client.put(f"/projects/{pid}/world/timeline/{e1['id']}", json={"title": "事件一修改版"})
        # Delete
        client.delete(f"/projects/{pid}/world/timeline/{e2['id']}")
        # Verify
        final = client.get(f"/projects/{pid}/world/timeline").json()
        assert len(final) == 1
        assert final[0]["title"] == "事件一修改版"


# ------------------------------------------------------------------ #
# 4. 世界概览接口                                                       #
# ------------------------------------------------------------------ #


class TestWorldOverviewApi:
    def test_overview_empty_world(self, client):
        resp = client.get(f"/projects/{PROJECT_ID}-overview-empty/world/overview")
        assert resp.status_code == 200
        body = resp.json()
        assert "statistics" in body
        assert "orphan_nodes" in body
        assert "completeness_hints" in body
        assert body["statistics"]["regions"] == 0

    def test_overview_with_data(self, client):
        pid = f"{PROJECT_ID}-overview"
        client.post(f"/projects/{pid}/world/regions", json={"name": "北境"})
        client.post(f"/projects/{pid}/world/regions", json={"name": "南境"})
        client.post(f"/projects/{pid}/world/factions", json={"name": "王国"})

        resp = client.get(f"/projects/{pid}/world/overview")
        body = resp.json()
        assert body["statistics"]["regions"] == 2
        assert body["statistics"]["factions"] == 1
        # All nodes should be orphaned since no relations exist
        assert len(body["orphan_nodes"]) == 3
        # Should have hints about no relations
        assert any("关系" in h for h in body["completeness_hints"])

    def test_overview_detects_orphan_nodes(self, client):
        pid = f"{PROJECT_ID}-orphan"
        r1 = client.post(f"/projects/{pid}/world/regions", json={"name": "东原"}).json()
        r2 = client.post(f"/projects/{pid}/world/regions", json={"name": "西岛"}).json()
        r3 = client.post(f"/projects/{pid}/world/regions", json={"name": "孤岛"}).json()
        # Connect r1 and r2 only
        client.post(f"/projects/{pid}/world/relations", json={
            "source_id": r1["id"], "target_id": r2["id"], "relation_type": "adjacent",
        })
        resp = client.get(f"/projects/{pid}/world/overview")
        orphans = resp.json()["orphan_nodes"]
        orphan_ids = [o["id"] for o in orphans]
        assert r3["id"] in orphan_ids
        assert r1["id"] not in orphan_ids


# ------------------------------------------------------------------ #
# 5. 地图布局接口                                                       #
# ------------------------------------------------------------------ #


class TestMapLayoutApi:
    def test_map_layout_empty(self, client):
        resp = client.get(f"/projects/{PROJECT_ID}-layout-empty/world/map-layout")
        assert resp.status_code == 200
        body = resp.json()
        assert body["nodes"] == []
        assert body["edges"] == []

    def test_map_layout_with_regions_no_adjacent(self, client):
        pid = f"{PROJECT_ID}-layout-no-adj"
        client.post(f"/projects/{pid}/world/regions", json={"name": "A区"})
        client.post(f"/projects/{pid}/world/regions", json={"name": "B区"})
        resp = client.get(f"/projects/{pid}/world/map-layout")
        body = resp.json()
        assert len(body["nodes"]) == 2
        assert body["edges"] == []

    def test_map_layout_with_adjacent_edges(self, client):
        pid = f"{PROJECT_ID}-layout-adj"
        r1 = client.post(f"/projects/{pid}/world/regions", json={"name": "城A"}).json()
        r2 = client.post(f"/projects/{pid}/world/regions", json={"name": "城B"}).json()
        r3 = client.post(f"/projects/{pid}/world/regions", json={"name": "城C"}).json()
        # Adjacent relations
        client.post(f"/projects/{pid}/world/relations", json={
            "source_id": r1["id"], "target_id": r2["id"], "relation_type": "adjacent",
        })
        client.post(f"/projects/{pid}/world/relations", json={
            "source_id": r2["id"], "target_id": r3["id"], "relation_type": "border",
        })
        # War relation (non-spatial, should be excluded from edges)
        client.post(f"/projects/{pid}/world/relations", json={
            "source_id": r1["id"], "target_id": r3["id"], "relation_type": "war",
        })
        resp = client.get(f"/projects/{pid}/world/map-layout")
        body = resp.json()
        assert len(body["nodes"]) == 3
        assert len(body["edges"]) == 2  # only adjacent and border, not war

    def test_map_layout_returns_faction_info(self, client):
        pid = f"{PROJECT_ID}-layout-fac"
        r1 = client.post(f"/projects/{pid}/world/regions", json={"name": "要塞"}).json()
        f1 = client.post(f"/projects/{pid}/world/factions", json={"name": "帝国"}).json()
        # Assign region to faction
        client.put(f"/projects/{pid}/world/factions/{f1['id']}", json={
            "id": f1["id"], "name": "帝国", "territory_region_ids": [r1["id"]],
        })
        resp = client.get(f"/projects/{pid}/world/map-layout")
        nodes = resp.json()["nodes"]
        node = next(n for n in nodes if n["id"] == r1["id"])
        assert f1["id"] in node["faction_ids"]


# ------------------------------------------------------------------ #
# 6. 关系类型标准化在 API 中的兼容                                       #
# ------------------------------------------------------------------ #


class TestRelationApiCompat:
    def test_create_relation_with_new_type_adjacent(self, client):
        pid = f"{PROJECT_ID}-reltype"
        r1 = client.post(f"/projects/{pid}/world/regions", json={"name": "A"}).json()
        r2 = client.post(f"/projects/{pid}/world/regions", json={"name": "B"}).json()
        resp = client.post(f"/projects/{pid}/world/relations", json={
            "source_id": r1["id"], "target_id": r2["id"], "relation_type": "adjacent",
        })
        assert resp.status_code == 201
        assert resp.json()["relation_type"] == "adjacent"

    def test_create_relation_with_all_new_types(self, client):
        pid = f"{PROJECT_ID}-all-types"
        r1 = client.post(f"/projects/{pid}/world/regions", json={"name": "X"}).json()
        r2 = client.post(f"/projects/{pid}/world/regions", json={"name": "Y"}).json()
        for rtype in ["adjacent", "border", "trade", "war", "alliance", "vassal", "blockade", "teleport", "connection"]:
            resp = client.post(f"/projects/{pid}/world/relations", json={
                "source_id": r1["id"], "target_id": r2["id"], "relation_type": rtype,
            })
            assert resp.status_code == 201, f"Failed for type: {rtype}"


# ------------------------------------------------------------------ #
# 7. 势力新字段在 API 中的使用                                           #
# ------------------------------------------------------------------ #


class TestFactionNewFieldsApi:
    def test_create_faction_without_color(self, client):
        pid = f"{PROJECT_ID}-fac-nocolor"
        resp = client.post(f"/projects/{pid}/world/factions", json={"name": "无色势力"})
        assert resp.status_code == 201
        body = resp.json()
        assert body["color"] is None
        assert body["x"] == 0.0
        assert body["y"] == 0.0

    def test_update_faction_with_color(self, client):
        pid = f"{PROJECT_ID}-fac-color"
        create = client.post(f"/projects/{pid}/world/factions", json={"name": "蓝组"})
        fid = create.json()["id"]
        update = client.put(f"/projects/{pid}/world/factions/{fid}", json={
            "id": fid, "name": "蓝组", "color": "#3b82f6", "x": 150.0, "y": 250.0,
        })
        assert update.status_code == 200
        assert update.json()["color"] == "#3b82f6"
        assert update.json()["x"] == 150.0
        assert update.json()["y"] == 250.0


# ------------------------------------------------------------------ #
# 8. finalize 摘要包含时间轴计数                                         #
# ------------------------------------------------------------------ #


class TestFinalizeIncludesTimeline:
    def test_finalize_summary_has_timeline_events(self, client):
        pid = f"{PROJECT_ID}-finalize"
        client.post(f"/projects/{pid}/world/timeline", json={"title": "开国"})
        client.post(f"/projects/{pid}/world/timeline", json={"title": "灭世"})
        resp = client.post(f"/projects/{pid}/world/finalize")
        assert resp.status_code == 200
        summary = resp.json()["summary"]
        assert summary["timeline_events"] == 2


# ------------------------------------------------------------------ #
# 9. 旧数据兼容性回归                                                   #
# ------------------------------------------------------------------ #


class TestBackwardCompatibility:
    def test_existing_project_data_unaffected(self, client):
        """已有项目的世界数据读取、编辑、保存不报错。"""
        pid = f"{PROJECT_ID}-compat"
        # Create full data
        r = client.post(f"/projects/{pid}/world/regions", json={"name": "旧城"})
        f = client.post(f"/projects/{pid}/world/factions", json={"name": "旧势力"})
        assert r.status_code == 201
        assert f.status_code == 201
        rid = r.json()["id"]
        fid = f.json()["id"]
        # Create relation with old-style type
        rel = client.post(f"/projects/{pid}/world/relations", json={
            "source_id": rid, "target_id": fid, "relation_type": "connection",
        })
        assert rel.status_code == 201
        # Read full world
        world = client.get(f"/projects/{pid}/world")
        assert world.status_code == 200
        data = world.json()
        assert "timeline_events" in data
        assert data["timeline_events"] == []
        # Finalize should still work
        fin = client.post(f"/projects/{pid}/world/finalize")
        assert fin.status_code == 200
        assert fin.json()["success"] is True
