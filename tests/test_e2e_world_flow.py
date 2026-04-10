"""
tests/test_e2e_world_flow.py — 世界构建模块优化三阶段·阶段三 E2E 测试

模拟真实用户流程：
  创建项目→构建世界元信息→创建地区→创建势力→
  建立归属→创建关系→添加时间轴事件→finalize

每个测试使用唯一 project_id 保证隔离。
"""
from __future__ import annotations

import uuid
import pytest
from fastapi.testclient import TestClient

from narrative_os.interface.api import app


@pytest.fixture()
def client():
    return TestClient(app, raise_server_exceptions=False)


def _pid():
    return f"e2e-{uuid.uuid4().hex[:8]}"


class TestE2EWorldFlow:
    """完整用户流程测试：从空白到 finalize。"""

    def test_full_user_flow(self, client):
        pid = _pid()

        # 1. 创建/更新世界元信息
        meta_res = client.put(f"/projects/{pid}/world/meta", json={
            "world_name": "九州天玄界",
            "world_type": "continental",
            "world_description": "一个由九大洲组成的玄幻世界",
        })
        assert meta_res.status_code == 200

        # 2. 创建 5 个地区
        region_ids = []
        region_names = ["玄天城", "幽冥谷", "龙脉山", "碧波海", "落日荒原"]
        region_types = ["capital", "cave", "mountain", "ocean", "desert"]
        for name, rtype in zip(region_names, region_types):
            r = client.post(f"/projects/{pid}/world/regions", json={
                "name": name, "region_type": rtype
            })
            assert r.status_code in (200, 201), f"Failed to create region {name}: {r.text}"
            region_ids.append(r.json()["id"])
        assert len(region_ids) == 5

        # 3. 创建 2 个势力 (with color)
        f1 = client.post(f"/projects/{pid}/world/factions", json={
            "name": "天玄宗", "scope": "internal", "description": "最强宗门",
        })
        assert f1.status_code in (200, 201)
        f1_id = f1.json()["id"]

        f2 = client.post(f"/projects/{pid}/world/factions", json={
            "name": "魔道联盟", "scope": "external", "description": "反派势力",
        })
        assert f2.status_code in (200, 201)
        f2_id = f2.json()["id"]

        # 4. 设置势力颜色和领地归属
        client.put(f"/projects/{pid}/world/factions/{f1_id}", json={
            "id": f1_id, "name": "天玄宗", "scope": "internal",
            "description": "最强宗门", "color": "#2ef2ff",
            "territory_region_ids": [region_ids[0], region_ids[2]],
            "alignment": "lawful_good", "relation_map": {},
            "power_system_id": None, "notes": "",
        })
        client.put(f"/projects/{pid}/world/factions/{f2_id}", json={
            "id": f2_id, "name": "魔道联盟", "scope": "external",
            "description": "反派势力", "color": "#ff2e88",
            "territory_region_ids": [region_ids[1], region_ids[3]],
            "alignment": "chaotic_evil", "relation_map": {},
            "power_system_id": None, "notes": "",
        })

        # 5. 创建关系 (multiple types)
        relations = [
            (region_ids[0], region_ids[2], "adjacent", "城山相连"),
            (region_ids[1], region_ids[3], "adjacent", "谷海通道"),
            (f1_id, f2_id, "war", "正邪大战"),
            (region_ids[0], region_ids[1], "border", "边境"),
            (region_ids[2], region_ids[4], "trade", "山原贸易"),
        ]
        for src, tgt, rtype, label in relations:
            rel = client.post(f"/projects/{pid}/world/relations", json={
                "source_id": src, "target_id": tgt,
                "relation_type": rtype, "label": label,
            })
            assert rel.status_code in (200, 201), f"Failed to create relation {label}: {rel.text}"

        # 6. 验证世界概览
        overview = client.get(f"/projects/{pid}/world/overview")
        assert overview.status_code == 200
        ov = overview.json()
        assert ov["statistics"]["regions"] == 5
        assert ov["statistics"]["factions"] == 2
        assert ov["statistics"]["relations"] == 5

        # 7. 验证地图布局
        layout = client.get(f"/projects/{pid}/world/map-layout")
        assert layout.status_code == 200
        ldata = layout.json()
        assert len(ldata["nodes"]) >= 5

        # 8. 添加时间轴事件
        te1 = client.post(f"/projects/{pid}/world/timeline", json={
            "title": "天玄宗建立", "year": "100", "event_type": "historical"
        })
        assert te1.status_code in (200, 201)

        te2 = client.post(f"/projects/{pid}/world/timeline", json={
            "title": "正邪大战", "year": "500", "event_type": "conflict"
        })
        assert te2.status_code in (200, 201)

        te3 = client.post(f"/projects/{pid}/world/timeline", json={
            "title": "和平协议", "year": "800", "event_type": "general"
        })
        assert te3.status_code in (200, 201)

        # Verify timeline list
        tl = client.get(f"/projects/{pid}/world/timeline")
        assert tl.status_code == 200
        assert len(tl.json()) == 3

        # 9. Finalize
        fin = client.post(f"/projects/{pid}/world/finalize")
        assert fin.status_code == 200
        summary = fin.json()["summary"]
        assert summary["regions"] == 5
        assert summary["factions"] == 2
        assert summary["relations"] == 5
        assert summary["timeline_events"] == 3

        # 10. Verify data persists after re-read
        world_data = client.get(f"/projects/{pid}/world")
        assert world_data.status_code == 200
        wd = world_data.json()
        assert wd["world_name"] == "九州天玄界"
        assert len(wd["regions"]) == 5
        assert len(wd["factions"]) == 2
        assert len(wd["relations"]) == 5


