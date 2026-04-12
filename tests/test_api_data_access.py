"""
tests/test_api_data_access.py — Phase 7: 数据访问 API 扩展测试

覆盖 13 个新端点的 happy-path 和 404/422 错误路径。
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from narrative_os.interface.api import (
    _wb_sessions,
    _wb_sessions_lock,
    _plugin_registry,
    _plugin_lock,
    app,
)


# ------------------------------------------------------------------ #
# 固定装置                                                              #
# ------------------------------------------------------------------ #

@pytest.fixture(autouse=True)
def reset_plugin_registry():
    """每个测试前后重置插件注册表为默认状态。"""
    original = {k: dict(v) for k, v in _plugin_registry.items()}
    yield
    with _plugin_lock:
        _plugin_registry.clear()
        _plugin_registry.update(original)


@pytest.fixture(autouse=True)
def clear_wb_sessions():
    """每个测试前后清空 WorldBuilder 会话。"""
    with _wb_sessions_lock:
        _wb_sessions.clear()
    yield
    with _wb_sessions_lock:
        _wb_sessions.clear()


@pytest.fixture()
def client():
    return TestClient(app, raise_server_exceptions=False)


def _mock_mgr(kb: dict | None = None, raises: bool = False):
    """构造 StateManager mock，可选择抛出 FileNotFoundError。"""
    mgr = MagicMock()
    if raises:
        mgr.load_state.side_effect = FileNotFoundError("not found")
    else:
        mgr.load_state.return_value = MagicMock()
        mgr.load_kb.return_value = kb or {}
    return mgr


# ------------------------------------------------------------------ #
# C1: GET /projects/{id}/plot                                          #
# ------------------------------------------------------------------ #

def test_get_plot_returns_nodes_and_edges(client):
    """存在项目时返回包含 nodes/edges 的 PlotGraph 结构。"""
    with patch("narrative_os.interface.api.StateManager", return_value=_mock_mgr()):
        resp = client.get("/projects/p1/plot")
    assert resp.status_code == 200
    body = resp.json()
    assert "nodes" in body
    assert "edges" in body
    assert body["current_volume_goal"] == ""


def test_get_plot_empty_on_missing_project(client):
    """项目不存在时返回空 PlotGraph（200）而非 404。"""
    with patch("narrative_os.interface.api.StateManager", return_value=_mock_mgr(raises=True)):
        resp = client.get("/projects/nonexistent/plot")
    assert resp.status_code == 200
    body = resp.json()
    assert "nodes" in body
    assert "edges" in body
    assert body["current_volume_goal"] == ""


def test_update_plot_volume_goal_creates_active_node(client):
    """PUT /projects/{id}/plot/volume-goal 在空图时创建一个激活节点并回写 KB。"""
    mgr = _mock_mgr(kb={})
    with patch("narrative_os.interface.api.StateManager", return_value=mgr):
        resp = client.put("/projects/p1/plot/volume-goal", json={"current_volume_goal": "卷一：找到黑石镇的入口"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["current_volume_goal"] == "卷一：找到黑石镇的入口"
    assert body["nodes"][0]["summary"] == "卷一：找到黑石镇的入口"
    saved_kb = mgr.save_kb.call_args.args[0]
    assert saved_kb["plot_graph"]["nodes"][0]["status"] == "active"


def test_update_plot_volume_goal_updates_existing_active_node(client):
    """已有 PlotGraph 时优先更新当前 active 节点摘要。"""
    kb = {
        "plot_graph": {
            "nodes": [
                {
                    "id": "goal-1",
                    "type": "setup",
                    "summary": "旧目标",
                    "tension": 0.5,
                    "status": "active",
                    "chapter_ref": 1,
                }
            ],
            "edges": [],
        }
    }
    mgr = _mock_mgr(kb=kb)
    with patch("narrative_os.interface.api.StateManager", return_value=mgr):
        resp = client.put("/projects/p1/plot/volume-goal", json={"current_volume_goal": "卷一：穿过荒原进入黑石镇"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["current_volume_goal"] == "卷一：穿过荒原进入黑石镇"
    assert body["nodes"][0]["summary"] == "卷一：穿过荒原进入黑石镇"


# ------------------------------------------------------------------ #
# C2: GET /projects/{id}/characters                                    #
# ------------------------------------------------------------------ #

def test_get_characters_returns_list(client):
    """存在角色数据时返回角色列表。"""
    kb = {"characters": [{"name": "林枫", "arc_stage": "觉醒", "faction": "林家", "is_alive": True}]}
    with patch("narrative_os.interface.api.StateManager", return_value=_mock_mgr(kb=kb)):
        resp = client.get("/projects/p1/characters")
    assert resp.status_code == 200
    chars = resp.json()
    assert isinstance(chars, list)
    assert chars[0]["name"] == "林枫"


def test_get_characters_returns_empty_list_when_no_characters(client):
    """项目存在但无角色数据时返回空列表。"""
    with patch("narrative_os.interface.api.StateManager", return_value=_mock_mgr(kb={})):
        resp = client.get("/projects/p1/characters")
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_characters_empty_on_missing_project(client):
    """项目不存在时返回空列表（200）而非 404。"""
    with patch("narrative_os.interface.api.StateManager", return_value=_mock_mgr(raises=True)):
        resp = client.get("/projects/ghost/characters")
    assert resp.status_code == 200
    assert resp.json() == []


# ------------------------------------------------------------------ #
# C3: GET /projects/{id}/characters/{name}                             #
# ------------------------------------------------------------------ #

def test_get_character_detail_returns_full_record(client):
    """按名称查找时返回完整角色记录。"""
    kb = {"characters": [{"name": "叶辰", "arc_stage": "成长", "traits": ["冷酷", "聪明"]}]}
    with patch("narrative_os.interface.api.StateManager", return_value=_mock_mgr(kb=kb)):
        resp = client.get("/projects/p1/characters/叶辰")
    assert resp.status_code == 200
    assert resp.json()["name"] == "叶辰"


def test_get_character_detail_404_on_missing(client):
    """角色不存在时返回 404。"""
    with patch("narrative_os.interface.api.StateManager", return_value=_mock_mgr(kb={"characters": []})):
        resp = client.get("/projects/p1/characters/不存在")
    assert resp.status_code == 404


# ------------------------------------------------------------------ #
# C4: GET /projects/{id}/memory                                        #
# ------------------------------------------------------------------ #

def test_get_memory_returns_counts(client):
    """返回 MemorySnapshot 结构（short_term / mid_term / long_term / collections / recent_anchors）。"""
    with patch("narrative_os.interface.api.StateManager", return_value=_mock_mgr()):
        with patch("narrative_os.interface.api.MemorySystem") as mock_ms:
            mock_ms.return_value.collection_counts.return_value = {}
            mock_ms.return_value.get_recent_anchors.return_value = []
            resp = client.get("/projects/p1/memory")
    assert resp.status_code == 200
    body = resp.json()
    assert "short_term" in body
    assert "mid_term" in body
    assert "long_term" in body
    assert "collections" in body
    assert "recent_anchors" in body


def test_get_memory_empty_on_missing_project(client):
    """项目不存在时返回空 MemorySnapshot（200）而非 404。"""
    with patch("narrative_os.interface.api.StateManager", return_value=_mock_mgr(raises=True)):
        with patch("narrative_os.interface.api.MemorySystem") as mock_ms:
            mock_ms.return_value.collection_counts.return_value = {}
            mock_ms.return_value.get_recent_anchors.return_value = []
            resp = client.get("/projects/ghost/memory")
    assert resp.status_code == 200
    body = resp.json()
    assert body["short_term"] == 0
    assert body["mid_term"] == 0
    assert body["long_term"] == 0


# ------------------------------------------------------------------ #
# C5: GET /projects/{id}/memory/search                                 #
# ------------------------------------------------------------------ #

def test_search_memory_requires_q_param(client):
    """缺少 q 参数时返回 422 Unprocessable Entity。"""
    with patch("narrative_os.interface.api.StateManager", return_value=_mock_mgr()):
        resp = client.get("/projects/p1/memory/search")
    assert resp.status_code == 422


def test_search_memory_q_max_length_200(client):
    """q 参数超过 200 字符时返回 422。"""
    long_q = "a" * 201
    with patch("narrative_os.interface.api.StateManager", return_value=_mock_mgr()):
        resp = client.get(f"/projects/p1/memory/search?q={long_q}")
    assert resp.status_code == 422


def test_search_memory_returns_results(client):
    """合法 q 参数时返回 query + results 结构。"""
    mock_result = MagicMock()
    mock_result.content = "主角登场"
    mock_result.similarity = 0.95
    with patch("narrative_os.interface.api.StateManager", return_value=_mock_mgr()):
        with patch("narrative_os.interface.api.MemorySystem") as mock_ms:
            mock_ms.return_value.retrieve_memory.return_value = [mock_result]
            resp = client.get("/projects/p1/memory/search?q=主角")
    assert resp.status_code == 200
    body = resp.json()
    assert body["query"] == "主角"
    assert isinstance(body["results"], list)


# ------------------------------------------------------------------ #
# C6: GET /traces/{chapter_id}                                         #
# ------------------------------------------------------------------ #

def test_get_traces_returns_200_with_empty_tree(client):
    """无日志数据时返回 200 + 空 nodes/edges + note 字段。"""
    resp = client.get("/traces/ch0001")
    assert resp.status_code == 200
    body = resp.json()
    assert body["nodes"] == []
    assert body["edges"] == []
    assert "note" in body
    assert body["chapter_id"] == "ch0001"


# ------------------------------------------------------------------ #
# C7–C8: 插件管理                                                      #
# ------------------------------------------------------------------ #

def test_list_plugins_returns_list(client):
    """返回插件列表，所有条目包含 id 和 enabled 字段。"""
    resp = client.get("/plugins")
    assert resp.status_code == 200
    plugins = resp.json()
    assert isinstance(plugins, list)
    assert len(plugins) > 0
    for p in plugins:
        assert "id" in p
        assert "enabled" in p


def test_plugin_toggle_changes_enabled_flag(client):
    """切换插件状态后 enabled 应取反。"""
    # 获取初始状态
    resp_before = client.get("/plugins")
    humanizer_before = next(p for p in resp_before.json() if p["id"] == "humanizer")
    initial_state = humanizer_before["enabled"]

    resp = client.post("/plugins/humanizer/toggle")
    assert resp.status_code == 200
    assert resp.json()["enabled"] == (not initial_state)


def test_toggle_plugin_404_on_unknown(client):
    """未知插件 ID 时返回 404。"""
    resp = client.post("/plugins/unknown_plugin/toggle")
    assert resp.status_code == 404


# ------------------------------------------------------------------ #
# C9–C10: 风格控制                                                     #
# ------------------------------------------------------------------ #

def test_extract_style_returns_dict(client):
    """POST /style/extract 返回包含 5 维风格参数的字典。"""
    resp = client.post("/style/extract", json={"text": "主角踏上旅途，前路漫漫。他抬头望天，心中坚定。"})
    assert resp.status_code == 200
    body = resp.json()
    assert "sentence_length" in body
    assert "tone" in body
    assert "genre" in body
    assert "style_directives" in body
    assert "warning_words" in body


def test_extract_style_empty_text_returns_422(client):
    """空文本（min_length=1 验证）时返回 422。"""
    resp = client.post("/style/extract", json={"text": ""})
    assert resp.status_code == 422


def test_list_style_presets_returns_list(client):
    """GET /style/presets 返回非空预设列表。"""
    resp = client.get("/style/presets")
    assert resp.status_code == 200
    presets = resp.json()
    assert isinstance(presets, list)
    assert len(presets) > 0
    assert "id" in presets[0]


# ------------------------------------------------------------------ #
# C11–C12: WorldBuilder 会话                                           #
# ------------------------------------------------------------------ #

def test_worldbuilder_start_returns_prompt(client):
    """POST /worldbuilder/start 返回 wb_session_id 和 step/prompt。"""
    resp = client.post("/worldbuilder/start")
    assert resp.status_code == 200
    body = resp.json()
    assert "wb_session_id" in body
    assert "step" in body
    assert "prompt" in body
    assert len(body["wb_session_id"]) > 0


def test_worldbuilder_step_advances_state(client):
    """POST /worldbuilder/step 用有效 session 推进状态。"""
    start_resp = client.post("/worldbuilder/start")
    wb_id = start_resp.json()["wb_session_id"]

    step_resp = client.post("/worldbuilder/step", json={
        "wb_session_id": wb_id,
        "user_input": "落魄少年在修炼者大陆凭借上古斗技，誓要复仇。",
    })
    assert step_resp.status_code == 200
    body = step_resp.json()
    assert "step" in body
    assert "done" in body
    assert body["wb_session_id"] == wb_id


def test_worldbuilder_step_404_on_unknown_session(client):
    """无效 wb_session_id 时返回 404。"""
    resp = client.post("/worldbuilder/step", json={
        "wb_session_id": "00000000-0000-0000-0000-000000000000",
        "user_input": "任意输入",
    })
    assert resp.status_code == 404


# ------------------------------------------------------------------ #
# C13: 一致性检查                                                       #
# ------------------------------------------------------------------ #

def test_consistency_check_returns_report(client):
    """POST /consistency/check 返回 ConsistencyReport 结构。"""
    resp = client.post("/consistency/check", json={
        "text": "主角在第一章登场，第二章死亡，第三章再次出现。",
        "chapter": 3,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert "score" in body
    assert "issues" in body
    assert isinstance(body["issues"], list)


def test_consistency_check_empty_text_returns_422(client):
    """空 text 字段（min_length 验证）时返回 422。"""
    resp = client.post("/consistency/check", json={"text": "", "chapter": 0})
    assert resp.status_code == 422


# ------------------------------------------------------------------ #
# C14+: 世界沙盘关系与详情接口                                         #
# ------------------------------------------------------------------ #

def test_world_relation_crud_flow(client):
    """关系创建/列表/详情/更新/删除全流程可用。"""
    project_id = "wb-rel-crud"

    r1 = client.post(f"/projects/{project_id}/world/regions", json={"name": "北境", "region_type": "雪原"})
    r2 = client.post(f"/projects/{project_id}/world/regions", json={"name": "南境", "region_type": "港湾"})
    assert r1.status_code == 201
    assert r2.status_code == 201
    region_a = r1.json()["id"]
    region_b = r2.json()["id"]

    create_resp = client.post(
        f"/projects/{project_id}/world/relations",
        json={
            "source_id": region_a,
            "target_id": region_b,
            "relation_type": "trade",
            "label": "北南商路",
            "description": "冬季封港前的主航线",
        },
    )
    assert create_resp.status_code == 201
    relation_id = create_resp.json()["id"]

    list_resp = client.get(f"/projects/{project_id}/world/relations")
    assert list_resp.status_code == 200
    assert any(item["id"] == relation_id for item in list_resp.json())

    get_resp = client.get(f"/projects/{project_id}/world/relations/{relation_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["relation_type"] == "trade"

    update_resp = client.put(
        f"/projects/{project_id}/world/relations/{relation_id}",
        json={"relation_type": "alliance", "label": "北南同盟"},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["relation_type"] == "alliance"
    assert update_resp.json()["label"] == "北南同盟"

    delete_resp = client.delete(f"/projects/{project_id}/world/relations/{relation_id}")
    assert delete_resp.status_code == 204

    missing_resp = client.get(f"/projects/{project_id}/world/relations/{relation_id}")
    assert missing_resp.status_code == 404


def test_world_relation_create_rejects_unknown_nodes(client):
    """关系创建时 source/target 不存在应返回 422。"""
    project_id = "wb-rel-invalid"
    resp = client.post(
        f"/projects/{project_id}/world/relations",
        json={
            "source_id": "missing-a",
            "target_id": "missing-b",
            "relation_type": "alliance",
        },
    )
    assert resp.status_code == 422


def test_world_get_faction_and_power_system_detail(client):
    """新增势力与力量体系详情接口可读取具体对象。"""
    project_id = "wb-details"
    faction = client.post(
        f"/projects/{project_id}/world/factions",
        json={"name": "赤曜会", "scope": "internal", "description": "地下情报组织"},
    )
    power = client.post(
        f"/projects/{project_id}/world/power-systems",
        json={"name": "灵脉体系", "template": "custom"},
    )
    assert faction.status_code == 201
    assert power.status_code == 201

    faction_id = faction.json()["id"]
    ps_id = power.json()["id"]

    f_get = client.get(f"/projects/{project_id}/world/factions/{faction_id}")
    p_get = client.get(f"/projects/{project_id}/world/power-systems/{ps_id}")
    assert f_get.status_code == 200
    assert p_get.status_code == 200
    assert f_get.json()["name"] == "赤曜会"
    assert p_get.json()["name"] == "灵脉体系"


def test_world_region_update_requires_full_schema(client):
    """地区更新收紧为结构化模型后，部分字段更新应返回 422。"""
    project_id = "wb-region-validate"
    created = client.post(
        f"/projects/{project_id}/world/regions",
        json={"name": "中枢城", "region_type": "城市"},
    )
    assert created.status_code == 201
    region_id = created.json()["id"]

    # 仅传 x/y，不满足 Region 模型
    invalid = client.put(
        f"/projects/{project_id}/world/regions/{region_id}",
        json={"x": 233, "y": 144},
    )
    assert invalid.status_code == 422
