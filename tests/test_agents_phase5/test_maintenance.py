"""tests/test_agents_phase5/test_maintenance.py — MaintenanceAgent 测试组。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from narrative_os.agents.critic import CriticReport
from narrative_os.agents.maintenance import (
    MaintenanceAgent,
    MaintenanceInput,
    MaintenanceOutput,
    _ARC_ORDER,
)
from narrative_os.agents.planner import PlannerOutput
from narrative_os.agents.writer import ChapterDraft
from narrative_os.core.character import ArcStage, CharacterDrive, CharacterState
from narrative_os.core.evolution import ChangeTag, get_canon_commit
from narrative_os.core.plot import NodeType, PlotGraph
from narrative_os.core.state import StateManager
from narrative_os.skills.consistency import ConsistencyIssue, ConsistencyReport


# ------------------------------------------------------------------ #
# Fixtures                                                              #
# ------------------------------------------------------------------ #

@pytest.fixture
def agent() -> MaintenanceAgent:
    return MaintenanceAgent()


def _make_draft(chapter: int = 3, text: str = "") -> ChapterDraft:
    return ChapterDraft(
        chapter=chapter,
        draft_text=text or f"第{chapter}章文本，主角击败了反派，完成了核心任务。情节推进顺利。下一章将面临更大危机。",
        total_words=50,
    )


def _make_char(name: str, arc_stage: str = ArcStage.DEFENSIVE) -> CharacterState:
    return CharacterState(name=name, arc_stage=arc_stage)


def _make_critic(character_issue_names: list[str] | None = None) -> CriticReport:
    issues = []
    if character_issue_names:
        for n in character_issue_names:
            issues.append(ConsistencyIssue(
                dimension="character",
                severity="hard",
                description=f"角色{n}行为不符合约束",
            ))
    cr = ConsistencyReport(passed=not issues, issues=issues)
    return CriticReport(passed=not issues, consistency_report=cr)


# ------------------------------------------------------------------ #
# MaintenanceOutput 模型                                               #
# ------------------------------------------------------------------ #

class TestMaintenanceOutputModel:
    def test_defaults(self):
        out = MaintenanceOutput(chapter=1)
        assert out.completed_nodes == []
        assert out.warnings == []
        assert out.memory_summary == ""
        assert out.next_hook == ""


# ------------------------------------------------------------------ #
# _update_arcs                                                          #
# ------------------------------------------------------------------ #

class TestUpdateArcs:
    def test_advances_arc_one_stage(self, agent):
        ch = _make_char("林枫", ArcStage.DEFENSIVE)
        inp = MaintenanceInput(chapter_draft=_make_draft(), characters=[ch])
        out = agent.maintain(inp)
        updated = {c.name: c.arc_stage for c in out.updated_characters}
        assert updated["林枫"] == ArcStage.CRACKING

    def test_blocked_by_character_issue(self, agent):
        ch = _make_char("林枫", ArcStage.DEFENSIVE)
        critic = _make_critic(character_issue_names=["林枫"])
        inp = MaintenanceInput(chapter_draft=_make_draft(), characters=[ch], critic_report=critic)
        out = agent.maintain(inp)
        # arc should NOT advance
        assert out.updated_characters[0].arc_stage == ArcStage.DEFENSIVE
        assert any("林枫" in w for w in out.warnings)

    def test_no_advance_when_false(self, agent):
        ch = _make_char("林枫", ArcStage.DEFENSIVE)
        inp = MaintenanceInput(chapter_draft=_make_draft(), characters=[ch], advance_arcs=False)
        out = agent.maintain(inp)
        assert out.updated_characters[0].arc_stage == ArcStage.DEFENSIVE

    def test_transformed_stays_at_end(self, agent):
        ch = _make_char("林枫", ArcStage.TRANSFORMED)
        inp = MaintenanceInput(chapter_draft=_make_draft(), characters=[ch])
        out = agent.maintain(inp)
        assert out.updated_characters[0].arc_stage == ArcStage.TRANSFORMED

    def test_multiple_characters_partial_block(self, agent):
        ch1 = _make_char("林枫", ArcStage.DEFENSIVE)
        ch2 = _make_char("陈伟", ArcStage.CRACKING)
        critic = _make_critic(character_issue_names=["陈伟"])
        inp = MaintenanceInput(
            chapter_draft=_make_draft(),
            characters=[ch1, ch2],
            critic_report=critic,
        )
        out = agent.maintain(inp)
        stages = {c.name: c.arc_stage for c in out.updated_characters}
        assert stages["林枫"] == ArcStage.CRACKING   # advanced
        assert stages["陈伟"] == ArcStage.CRACKING   # blocked

    def test_no_characters_returns_empty(self, agent):
        inp = MaintenanceInput(chapter_draft=_make_draft(), characters=[])
        out = agent.maintain(inp)
        assert out.updated_characters == []


# ------------------------------------------------------------------ #
# _mark_completed_nodes                                                 #
# ------------------------------------------------------------------ #

class TestMarkCompletedNodes:
    def test_marks_chapter_nodes(self, agent):
        graph = PlotGraph()
        graph.create_event("ch3_01", type=NodeType.CONFLICT, summary="冲突")
        graph.create_event("ch3_02", type=NodeType.CLIMAX, summary="高潮")
        graph.create_event("ch4_01", type=NodeType.SETUP, summary="其他章")

        inp = MaintenanceInput(chapter_draft=_make_draft(chapter=3))
        out = agent.maintain(inp, plot_graph=graph)

        assert "ch3_01" in out.completed_nodes
        assert "ch3_02" in out.completed_nodes
        assert "ch4_01" not in out.completed_nodes

    def test_no_graph_returns_empty(self, agent):
        inp = MaintenanceInput(chapter_draft=_make_draft())
        out = agent.maintain(inp, plot_graph=None)
        assert out.completed_nodes == []

    def test_no_nodes_for_chapter(self, agent):
        graph = PlotGraph()
        graph.create_event("ch5_01", type=NodeType.SETUP, summary="另一章")
        inp = MaintenanceInput(chapter_draft=_make_draft(chapter=3))
        out = agent.maintain(inp, plot_graph=graph)
        assert out.completed_nodes == []


# ------------------------------------------------------------------ #
# _extract_next_hook                                                    #
# ------------------------------------------------------------------ #

class TestExtractNextHook:
    def test_extracts_last_60_chars(self, agent):
        long_text = "A" * 100 + "末尾钩子内容在这里出现了，非常重要的剧情转折啊。"
        inp = MaintenanceInput(chapter_draft=_make_draft(text=long_text))
        out = agent.maintain(inp)
        assert "末尾钩子" in out.next_hook or len(out.next_hook) == 60

    def test_short_text_returns_full(self, agent):
        short = "短文本结束"
        inp = MaintenanceInput(chapter_draft=_make_draft(text=short))
        out = agent.maintain(inp)
        assert out.next_hook == short

    def test_empty_draft_returns_empty_hook(self, agent):
        draft = ChapterDraft(chapter=3, draft_text="", total_words=0)
        inp = MaintenanceInput(chapter_draft=draft)
        out = agent.maintain(inp)
        assert out.next_hook == ""


# ------------------------------------------------------------------ #
# _compress_memory                                                      #
# ------------------------------------------------------------------ #

class TestCompressMemory:
    def test_writes_to_mid_layer(self, agent):
        memory = MagicMock()
        memory.write_memory.return_value = MagicMock()
        inp = MaintenanceInput(chapter_draft=_make_draft(chapter=3))
        out = agent.maintain(inp, memory=memory)

        memory.write_memory.assert_called_once()
        call_kwargs = memory.write_memory.call_args
        assert call_kwargs.kwargs.get("layer") == "mid"
        assert "第3章" in out.memory_summary

    def test_no_memory_returns_empty(self, agent):
        inp = MaintenanceInput(chapter_draft=_make_draft())
        out = agent.maintain(inp, memory=None)
        assert out.memory_summary == ""

    def test_memory_failure_adds_warning(self, agent):
        memory = MagicMock()
        memory.write_memory.side_effect = RuntimeError("DB 不可用")
        inp = MaintenanceInput(chapter_draft=_make_draft())
        out = agent.maintain(inp, memory=memory)
        assert any("记忆" in w for w in out.warnings)
        assert out.memory_summary == ""


class TestStage5Writeback:
    def test_creates_pending_changeset_and_persists_hook(self, agent, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        memory = MagicMock()
        memory.write_memory.return_value = MagicMock()
        memory.write_anchor.return_value = {
            "chapter": 3,
            "key_pivot": "主角完成关键突破",
            "burning_question": "敌人下一步会如何反击",
            "next_chapter_debt": "追查幕后真相",
        }

        character = CharacterState(
            name="林枫",
            drive=CharacterDrive(core_desire="变强", core_fear="失去同伴"),
        )
        graph = PlotGraph()
        graph.create_event("ch3_01", type=NodeType.CONFLICT, summary="突破困局")
        graph.create_event("ch4_01", type=NodeType.SETUP, summary="追查幕后")
        graph.link_events("ch3_01", "ch4_01")

        inp = MaintenanceInput(
            project_id="stage5_proj",
            chapter_draft=_make_draft(chapter=3),
            planner_output=PlannerOutput(
                chapter_outline="主角完成突破",
                planned_nodes=[],
                edge_pairs=[],
                hook_suggestion="追查幕后",
            ),
            characters=[character],
        )

        out = agent.maintain(inp, plot_graph=graph, memory=memory)

        assert out.changeset_id is not None
        assert out.memory_anchor != ""
        assert out.next_hook != ""
        assert "ch4_01" in out.activated_nodes

        state_mgr = StateManager(project_id="stage5_proj", base_dir=".narrative_state")
        state_mgr.load_state()
        assert state_mgr.get_last_hook(3) == out.next_hook

        changesets = get_canon_commit("stage5_proj").list_changesets("stage5_proj")
        assert changesets[-1].changes[0].tag == ChangeTag.CANON_PENDING
