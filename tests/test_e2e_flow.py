"""
tests/test_e2e_flow.py — Phase 3: 端到端流程集成测试

覆盖从「创建项目 → 世界构建 → 生成章节 → 导出」的完整流程
以及 TRPG session_end 持久化路径。
使用 Mock 代替真实 LLM 调用，全部为幂等测试。
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from narrative_os.interface.api import app, _sessions, _sessions_lock, _wb_sessions, _wb_sessions_lock
from narrative_os.core.state import ChapterMeta, NarrativeState


# ------------------------------------------------------------------ #
# 固定装置                                                              #
# ------------------------------------------------------------------ #

@pytest.fixture(autouse=True)
def clear_sessions():
    with _sessions_lock:
        _sessions.clear()
    with _wb_sessions_lock:
        _wb_sessions.clear()
    yield
    with _sessions_lock:
        _sessions.clear()
    with _wb_sessions_lock:
        _wb_sessions.clear()


@pytest.fixture()
def client():
    return TestClient(app, raise_server_exceptions=False)


def _base_mgr(project_id: str = "e2e_proj", chapter: int = 0):
    """返回通用 StateManager mock。"""
    mgr = MagicMock()
    state = NarrativeState(project_id=project_id, project_name=project_id)
    state.current_chapter = chapter
    state.chapters = [
        ChapterMeta(chapter=n, summary=f"ch{n}", quality_score=0.8, hook_score=0.7, word_count=2000)
        for n in range(1, chapter + 1)
    ]
    mgr.state = state
    mgr.load_state.return_value = state
    mgr.load_kb.return_value = {}
    mgr.list_chapter_files.return_value = list(range(1, chapter + 1))
    mgr.load_chapter_text.return_value = "章节内容示例" if chapter > 0 else None
    mgr.list_versions.return_value = list(range(1, chapter + 1))
    mgr._dir = MagicMock()
    mgr._versions_dir = MagicMock()
    return mgr


# ------------------------------------------------------------------ #
# 项目管理基础流程                                                       #
# ------------------------------------------------------------------ #

class TestProjectFlow:
    def test_list_projects_empty(self, client):
        """初始时项目列表为空或不报错。"""
        with patch("narrative_os.interface.api.StateManager") as MockMgr:
            MockMgr.side_effect = FileNotFoundError
            r = client.get("/projects")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_init_project(self, client):
        """初始化项目成功，返回 project_id。"""
        from narrative_os.core.state import NarrativeState
        mgr = _base_mgr("new_proj", 0)
        new_state = NarrativeState(project_id="new_proj", project_name="new_proj")
        mgr.initialize.return_value = new_state
        with patch("narrative_os.interface.api.StateManager", return_value=mgr):
            r = client.post("/projects/init", json={"project_id": "new_proj", "title": "new_proj"})
        assert r.status_code == 201
        assert r.json()["project_id"] == "new_proj"


# ------------------------------------------------------------------ #
# 章节列表与导出                                                        #
# ------------------------------------------------------------------ #

class TestChapterExportFlow:
    def test_chapter_list_empty(self, client):
        """新项目章节列表为空。"""
        mgr = _base_mgr("new_proj", 0)
        with patch("narrative_os.interface.api._load_project_or_404", return_value=mgr):
            r = client.get("/projects/new_proj/chapters")
        assert r.status_code == 200
        assert r.json() == []

    def test_export_no_chapters(self, client):
        """无章节时导出返回 404（无章节视为 not found）。"""
        mgr = _base_mgr("new_proj", 0)
        mgr.load_chapter_text.return_value = None
        with patch("narrative_os.interface.api._load_project_or_404", return_value=mgr):
            r = client.get("/projects/new_proj/export")
        assert r.status_code == 404

    def test_chapter_list_with_data(self, client):
        """有章节时返回正确列表。"""
        mgr = _base_mgr("proj_with_ch", 3)
        with patch("narrative_os.interface.api._load_project_or_404", return_value=mgr):
            r = client.get("/projects/proj_with_ch/chapters")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 3
        assert data[0]["chapter"] == 1

    def test_export_with_chapters(self, client):
        """有章节时导出返回正确总字数。"""
        mgr = _base_mgr("proj_with_ch", 2)
        mgr.load_chapter_text.return_value = "一" * 1000  # 1000字
        with patch("narrative_os.interface.api._load_project_or_404", return_value=mgr):
            r = client.get("/projects/proj_with_ch/export")
        assert r.status_code == 200
        body = r.json()
        assert body["chapter_count"] == 2
        assert body["total_words"] >= 1000


# ------------------------------------------------------------------ #
# WorldBuilder 流程                                                     #
# ------------------------------------------------------------------ #

class TestWorldBuilderFlow:
    def test_worldbuilder_start(self, client):
        """WorldBuilder /worldbuilder/start 端点存在，返回非 5xx。"""
        # 仅验证路由已注册，不做 agent 内部验证
        r = client.post("/worldbuilder/start", json={"project_id": "e2e_proj"})
        assert r.status_code < 500

    def test_worldbuilder_step_missing_session(self, client):
        """不存在的 WorldBuilder session 返回 404。"""
        r = client.post("/worldbuilder/nonexistent_session/step",
                        json={"user_input": "测试"})
        assert r.status_code in (404, 422)


# ------------------------------------------------------------------ #
# TRPG session_end 持久化                                               #
# ------------------------------------------------------------------ #

class TestTRPGSessionEnd:
    def test_session_end_persists_chapter(self, client):
        """session_end 在 chapter_text 存在时触发持久化。"""
        from narrative_os.agents.interactive import InteractiveSession, InteractiveAgent

        mock_session = MagicMock(spec=InteractiveSession)
        mock_session.project_id = "trpg_proj"

        mock_agent = MagicMock(spec=InteractiveAgent)
        mock_agent.land.return_value = {
            "chapter_text": "这是 TRPG 章节正文内容，超过一百字。" * 10,
            "word_count": 200,
            "hook": "下一章悬念。",
            "character_deltas": [],
            "turns": 10,
            "history_summary": "故事摘要。",
        }

        mgr = _base_mgr("trpg_proj", 0)

        import time
        with _sessions_lock:
            _sessions["trpg_test_001"] = (mock_session, time.time())

        with patch("narrative_os.interface.api._interactive_agent", mock_agent):
            with patch("narrative_os.interface.api.StateManager", return_value=mgr):
                r = client.post("/sessions/trpg_test_001/end")

        assert r.status_code == 200
        body = r.json()
        assert body["word_count"] == 200
        assert body["next_hook"] == "下一章悬念。"
        # 持久化应该被调用
        mgr.save_chapter_text.assert_called_once()
        mgr.commit_chapter.assert_called_once()

    def test_session_end_no_text(self, client):
        """chapter_text 为空时不调用持久化，但仍返回 200。"""
        from narrative_os.agents.interactive import InteractiveSession, InteractiveAgent

        mock_session = MagicMock(spec=InteractiveSession)
        mock_session.project_id = "trpg_proj2"

        mock_agent = MagicMock(spec=InteractiveAgent)
        mock_agent.land.return_value = {
            "chapter_text": "",
            "word_count": 0,
            "hook": "",
            "character_deltas": [],
            "turns": 0,
            "history_summary": "",
        }

        mgr = _base_mgr("trpg_proj2", 0)

        import time
        with _sessions_lock:
            _sessions["trpg_test_002"] = (mock_session, time.time())

        with patch("narrative_os.interface.api._interactive_agent", mock_agent):
            with patch("narrative_os.interface.api.StateManager", return_value=mgr):
                r = client.post("/sessions/trpg_test_002/end")

        assert r.status_code == 200
        mgr.save_chapter_text.assert_not_called()


# ------------------------------------------------------------------ #
# 综合一致性：项目列表 + 费用摘要 + 风格预设                               #
# ------------------------------------------------------------------ #

class TestMiscEndpoints:
    def test_cost_summary(self, client):
        r = client.get("/cost/summary")
        assert r.status_code == 200

    def test_style_presets(self, client):
        r = client.get("/style/presets")
        assert r.status_code == 200

    def test_consistency_check(self, client):
        """一致性检查端点不报 500。"""
        r = client.post(
            "/chapters/check",
            json={"project_id": "consistency_proj", "chapter_text": "文本内容。"},
        )
        assert r.status_code < 500
