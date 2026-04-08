"""
tests/test_chapter_persistence.py — Phase 3: 章节持久化测试

覆盖：
  StateManager.save_chapter_text / load_chapter_text / list_chapter_files
  GET  /projects/{id}/chapters
  GET  /projects/{id}/chapters/{n}
  GET  /projects/{id}/export
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from narrative_os.interface.api import app
from narrative_os.core.state import ChapterMeta, NarrativeState, StateManager


# ------------------------------------------------------------------ #
# 固定装置                                                              #
# ------------------------------------------------------------------ #

@pytest.fixture()
def client():
    return TestClient(app, raise_server_exceptions=False)


def _make_mgr(chapter_files: list[int] | None = None, text: str | None = None):
    """构造带章节方法的 StateManager mock。"""
    mgr = MagicMock(spec=StateManager)
    state = NarrativeState(project_id="p1", project_name="Test")
    state.current_chapter = max(chapter_files or [0]) if chapter_files else 0
    state.chapters = [
        ChapterMeta(
            chapter=n,
            summary=f"第{n}章摘要",
            quality_score=0.8,
            hook_score=0.7,
            word_count=2000,
        )
        for n in (chapter_files or [])
    ]
    mgr.state = state
    mgr.load_state.return_value = state
    mgr.load_kb.return_value = {}
    mgr.list_chapter_files.return_value = sorted(chapter_files or [])
    mgr.load_chapter_text.return_value = text
    return mgr


# ------------------------------------------------------------------ #
# StateManager 单元测试（使用临时目录）                                   #
# ------------------------------------------------------------------ #

def test_save_and_load_chapter_text(tmp_path):
    """save_chapter_text 写入文件，load_chapter_text 读取回来。"""
    mgr = StateManager(project_id="unit_test", base_dir=str(tmp_path))
    mgr.initialize(project_name="unit_test")

    mgr.save_chapter_text(1, "第一章正文内容。")
    loaded = mgr.load_chapter_text(1)
    assert loaded == "第一章正文内容。"


def test_load_chapter_text_missing(tmp_path):
    """load_chapter_text 不存在时返回 None。"""
    mgr = StateManager(project_id="unit_test2", base_dir=str(tmp_path))
    mgr.initialize(project_name="unit_test2")
    result = mgr.load_chapter_text(99)
    assert result is None


def test_list_chapter_files(tmp_path):
    """list_chapter_files 返回已保存章节的有序列表。"""
    mgr = StateManager(project_id="unit_test3", base_dir=str(tmp_path))
    mgr.initialize(project_name="unit_test3")

    mgr.save_chapter_text(3, "ch3")
    mgr.save_chapter_text(1, "ch1")
    mgr.save_chapter_text(2, "ch2")

    result = mgr.list_chapter_files()
    assert result == [1, 2, 3]


# ------------------------------------------------------------------ #
# GET /projects/{id}/chapters                                          #
# ------------------------------------------------------------------ #

def test_list_chapters_ok(client):
    """正常列出章节列表。"""
    mgr = _make_mgr(chapter_files=[1, 2, 3])
    with patch("narrative_os.interface.api._load_project_or_404", return_value=mgr):
        r = client.get("/projects/p1/chapters")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 3
    assert data[0]["chapter"] == 1


def test_list_chapters_empty(client):
    """无章节时返回空列表。"""
    mgr = _make_mgr(chapter_files=[])
    with patch("narrative_os.interface.api._load_project_or_404", return_value=mgr):
        r = client.get("/projects/p1/chapters")
    assert r.status_code == 200
    assert r.json() == []


# ------------------------------------------------------------------ #
# GET /projects/{id}/chapters/{chapter_num}                            #
# ------------------------------------------------------------------ #

def test_get_chapter_text_ok(client):
    """正常读取章节全文。"""
    mgr = _make_mgr(chapter_files=[1], text="第一章内容。")
    with patch("narrative_os.interface.api._load_project_or_404", return_value=mgr):
        r = client.get("/projects/p1/chapters/1")
    assert r.status_code == 200
    body = r.json()
    assert body["chapter"] == 1
    assert body["text"] == "第一章内容。"


def test_get_chapter_text_not_found(client):
    """章节不存在时返回 404。"""
    mgr = _make_mgr(chapter_files=[], text=None)
    with patch("narrative_os.interface.api._load_project_or_404", return_value=mgr):
        r = client.get("/projects/p1/chapters/99")
    assert r.status_code == 404


# ------------------------------------------------------------------ #
# GET /projects/{id}/export                                            #
# ------------------------------------------------------------------ #

def test_export_novel_ok(client):
    """正常导出，返回章节数和总字数。"""
    mgr = _make_mgr(chapter_files=[1, 2], text="五千字内容。")
    with patch("narrative_os.interface.api._load_project_or_404", return_value=mgr):
        r = client.get("/projects/p1/export")
    assert r.status_code == 200
    body = r.json()
    assert body["project_id"] == "p1"
    assert body["chapter_count"] == 2


def test_export_novel_empty(client):
    """无章节时返回 404（无章节视为 not found）。"""
    mgr = _make_mgr(chapter_files=[], text=None)
    mgr.load_chapter_text.return_value = None
    with patch("narrative_os.interface.api._load_project_or_404", return_value=mgr):
        r = client.get("/projects/p1/export")
    assert r.status_code == 404
