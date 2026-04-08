"""
tests/test_api_management.py — 阶段二：项目管理 & CLI 覆盖端点测试

覆盖 8 个新端点的 happy-path 和基础错误路径：
  GET  /projects
  POST /projects/init
  POST /chapters/check
  POST /chapters/humanize
  POST /projects/{id}/rollback
  GET  /cost/summary
  GET  /cost/history
  GET  /projects/{id}/metrics/history
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from narrative_os.interface.api import app
from narrative_os.core.state import ChapterMeta, NarrativeState


# ------------------------------------------------------------------ #
# 固定装置                                                              #
# ------------------------------------------------------------------ #

@pytest.fixture()
def client():
    return TestClient(app, raise_server_exceptions=False)


def _make_state(project_id: str = "proj1", chapter: int = 3) -> NarrativeState:
    state = NarrativeState(project_id=project_id, project_name="Test " + project_id)
    state.current_chapter = chapter
    state.chapters = [
        ChapterMeta(chapter=1, summary="ch1", quality_score=0.8, hook_score=0.7, word_count=2000),
        ChapterMeta(chapter=2, summary="ch2", quality_score=0.9, hook_score=0.85, word_count=2100),
    ]
    return state


def _make_mgr(project_id: str = "proj1", chapter: int = 3):
    mgr = MagicMock()
    state = _make_state(project_id, chapter)
    mgr.state = state
    mgr.load_state.return_value = state
    mgr.load_kb.return_value = {}
    mgr.list_versions.return_value = [1, 2, 3]
    mgr.rollback.return_value = {"timestamp": "2024-01-01T00:00:00Z", "version": 2}
    mgr._dir = Path(f".narrative_state/{project_id}")
    mgr._versions_dir = Path(f".narrative_state/{project_id}/versions")
    return mgr


# ------------------------------------------------------------------ #
# GET /projects — 列出所有项目                                          #
# ------------------------------------------------------------------ #

def test_list_projects_returns_list(client, tmp_path, monkeypatch):
    """当 .narrative_state/ 存在时，返回项目列表。"""
    monkeypatch.chdir(tmp_path)
    base = tmp_path / ".narrative_state"
    base.mkdir()
    proj_dir = base / "my_novel"
    proj_dir.mkdir()
    state_data = {
        "project_id": "my_novel",
        "project_name": "我的小说",
        "current_chapter": 5,
        "updated_at": "2024-06-01T12:00:00Z",
    }
    (proj_dir / "state.json").write_text(json.dumps(state_data), encoding="utf-8")

    resp = client.get("/projects")

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 1
    item = data[0]
    assert item["project_id"] == "my_novel"
    assert item["title"] == "我的小说"
    assert item["chapter_count"] == 5


def test_list_projects_empty_when_no_state_dir(client, tmp_path, monkeypatch):
    """当 .narrative_state/ 不存在时，返回空列表（不报错）。"""
    monkeypatch.chdir(tmp_path)
    resp = client.get("/projects")
    assert resp.status_code == 200
    assert resp.json() == []


# ------------------------------------------------------------------ #
# POST /projects/init — 初始化项目                                      #
# ------------------------------------------------------------------ #

def test_init_project_creates_directory(client):
    """POST /projects/init 成功时返回 201 + project_id 字段。"""
    mgr = _make_mgr("new_novel", chapter=0)
    mgr.initialize.return_value = _make_state("new_novel", 0)

    with patch("narrative_os.interface.api.StateManager", return_value=mgr):
        resp = client.post("/projects/init", json={
            "project_id": "new_novel",
            "title": "测试小说",
            "genre": "仙侠",
            "description": "一个关于修仙的故事",
        })

    assert resp.status_code == 201
    data = resp.json()
    assert data["project_id"] == "new_novel"
    assert "created_at" in data
    assert "state_dir" in data
    mgr.initialize.assert_called_once_with(project_name="测试小说")


def test_init_project_saves_genre_to_kb(client):
    """初始化时提供 genre/description，应存入知识库。"""
    mgr = _make_mgr("proj_kb", chapter=0)
    mgr.initialize.return_value = _make_state("proj_kb", 0)
    mgr.load_kb.return_value = {}

    with patch("narrative_os.interface.api.StateManager", return_value=mgr):
        resp = client.post("/projects/init", json={
            "project_id": "proj_kb",
            "title": "",
            "genre": "玄幻",
            "description": "",
        })

    assert resp.status_code == 201
    mgr.save_kb.assert_called_once()
    saved_kb = mgr.save_kb.call_args[0][0]
    assert saved_kb.get("genre") == "玄幻"


# ------------------------------------------------------------------ #
# POST /chapters/check — 一致性检查                                     #
# ------------------------------------------------------------------ #

def test_check_chapter_returns_issues(client):
    """POST /chapters/check 对给定文本返回 issues 列表和 passed 标志。"""
    from narrative_os.skills.consistency import ConsistencyReport, ConsistencyIssue

    mock_issue = ConsistencyIssue(
        dimension="character",
        severity="soft",
        description="角色前后矛盾",
        suggestion="请检查角色状态",
        confidence=0.9,
    )
    mock_report = ConsistencyReport(passed=True, issues=[mock_issue])

    with patch("narrative_os.interface.api.ConsistencyChecker") as MockChecker:
        MockChecker.return_value.check.return_value = mock_report
        with patch("narrative_os.interface.api._try_load_project", return_value=None):
            resp = client.post("/chapters/check", json={
                "text": "这是一段测试文本，用于检验一致性检查功能。",
                "project_id": "default",
                "chapter": 1,
            })

    assert resp.status_code == 200
    data = resp.json()
    assert "issues" in data
    assert "passed" in data
    assert isinstance(data["issues"], list)
    assert data["passed"] is True
    assert len(data["issues"]) == 1
    assert data["issues"][0]["dimension"] == "character"
    assert data["issues"][0]["severity"] == "soft"


def test_check_chapter_empty_text_returns_422(client):
    """文本为空时，应返回 422 校验错误。"""
    resp = client.post("/chapters/check", json={"text": ""})
    assert resp.status_code == 422


# ------------------------------------------------------------------ #
# POST /chapters/humanize — 人味化处理                                  #
# ------------------------------------------------------------------ #

def test_humanize_returns_processed_text(client):
    """POST /chapters/humanize 返回 original/humanized/changes_count/diff。"""
    from narrative_os.skills.humanize import HumanizeOutput

    original_text = "这是一段机器生成的文本，充满了AI味道。"
    humanized_text = "这是一段经过人味化处理后的文本，读起来更自然。"

    mock_output = HumanizeOutput(
        original_text=original_text,
        humanized_text=humanized_text,
        change_ratio=0.4,
        applied_rules=["对话去AI化"],
        model_used="gpt-4o-mini",
    )

    with patch("narrative_os.skills.humanize.Humanizer.humanize", new_callable=AsyncMock, return_value=mock_output):
        resp = client.post("/chapters/humanize", json={
            "text": original_text,
            "project_id": "default",
            "intensity": 0.6,
        })

    assert resp.status_code == 200
    data = resp.json()
    assert data["original"] == original_text
    assert data["humanized"] == humanized_text
    assert "changes_count" in data
    assert "diff" in data
    assert isinstance(data["diff"], list)


# ------------------------------------------------------------------ #
# POST /projects/{id}/rollback — 项目回滚                               #
# ------------------------------------------------------------------ #

def test_rollback_returns_success(client):
    """POST /projects/{id}/rollback 成功时返回 rolled_back_to_chapter。"""
    mgr = _make_mgr("story1", chapter=3)

    with patch("narrative_os.interface.api._load_project_or_404", return_value=mgr):
        resp = client.post("/projects/story1/rollback", json={"steps": 1})

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["project_id"] == "story1"
    assert "rolled_back_to_chapter" in data
    assert "snapshot_timestamp" in data


def test_rollback_404_when_no_versions(client):
    """项目无版本快照时，应返回 404。"""
    mgr = _make_mgr("empty_proj", chapter=0)
    mgr.list_versions.return_value = []

    with patch("narrative_os.interface.api._load_project_or_404", return_value=mgr):
        resp = client.post("/projects/empty_proj/rollback", json={"steps": 1})

    assert resp.status_code == 404


# ------------------------------------------------------------------ #
# GET /cost/summary — 成本汇总                                          #
# ------------------------------------------------------------------ #

def test_cost_summary_structure(client):
    """GET /cost/summary 返回正确字段结构。"""
    mock_summary = {
        "budget": 100000,
        "used": 5000,
        "ratio": 0.05,
        "by_skill": {"writer": 3000, "planner": 2000},
        "by_agent": {"chapter_agent": 5000},
    }

    with patch("narrative_os.interface.api.cost_ctrl") as mock_ctrl:
        mock_ctrl.summary.return_value = mock_summary
        resp = client.get("/cost/summary")

    assert resp.status_code == 200
    data = resp.json()
    assert "today_tokens" in data
    assert "total_tokens" in data
    assert "today_cost_usd" in data
    assert "by_agent" in data
    assert "by_skill" in data
    assert data["today_tokens"] == 5000
    assert isinstance(data["today_cost_usd"], float)
    assert data["by_skill"]["writer"] == 3000


def test_cost_history_returns_list(client):
    """GET /cost/history 返回列表（可为空）。"""
    mock_summary = {
        "budget": 100000,
        "used": 0,
        "ratio": 0.0,
        "by_skill": {},
        "by_agent": {},
    }

    with patch("narrative_os.interface.api.cost_ctrl") as mock_ctrl:
        mock_ctrl.summary.return_value = mock_summary
        resp = client.get("/cost/history")

    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ------------------------------------------------------------------ #
# GET /projects/{id}/metrics/history — 章节评分历史                     #
# ------------------------------------------------------------------ #

def test_metrics_history_returns_list(client):
    """GET /projects/{id}/metrics/history 返回章节评分历史列表。"""
    mgr = _make_mgr("story2", chapter=2)

    with patch("narrative_os.interface.api._load_project_or_404", return_value=mgr):
        resp = client.get("/projects/story2/metrics/history")

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 2
    first = data[0]
    assert "chapter" in first
    assert "quality_score" in first
    assert "hook_score" in first
    assert "word_count" in first
    assert first["chapter"] == 1
    assert first["quality_score"] == pytest.approx(0.8)


def test_metrics_history_empty_for_new_project(client):
    """新项目（无章节记录）时返回空列表。"""
    mgr = _make_mgr("brand_new", chapter=0)
    mgr.state.chapters = []

    with patch("narrative_os.interface.api._load_project_or_404", return_value=mgr):
        resp = client.get("/projects/brand_new/metrics/history")

    assert resp.status_code == 200
    assert resp.json() == []


# ------------------------------------------------------------------ #
# 边界情况补充（6.1 丰富）                                              #
# ------------------------------------------------------------------ #

def test_init_project_missing_project_id_returns_422(client):
    """project_id 缺失时应返回 422 校验错误。"""
    resp = client.post("/projects/init", json={"title": "无ID项目"})
    assert resp.status_code == 422


def test_check_chapter_long_text_accepted(client):
    """5000 字文本也能被正常处理，不应返回 4xx。"""
    from narrative_os.skills.consistency import ConsistencyReport

    long_text = "这是测试文本。" * 500   # ~3500 chars
    mock_report = ConsistencyReport(passed=True, issues=[])

    with patch("narrative_os.interface.api.ConsistencyChecker") as MockChecker:
        MockChecker.return_value.check.return_value = mock_report
        with patch("narrative_os.interface.api._try_load_project", return_value=None):
            resp = client.post("/chapters/check", json={
                "text": long_text,
                "project_id": "default",
                "chapter": 1,
            })

    assert resp.status_code == 200
    data = resp.json()
    assert data["passed"] is True
    assert isinstance(data["issues"], list)


def test_humanize_empty_text_returns_422(client):
    """文本为空字符串时应返回 422。"""
    resp = client.post("/chapters/humanize", json={"text": "", "project_id": "default"})
    assert resp.status_code == 422


def test_humanize_intensity_out_of_range_returns_422(client):
    """intensity 超过 1.0 时应返回 422。"""
    resp = client.post("/chapters/humanize", json={
        "text": "一些文字",
        "project_id": "default",
        "intensity": 2.0,
    })
    assert resp.status_code == 422


def test_rollback_steps_zero_returns_422(client):
    """steps=0 违反 ge=1 约束，应返回 422。"""
    mgr = _make_mgr("proj_zero", chapter=2)

    with patch("narrative_os.interface.api._load_project_or_404", return_value=mgr):
        resp = client.post("/projects/proj_zero/rollback", json={"steps": 0})

    assert resp.status_code == 422


def test_list_projects_ignores_dirs_without_state_json(client, tmp_path, monkeypatch):
    """不含 state.json 的子目录应被跳过，不出现在列表中。"""
    monkeypatch.chdir(tmp_path)
    base = tmp_path / ".narrative_state"
    base.mkdir()
    # 有效项目
    valid = base / "valid_proj"
    valid.mkdir()
    (valid / "state.json").write_text(
        '{"project_id":"valid_proj","project_name":"有效","current_chapter":2}',
        encoding="utf-8",
    )
    # 无效目录（仅目录，无 state.json）
    (base / "incomplete_proj").mkdir()

    resp = client.get("/projects")
    assert resp.status_code == 200
    data = resp.json()
    ids = [item["project_id"] for item in data]
    assert "valid_proj" in ids
    assert "incomplete_proj" not in ids


def test_cost_summary_zero_usage(client):
    """当 used=0 时，today_cost_usd 和 ratio 均为 0。"""
    mock_summary = {"budget": 50000, "used": 0, "ratio": 0.0, "by_skill": {}, "by_agent": {}}

    with patch("narrative_os.interface.api.cost_ctrl") as mock_ctrl:
        mock_ctrl.summary.return_value = mock_summary
        resp = client.get("/cost/summary")

    assert resp.status_code == 200
    data = resp.json()
    assert data["today_tokens"] == 0
    assert data["today_cost_usd"] == pytest.approx(0.0)


def test_metrics_history_contains_8d_fields(client):
    """metrics/history 返回的每条记录应含 qd_* 字段（8D 雷达数据）。"""
    mgr = _make_mgr("story3", chapter=2)

    with patch("narrative_os.interface.api._load_project_or_404", return_value=mgr):
        resp = client.get("/projects/story3/metrics/history")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    first = data[0]
    # 8 个维度字段全部存在
    for i in range(1, 9):
        key = f"qd_{i:02d}"
        assert key in first, f"缺少字段 {key}"
        assert isinstance(first[key], float)
