"""tests/test_core/test_state.py — StateManager + NarrativeState 单元测试"""
import json

import pytest
from narrative_os.core.state import ChapterMeta, NarrativeState, StateManager


# ------------------------------------------------------------------ #
# Fixtures                                                             #
# ------------------------------------------------------------------ #

@pytest.fixture
def sm(tmp_path) -> StateManager:
    """Isolated StateManager using tmp_path."""
    return StateManager(project_id="test_novel", base_dir=str(tmp_path))


# ------------------------------------------------------------------ #
# Initialization                                                        #
# ------------------------------------------------------------------ #

class TestInit:
    def test_initialize_creates_dir(self, sm: StateManager):
        sm.initialize(project_name="测试小说")
        assert (sm._dir).exists()
        assert (sm._versions_dir).exists()
        assert sm._state_path.exists()

    def test_initialize_returns_state(self, sm: StateManager):
        state = sm.initialize(project_name="测试小说")
        assert isinstance(state, NarrativeState)
        assert state.project_name == "测试小说"
        assert state.current_chapter == 0

    def test_double_initialize_loads_existing(self, sm: StateManager, tmp_path):
        sm.initialize(project_name="测试小说")
        # Second manager pointing at same dir
        sm2 = StateManager(project_id="test_novel", base_dir=str(tmp_path))
        state2 = sm2.initialize(project_name="覆盖名")
        assert state2.project_name == "测试小说"  # loaded old state, name unchanged

    def test_force_reinitialize(self, sm: StateManager, tmp_path):
        sm.initialize(project_name="旧名")
        sm2 = StateManager(project_id="test_novel", base_dir=str(tmp_path))
        state2 = sm2.initialize(project_name="新名", force=True)
        assert state2.project_name == "新名"

    def test_load_missing_state_raises(self, sm: StateManager):
        with pytest.raises(FileNotFoundError):
            sm.load_state()


# ------------------------------------------------------------------ #
# Save / Load                                                           #
# ------------------------------------------------------------------ #

class TestSaveLoad:
    def test_save_and_reload(self, sm: StateManager, tmp_path):
        sm.initialize(project_name="持久化测试")
        sm.state.current_step = "planning"
        sm.save_state()

        sm2 = StateManager(project_id="test_novel", base_dir=str(tmp_path))
        loaded = sm2.load_state()
        assert loaded.current_step == "planning"


# ------------------------------------------------------------------ #
# Chapter Versioning                                                    #
# ------------------------------------------------------------------ #

class TestVersioning:
    def test_commit_chapter_creates_file(self, sm: StateManager):
        sm.initialize()
        path = sm.commit_chapter(
            chapter=1,
            plot_graph_dict={"nodes": []},
            characters_dict={"hero": {"name": "林风"}},
            world_dict={"factions": []},
        )
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["version"] == 1

    def test_list_versions(self, sm: StateManager):
        sm.initialize()
        sm.commit_chapter(1)
        sm.commit_chapter(2)
        sm.commit_chapter(5)
        assert sm.list_versions() == [1, 2, 5]

    def test_rollback_restores_data(self, sm: StateManager):
        sm.initialize()
        sm.commit_chapter(1, plot_graph_dict={"snap": "chapter1"})
        sm.commit_chapter(2, plot_graph_dict={"snap": "chapter2"})

        snapshot = sm.rollback(1)
        assert snapshot["plot_graph"]["snap"] == "chapter1"
        assert sm.state.current_chapter == 1

    def test_rollback_missing_raises(self, sm: StateManager):
        sm.initialize()
        with pytest.raises(FileNotFoundError):
            sm.rollback(999)

    def test_commit_with_meta(self, sm: StateManager):
        sm.initialize()
        meta = ChapterMeta(chapter=1, summary="林风出场", quality_score=0.85, word_count=3000)
        sm.commit_chapter(1, chapter_meta=meta)
        assert len(sm.state.chapters) == 1
        assert sm.state.chapters[0].quality_score == pytest.approx(0.85)


# ------------------------------------------------------------------ #
# Human-in-the-Loop                                                    #
# ------------------------------------------------------------------ #

class TestHITL:
    def test_request_and_approve(self, sm: StateManager):
        sm.initialize()
        sm.request_approval({"message": "请确认继续"})
        assert sm.is_pending_approval()

        sm.approve("planning_done")
        assert not sm.is_pending_approval()
        assert sm.state.last_confirmed_step == "planning_done"

    def test_approval_context_cleared_after_approve(self, sm: StateManager):
        sm.initialize()
        sm.request_approval({"key": "val"})
        sm.approve("step1")
        assert sm.state.approval_context == {}


# ------------------------------------------------------------------ #
# Knowledge Base                                                        #
# ------------------------------------------------------------------ #

class TestKnowledgeBase:
    def test_save_and_load_kb(self, sm: StateManager):
        sm.initialize()
        kb = {"characters": {"hero": "林风"}, "world_rules": ["不能飞行"]}
        sm.save_kb(kb)
        loaded = sm.load_kb()
        assert loaded["characters"]["hero"] == "林风"

    def test_load_missing_kb_returns_empty(self, sm: StateManager):
        sm.initialize()
        assert sm.load_kb() == {}


# ------------------------------------------------------------------ #
# Path helpers + repr                                                   #
# ------------------------------------------------------------------ #

class TestPathHelpers:
    def test_chapter_path(self, sm: StateManager):
        p = sm.chapter_path(3)
        assert "chapter_0003.md" in str(p)

    def test_outline_path(self, sm: StateManager):
        p = sm.outline_path("main_arc")
        assert "main_arc.md" in str(p)

    def test_scene_path(self, sm: StateManager):
        p = sm.scene_path("arc1", 5)
        assert "chapter_0005.md" in str(p)

    def test_repr_before_init(self, sm: StateManager):
        r = repr(sm)
        assert "StateManager" in r
        assert "?" in r  # no state yet

    def test_repr_after_init(self, sm: StateManager):
        sm.initialize()
        r = repr(sm)
        assert "StateManager" in r
        assert "test_novel" in r
