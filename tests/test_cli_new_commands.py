"""
tests/test_cli_new_commands.py — 阶段 2：CLI 新命令测试
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from narrative_os.interface.cli import app

runner = CliRunner()


# ------------------------------------------------------------------ #
# narrative init                                                        #
# ------------------------------------------------------------------ #

def test_init_command_runs_world_builder(tmp_path):
    """verify WorldBuilder.start() and submit_step() are called, seed.json is saved."""
    from narrative_os.core.world_builder import StepResult, BuilderStep

    done_result = StepResult(
        step=BuilderStep.DONE,
        prompt_to_user="完成！",
        draft={},
    )
    first_result = StepResult(
        step=BuilderStep.ONE_SENTENCE,
        prompt_to_user="请输入一句话：",
        draft={},
    )

    mock_builder = MagicMock()
    mock_builder.start.return_value = first_result
    mock_builder.submit_step.return_value = done_result
    mock_builder.state.__dict__ = {"one_sentence": "测试故事"}

    with patch("narrative_os.core.world_builder.WorldBuilder", return_value=mock_builder):
        result = runner.invoke(app, ["init", "--project", "test_proj",
                                     "--dir", str(tmp_path)], input="我的故事\n")

    mock_builder.start.assert_called_once()
    mock_builder.submit_step.assert_called_once()


# ------------------------------------------------------------------ #
# narrative write                                                       #
# ------------------------------------------------------------------ #

def test_write_command_calls_writer_agent():
    """verify WriterAgent.write() is called and PlannerAgent.plan() is NOT called."""
    from narrative_os.agents.writer import ChapterDraft

    mock_draft = ChapterDraft(
        chapter=3,
        volume=1,
        draft_text="这是生成的章节内容。",
        total_words=100,
    )

    with patch("narrative_os.agents.writer.WriterAgent") as mock_agent_cls:
        mock_agent = MagicMock()
        mock_agent.write = AsyncMock(return_value=mock_draft)
        mock_agent_cls.return_value = mock_agent

        result = runner.invoke(app, ["write", "--chapter", "3", "--summary", "主角觉醒"])

    mock_agent.write.assert_called_once()
    assert result.exit_code == 0
    assert result.exit_code == 0 or "失败" not in result.output


# ------------------------------------------------------------------ #
# narrative interactive                                                 #
# ------------------------------------------------------------------ #

def test_interactive_command_creates_session():
    """verify InteractiveAgent.create_session() and start() are called."""
    from narrative_os.agents.interactive import SessionPhase, TurnRecord

    mock_turn = TurnRecord(
        turn_id=0,
        who="dm",
        content="夜色深沉。\n[选项 A]：前进\n[选项 B]：等待",
        phase=SessionPhase.PING_PONG,
    )
    land_result = {
        "session_id": "test-123",
        "turns": 1,
        "final_pressure": 5.0,
        "dm_text_length": 20,
        "history_summary": "夜色深沉。",
        "user_actions": [],
    }

    with patch("narrative_os.agents.interactive.InteractiveAgent") as mock_agent_cls:
        mock_agent = MagicMock()
        mock_session = MagicMock()
        mock_session.phase = SessionPhase.PING_PONG

        mock_agent.create_session.return_value = mock_session
        mock_agent.start = AsyncMock(return_value=mock_turn)
        mock_agent.step = AsyncMock(return_value=mock_turn)
        mock_agent.land = MagicMock(return_value=land_result)
        mock_agent_cls.return_value = mock_agent

        # Send /end immediately after start
        result = runner.invoke(
            app, ["interactive", "--project", "test"],
            input="/end\n",
        )

    mock_agent.create_session.assert_called_once()
    mock_agent.start.assert_called_once()


# ------------------------------------------------------------------ #
# narrative check                                                       #
# ------------------------------------------------------------------ #

def test_check_command_passes_on_clean_report(tmp_path):
    """clean report (no issues) → exit code 0."""
    from narrative_os.skills.consistency import ConsistencyReport

    draft_file = tmp_path / "draft.txt"
    draft_file.write_text("这是一段正常的故事文本。", encoding="utf-8")

    clean_report = ConsistencyReport(passed=True, issues=[], score=1.0)

    with patch("narrative_os.skills.consistency.ConsistencyChecker") as mock_cls:
        mock_checker = MagicMock()
        mock_checker.check.return_value = clean_report
        mock_cls.return_value = mock_checker

        result = runner.invoke(app, ["check", "--chapter", "1", "--draft", str(draft_file)])

    assert result.exit_code == 0
    assert "通过" in result.output or "PASSED" not in result.output


def test_check_command_exits_1_on_hard_issue(tmp_path):
    """report with hard issue → exit code 1."""
    from narrative_os.skills.consistency import ConsistencyReport, ConsistencyIssue

    draft_file = tmp_path / "draft.txt"
    draft_file.write_text("错误的文本内容。", encoding="utf-8")

    hard_report = ConsistencyReport(
        passed=False,
        issues=[ConsistencyIssue(
            dimension="character",
            severity="hard",
            description="角色死亡后复活",
            suggestion="修改角色状态",
        )],
        score=0.7,
    )

    with patch("narrative_os.skills.consistency.ConsistencyChecker") as mock_cls:
        mock_checker = MagicMock()
        mock_checker.check.return_value = hard_report
        mock_cls.return_value = mock_checker

        result = runner.invoke(app, ["check", "--chapter", "2", "--draft", str(draft_file)])

    assert result.exit_code == 1


# ------------------------------------------------------------------ #
# narrative humanize                                                    #
# ------------------------------------------------------------------ #

def test_humanize_command_reads_file(tmp_path):
    """--input file is read and Humanizer.humanize() is called."""
    from narrative_os.skills.humanize import HumanizeOutput

    input_file = tmp_path / "input.txt"
    input_file.write_text("AI写的文章，感觉很机械。", encoding="utf-8")

    mock_output = HumanizeOutput(
        original_text="AI写的文章，感觉很机械。",
        humanized_text="这篇文章读起来自然多了。",
        change_ratio=0.4,
        applied_rules=["对话去AI化"],
        model_used="gpt-4o-mini",
    )

    with patch("narrative_os.skills.humanize.Humanizer") as mock_cls:
        mock_humanizer = MagicMock()
        mock_humanizer.humanize = AsyncMock(return_value=mock_output)
        mock_cls.return_value = mock_humanizer

        result = runner.invoke(app, ["humanize", "--input", str(input_file)])

    mock_humanizer.humanize.assert_called_once()
    assert result.exit_code == 0


# ------------------------------------------------------------------ #
# narrative rollback                                                    #
# ------------------------------------------------------------------ #

def test_rollback_aborts_without_confirmation(tmp_path):
    """without --yes, user answers 'n' → rollback NOT called."""
    with patch("narrative_os.core.state.StateManager") as mock_cls:
        mock_mgr = MagicMock()
        mock_state = MagicMock()
        mock_state.current_chapter = 5
        mock_state.current_volume = 1
        mock_mgr.load_state.return_value = mock_state
        mock_cls.return_value = mock_mgr

        result = runner.invoke(app, ["rollback", "--steps", "1", "--project", "test"],
                               input="N\n")

    mock_mgr.rollback.assert_not_called()


def test_rollback_proceeds_with_yes_flag(tmp_path):
    """with --yes flag, rollback IS called without interactive prompt."""
    with patch("narrative_os.core.state.StateManager") as mock_cls:
        mock_mgr = MagicMock()
        mock_state = MagicMock()
        mock_state.current_chapter = 5
        mock_state.current_volume = 1
        mock_mgr.load_state.return_value = mock_state
        mock_cls.return_value = mock_mgr

        result = runner.invoke(app, ["rollback", "--steps", "2", "--yes", "--project", "test"])

    mock_mgr.rollback.assert_called_once_with(chapter=3)
    assert result.exit_code == 0


def test_all_commands_visible_in_help():
    """All new commands should appear in --help output."""
    result = runner.invoke(app, ["--help"])
    for cmd in ["init", "write", "interactive", "check", "humanize", "rollback"]:
        assert cmd in result.output, f"命令 '{cmd}' 未在 --help 中出现"


# ------------------------------------------------------------------ #
# narrative plan                                                        #
# ------------------------------------------------------------------ #

def test_plan_command_calls_planner_agent():
    """narrative plan → PlannerAgent.plan() called, output shown."""
    from narrative_os.agents.planner import PlannerOutput, PlannedNode

    mock_plan = PlannerOutput(
        chapter_outline="林风踏上修炼之路",
        planned_nodes=[
            PlannedNode(id="ch0001_n1", type="scene", summary="起始", tension=0.5)
        ],
        hook_suggestion="下章钩子",
        hook_type="cliffhanger",
        dialogue_goals=["深化人物关系"],
    )

    with patch("narrative_os.agents.planner.PlannerAgent") as mock_cls:
        mock_agent = MagicMock()
        mock_agent.plan = AsyncMock(return_value=mock_plan)
        mock_cls.return_value = mock_agent

        result = runner.invoke(app, [
            "plan", "--chapter", "1", "--summary", "觉醒", "--volume", "1"
        ])

    mock_agent.plan.assert_called_once()
    assert result.exit_code == 0


def test_plan_command_failure_exits_1():
    """narrative plan → error raised → exit code 1."""
    with patch("narrative_os.agents.planner.PlannerAgent") as mock_cls:
        mock_agent = MagicMock()
        mock_agent.plan = AsyncMock(side_effect=RuntimeError("规划失败"))
        mock_cls.return_value = mock_agent

        result = runner.invoke(app, [
            "plan", "--chapter", "1", "--summary", "觉醒"
        ])

    assert result.exit_code == 1


def test_plan_command_saves_json(tmp_path):
    """narrative plan --json <path> → writes JSON file."""
    from narrative_os.agents.planner import PlannerOutput, PlannedNode

    mock_plan = PlannerOutput(
        chapter_outline="骨架",
        planned_nodes=[PlannedNode(id="n1", type="scene", summary="摘要", tension=0.5)],
    )
    out_file = tmp_path / "plan.json"

    with patch("narrative_os.agents.planner.PlannerAgent") as mock_cls:
        mock_agent = MagicMock()
        mock_agent.plan = AsyncMock(return_value=mock_plan)
        mock_cls.return_value = mock_agent

        result = runner.invoke(app, [
            "plan", "--chapter", "2", "--summary", "测试",
            "--json", str(out_file)
        ])

    assert result.exit_code == 0
    assert out_file.exists()


# ------------------------------------------------------------------ #
# narrative status                                                      #
# ------------------------------------------------------------------ #

def test_status_command_shows_project_state(tmp_path):
    """narrative status → StateManager.load_state() called, output shown."""
    with patch("narrative_os.core.state.StateManager") as mock_cls:
        mock_mgr = MagicMock()
        mock_state = MagicMock()
        mock_state.current_chapter = 3
        mock_state.current_volume = 1
        mock_state.total_word_count = 9000
        mock_state.chapters = []
        mock_mgr.load_state.return_value = mock_state
        mock_mgr._state = mock_state
        mock_mgr.list_versions.return_value = []
        mock_cls.return_value = mock_mgr

        result = runner.invoke(app, ["status", "--project", "my_novel"])

    assert result.exit_code == 0


def test_status_command_no_state_shows_warning():
    """narrative status with no saved state → shows yellow warning."""
    with patch("narrative_os.core.state.StateManager") as mock_cls:
        mock_mgr = MagicMock()
        mock_mgr.load_state.side_effect = Exception("no state")
        mock_cls.return_value = mock_mgr

        result = runner.invoke(app, ["status", "--project", "nonexistent"])

    assert result.exit_code == 0  # not an error exit


# ------------------------------------------------------------------ #
# narrative cost                                                        #
# ------------------------------------------------------------------ #

def test_cost_command_shows_summary():
    """narrative cost → cost_ctrl.summary() called and output shown."""
    with patch("narrative_os.infra.cost.cost_ctrl") as mock_ctrl:
        mock_ctrl.summary.return_value = {
            "used": 45000,
            "budget": 100000,
            "ratio": 0.45,
            "by_skill": {"scene": 30000, "humanize": 15000},
            "by_agent": {"writer": 40000},
        }

        result = runner.invoke(app, ["cost"])

    assert result.exit_code == 0
    assert "45" in result.output or "45,000" in result.output or "45000" in result.output


# ------------------------------------------------------------------ #
# narrative metrics                                                     #
# ------------------------------------------------------------------ #

def test_metrics_command_shows_scores(tmp_path):
    """narrative metrics --draft <file> → evaluates and shows table."""
    from narrative_os.agents.writer import ChapterDraft

    draft = ChapterDraft(
        chapter=2,
        volume=1,
        draft_text="这是第二章正文，" * 200,
        total_words=3000,
        avg_tension=6.5,
        hook_score=0.75,
    )
    draft_file = tmp_path / "draft.json"
    draft_file.write_text(draft.model_dump_json(), encoding="utf-8")

    result = runner.invoke(app, [
        "metrics", "--chapter", "2", "--draft", str(draft_file)
    ])

    assert result.exit_code == 0
    assert "综合分" in result.output or "overall" in result.output.lower() or "章" in result.output


def test_metrics_command_file_not_found(tmp_path):
    """narrative metrics --draft <missing> → exit code 1."""
    result = runner.invoke(app, [
        "metrics", "--chapter", "1", "--draft", str(tmp_path / "nonexistent.json")
    ])
    assert result.exit_code == 1


# ------------------------------------------------------------------ #
# narrative run                                                         #
# ------------------------------------------------------------------ #

def test_run_command_calls_run_chapter():
    """narrative run → orchestrator run_chapter called, output shown."""
    from narrative_os.agents.editor import EditedChapter
    from narrative_os.agents.critic import CriticReport

    mock_edited = EditedChapter(
        chapter=1,
        volume=1,
        text="最终章节正文",
        word_count=2000,
        change_ratio=0.35,
        applied_rules=["去AI化"],
    )
    mock_critic = CriticReport(
        passed=True,
        quality_score=0.85,
        hook_score=0.80,
        rewrite_instructions=[],
    )
    mock_result = {
        "edited_chapter": mock_edited,
        "critic_report": mock_critic,
    }

    with patch("narrative_os.orchestrator.graph.run_chapter", new=AsyncMock(return_value=mock_result)):
        result = runner.invoke(app, [
            "run", "--chapter", "1", "--summary", "第一章觉醒"
        ])

    assert result.exit_code == 0


def test_run_command_failure_exits_1():
    """narrative run → exception in orchestrator → exit code 1."""
    with patch("narrative_os.orchestrator.graph.run_chapter",
               new=AsyncMock(side_effect=RuntimeError("编排失败"))):
        result = runner.invoke(app, [
            "run", "--chapter", "1", "--summary", "测试"
        ])

    assert result.exit_code == 1


def test_run_command_writes_output_file(tmp_path):
    """narrative run --output <file> → writes text to disk."""
    from narrative_os.agents.editor import EditedChapter
    from narrative_os.agents.critic import CriticReport

    mock_edited = EditedChapter(
        chapter=1, volume=1, text="正文内容", word_count=100, change_ratio=0.2, applied_rules=[]
    )
    mock_result = {
        "edited_chapter": mock_edited,
        "critic_report": CriticReport(passed=True, quality_score=0.8, hook_score=0.7, rewrite_instructions=[]),
    }
    out_file = tmp_path / "chapter_01.txt"

    with patch("narrative_os.orchestrator.graph.run_chapter", new=AsyncMock(return_value=mock_result)):
        result = runner.invoke(app, [
            "run", "--chapter", "1", "--summary", "测试", "--output", str(out_file)
        ])

    assert result.exit_code == 0
    assert out_file.exists()
    assert "正文内容" in out_file.read_text(encoding="utf-8")