class TestMapViewAdjacency:
    """地图视图邻接自查：5+ 地区含邻接关系。"""

    def test_adjacent_regions_layout(self, client):
        pid = _pid()
        # Create 6 regions
        rids = []
        for i in range(6):
            r = client.post(f"/projects/{pid}/world/regions", json={
                "name": f"Region-{i}", "region_type": "plain"
            })
            assert r.status_code in (200, 201)
            rids.append(r.json()["id"])

        # Create adjacency chain: 0-1-2-3-4-5
        for i in range(5):
            rel = client.post(f"/projects/{pid}/world/relations", json={
                "source_id": rids[i], "target_id": rids[i + 1],
                "relation_type": "adjacent", "label": f"adj-{i}"
            })
            assert rel.status_code in (200, 201)

        # Verify map layout
        layout = client.get(f"/projects/{pid}/world/map-layout")
        assert layout.status_code == 200
        nodes = layout.json()["nodes"]
        assert len(nodes) >= 6
        # Verify all nodes have positions
        for n in nodes:
            assert "x" in n and "y" in n


class TestTimelineBackendPersistence:
    """时间轴后端持久化自查。"""

    def test_timeline_crud_and_persist(self, client):
        pid = _pid()

        # Create events
        e1 = client.post(f"/projects/{pid}/world/timeline", json={
            "title": "开天辟地", "year": "1"
        })
        assert e1.status_code in (200, 201)
        e1_id = e1.json()["id"]

        e2 = client.post(f"/projects/{pid}/world/timeline", json={
            "title": "文明诞生", "year": "1000"
        })
        assert e2.status_code in (200, 201)

        # List
        tl = client.get(f"/projects/{pid}/world/timeline")
        assert len(tl.json()) == 2

        # Update
        upd = client.put(f"/projects/{pid}/world/timeline/{e1_id}", json={
            "title": "开天辟地（修订）", "description": "宇宙起源"
        })
        assert upd.status_code == 200
        assert upd.json()["title"] == "开天辟地（修订）"

        # Delete one
        d = client.delete(f"/projects/{pid}/world/timeline/{e1_id}")
        assert d.status_code in (200, 204)

        tl2 = client.get(f"/projects/{pid}/world/timeline")
        assert len(tl2.json()) == 1

        # Re-read world — timeline should reflect changes
        wd = client.get(f"/projects/{pid}/world")
        assert wd.status_code == 200


class TestFinalizeQualityGate:
    """finalize 摘要验证。"""

    def test_finalize_returns_complete_summary(self, client):
        pid = _pid()
        # Minimal setup
        client.put(f"/projects/{pid}/world/meta", json={
            "world_name": "测试世界", "world_type": "continental",
        })
        r = client.post(f"/projects/{pid}/world/regions", json={"name": "测试地区"})
        assert r.status_code in (200, 201)

        f = client.post(f"/projects/{pid}/world/factions", json={"name": "测试势力"})
        assert f.status_code in (200, 201)

        fin = client.post(f"/projects/{pid}/world/finalize")
        assert fin.status_code == 200
        s = fin.json()["summary"]
        assert "regions" in s
        assert "factions" in s
        assert "power_systems" in s
        assert "relations" in s
        assert "timeline_events" in s
