"""
interface/cli.py — Phase 4: Typer CLI

用法示例：
    narrative run --chapter 3 --summary "主角觉醒"
    narrative plan --chapter 3 --summary "主角觉醒"
    narrative status --project my-novel
    narrative cost
    narrative metrics --chapter 3

命令组：
  run       完整章节生成（Planner→Writer→Critic→Editor→Memory）
  plan      仅执行 Planner，输出结构化骨架（不生成正文）
  status    查看项目状态（chapters committed, token usage等）
  cost      查看今日 token 消耗
  metrics   读取已有草稿并输出叙事指标
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from narrative_os.schemas.characters import CharacterRuntimeUpdateRequest
from narrative_os.schemas.trpg import SaveRequest

app = typer.Typer(
    name="narrative",
    help="Narrative OS — 可编程叙事操作系统 CLI",
    no_args_is_help=True,
)
console = Console()


# ------------------------------------------------------------------ #
# 工具函数                                                              #
# ------------------------------------------------------------------ #

def _run_async(coro):
    """在同步 CLI 中运行 async 协程。"""
    return asyncio.get_event_loop().run_until_complete(coro)


def _print_success(msg: str) -> None:
    console.print(f"[bold green]✓[/bold green] {msg}")


def _print_error(msg: str) -> None:
    console.print(f"[bold red]✗[/bold red] {msg}", file=sys.stderr)


# ------------------------------------------------------------------ #
# narrative run                                                         #
# ------------------------------------------------------------------ #

@app.command("run")
def run_chapter(
    chapter: int = typer.Option(..., "--chapter", "-c", help="章节号"),
    summary: str = typer.Option(..., "--summary", "-s", help="本章定位（一句话）"),
    volume: int = typer.Option(1, "--volume", "-v", help="卷号"),
    words: int = typer.Option(2000, "--words", "-w", help="目标字数"),
    strategy: str = typer.Option("QUALITY_FIRST", "--strategy",
                                  help="QUALITY_FIRST | COST_OPTIMIZED | SPEED_FIRST"),
    hook: str = typer.Option("", "--hook", help="上章结尾钩子"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="将最终章节写入文件"),
    project: str = typer.Option("default", "--project", "-p", help="项目 ID"),
) -> None:
    """完整生成一章：Planner → Writer → Critic → Editor → Memory。"""
    from narrative_os.orchestrator.graph import run_chapter as _run

    console.print(Panel(
        f"[bold]卷{volume} 第{chapter}章[/bold]\n{summary}",
        title="Narrative OS — 开始生成",
        border_style="blue",
    ))

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        task = progress.add_task("正在生成章节...", total=None)
        try:
            result = _run_async(_run(
                chapter=chapter,
                volume=volume,
                target_summary=summary,
                word_count_target=words,
                strategy=strategy,
                previous_hook=hook,
                project_id=project,
                thread_id=f"{project}-ch{chapter:04d}",
            ))
            progress.update(task, description="生成完成 ✓")
        except Exception as exc:
            _print_error(f"生成失败：{exc}")
            raise typer.Exit(code=1)

    edited = result.get("edited_chapter")
    if edited is None:
        _print_error("未能生成最终章节。")
        raise typer.Exit(code=1)

    # 显示摘要
    critic = result.get("critic_report")
    _show_chapter_summary(chapter, volume, edited.word_count, edited.change_ratio, critic)

    # 写文件
    if output:
        output.write_text(edited.text, encoding="utf-8")
        _print_success(f"已写入 {output}")
    else:
        console.rule("[dim]章节正文[/dim]")
        console.print(edited.text)


# ------------------------------------------------------------------ #
# narrative plan                                                        #
# ------------------------------------------------------------------ #

@app.command("plan")
def plan_chapter(
    chapter: int = typer.Option(..., "--chapter", "-c", help="章节号"),
    summary: str = typer.Option(..., "--summary", "-s", help="本章定位"),
    volume: int = typer.Option(1, "--volume", "-v", help="卷号"),
    words: int = typer.Option(2000, "--words", "-w", help="目标字数"),
    hook: str = typer.Option("", "--hook", help="上章钩子"),
    output_json: Optional[Path] = typer.Option(None, "--json", help="将规划输出为 JSON 文件"),
) -> None:
    """仅生成章节剧情骨架（不写正文）。"""
    from narrative_os.agents.planner import PlannerAgent, PlannerInput

    agent = PlannerAgent()
    inp = PlannerInput(
        chapter=chapter, volume=volume, target_summary=summary,
        word_count_target=words, previous_hook=hook,
    )

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                  transient=True) as progress:
        t = progress.add_task("正在规划剧情...", total=None)
        try:
            plan = _run_async(agent.plan(inp))
            progress.update(t, description="规划完成 ✓")
        except Exception as exc:
            _print_error(f"规划失败：{exc}")
            raise typer.Exit(code=1)

    # 展示大纲
    console.print(Panel(plan.chapter_outline or "（无大纲）",
                        title=f"第{chapter}章剧情骨架", border_style="cyan"))

    # 展示节点表格
    table = Table("节点ID", "类型", "摘要", "张力", title="情节节点")
    for n in plan.planned_nodes:
        table.add_row(n.id, n.type, n.summary, f"{n.tension:.2f}")
    console.print(table)

    if plan.dialogue_goals:
        console.print("[bold]对话目标：[/bold]")
        for g in plan.dialogue_goals:
            console.print(f"  • {g}")

    if plan.hook_suggestion:
        console.print(f"[bold]结尾钩子：[/bold]{plan.hook_suggestion} [{plan.hook_type}]")

    if output_json:
        output_json.write_text(plan.model_dump_json(indent=2), encoding="utf-8")
        _print_success(f"已写入 {output_json}")


# ------------------------------------------------------------------ #
# narrative status                                                      #
# ------------------------------------------------------------------ #

@app.command("status")
def show_status(
    project: str = typer.Option("default", "--project", "-p", help="项目 ID"),
    base_dir: Optional[Path] = typer.Option(None, "--dir", help="项目目录（default: .narrative_state）"),
) -> None:
    """查看项目章节提交历史与状态。"""
    from narrative_os.core.state import StateManager
    from narrative_os.infra.config import settings

    dir_ = str(base_dir) if base_dir else ".narrative_state"
    mgr = StateManager(project_id=project, base_dir=dir_)
    try:
        mgr.load_state()
    except Exception:
        console.print(f"[yellow]项目 '{project}' 尚无已保存状态。[/yellow]")
        return

    state = mgr._state  # type: ignore[attr-defined]
    console.print(Panel(
        f"项目：{project}\n"
        f"当前章节：第{state.current_chapter}章 卷{state.current_volume}\n"
        f"总词数：{state.total_word_count:,}",
        title="项目状态", border_style="green",
    ))

    versions = mgr.list_versions()
    if versions:
        table = Table("章节", "时间", title="已提交版本")
        for v in versions:
            table.add_row(str(v.get("chapter", "?")), str(v.get("ts", "?")))
        console.print(table)
    else:
        console.print("[dim]暂无已提交章节。[/dim]")


# ------------------------------------------------------------------ #
# narrative cost                                                        #
# ------------------------------------------------------------------ #

@app.command("cost")
def show_cost() -> None:
    """显示今日 token 消耗统计。"""
    from narrative_os.infra.cost import cost_ctrl

    try:
        report = cost_ctrl.summary()
    except Exception as exc:
        _print_error(f"无法读取成本数据：{exc}")
        raise typer.Exit(code=1)

    by_skill = report.get("by_skill", {})
    table = Table("Skill / Agent", "总 Tokens", title="今日 Token 消耗（按 Skill）")
    for name, total_tok in by_skill.items():
        table.add_row(name, str(total_tok))

    total = report.get("used", 0)
    budget = report.get("budget", 0)
    used_pct = f"{report.get('ratio', 0) * 100:.1f}%"

    console.print(table)
    console.print(
        f"\n今日总计：[bold]{total:,}[/bold] tokens"
        f"  |  预算：{budget:,}  |  已用：{used_pct}"
    )


# ------------------------------------------------------------------ #
# narrative metrics                                                     #
# ------------------------------------------------------------------ #

@app.command("metrics")
def show_metrics(
    chapter: int = typer.Option(..., "--chapter", "-c", help="章节号"),
    draft_path: Path = typer.Option(..., "--draft", "-d",
                                     help="ChapterDraft JSON 文件路径"),
) -> None:
    """读取草稿 JSON，输出叙事质量指标。"""
    from narrative_os.agents.writer import ChapterDraft
    from narrative_os.skills.metrics import NarrativeMetricsCalc

    if not draft_path.exists():
        _print_error(f"找不到文件：{draft_path}")
        raise typer.Exit(code=1)

    raw = draft_path.read_text(encoding="utf-8")
    try:
        draft = ChapterDraft.model_validate_json(raw)
    except Exception as exc:
        _print_error(f"解析 ChapterDraft 失败：{exc}")
        raise typer.Exit(code=1)

    calc = NarrativeMetricsCalc()
    ch_metrics = calc.evaluate_chapter(draft, word_count_target=2000)

    table = Table("指标", "值", title=f"第{chapter}章叙事指标")
    table.add_row("综合分",     f"{ch_metrics.overall_score:.3f}")
    table.add_row("平均张力",   f"{ch_metrics.avg_tension:.3f}")
    table.add_row("钩子强度",   f"{ch_metrics.hook_score:.3f}")
    table.add_row("爽点密度",   f"{ch_metrics.payoff_density:.3f}")
    table.add_row("节奏分",     f"{ch_metrics.pacing_score:.3f}")
    table.add_row("张力趋势",   ch_metrics.tension_trend)
    table.add_row("一致性分",   f"{ch_metrics.consistency_score:.3f}")
    table.add_row("字效分",     f"{ch_metrics.word_efficiency:.3f}")

    console.print(table)


# ------------------------------------------------------------------ #
# narrative init                                                        #
# ------------------------------------------------------------------ #

@app.command("init")
def init_project(
    project: str = typer.Option("default", "--project", "-p", help="项目 ID"),
    dir_: Optional[Path] = typer.Option(None, "--dir", help="项目目录"),
) -> None:
    """交互式引导创建新项目（WorldBuilder 六步法）。"""
    import json as _json
    from narrative_os.core.world_builder import WorldBuilder, BuilderStep
    from narrative_os.infra.config import settings

    builder = WorldBuilder()
    step_result = builder.start()

    console.print(Panel("欢迎使用 Narrative OS 项目初始化向导", border_style="cyan"))

    while step_result.step != BuilderStep.DONE:
        console.print(f"\n[bold cyan]【{step_result.step.value}】[/bold cyan] {step_result.prompt_to_user}")
        if step_result.draft:
            console.print(f"[dim]草稿：{step_result.draft}[/dim]")
        try:
            user_input = typer.prompt("你的回答（回车跳过）", default="")
        except (typer.Abort, KeyboardInterrupt):
            console.print("\n[yellow]已取消初始化。[/yellow]")
            raise typer.Exit()
        step_result = builder.submit_step(user_input)

    # 保存 seed.json
    seed = builder.get_seed_data() if hasattr(builder, "get_seed_data") else builder.state.__dict__.copy()
    state_base = Path(str(dir_) if dir_ else settings.state_dir)
    seed_dir = state_base / project
    seed_dir.mkdir(parents=True, exist_ok=True)
    seed_path = seed_dir / "seed.json"
    seed_path.write_text(_json.dumps(seed, ensure_ascii=False, indent=2), encoding="utf-8")

    summary_table = Table("字段", "值", title="项目初始化摘要")
    for k, v in list(seed.items())[:8]:
        summary_table.add_row(str(k), str(v)[:60])
    console.print(summary_table)
    _print_success(f"种子数据已保存至 {seed_path}")


# ------------------------------------------------------------------ #
# narrative write                                                       #
# ------------------------------------------------------------------ #

@app.command("write")
def write_chapter(
    chapter: int = typer.Option(..., "--chapter", "-c", help="章节号"),
    summary: str = typer.Option(..., "--summary", "-s", help="本章定位"),
    volume: int = typer.Option(1, "--volume", "-v", help="卷号"),
    words: int = typer.Option(2000, "--words", "-w", help="目标字数"),
    project: str = typer.Option("default", "--project", "-p", help="项目 ID"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="输出文件"),
) -> None:
    """直接生成章节草稿（跳过 Planner，快速写作模式）。"""
    from narrative_os.agents.planner import PlannerOutput, PlannedNode
    from narrative_os.agents.writer import WriterAgent
    from narrative_os.execution.context_builder import WriteContext, ChapterTarget

    # 构造最小化 PlannerOutput（单节点，不调用 PlannerAgent）
    minimal_plan = PlannerOutput(
        chapter_outline=summary,
        planned_nodes=[
            PlannedNode(
                id=f"ch{chapter:04d}_n1",
                type="scene",
                summary=summary,
                tension=0.6,
            )
        ],
        hook_suggestion="",
    )
    ctx = WriteContext(
        chapter_target=ChapterTarget(
            chapter=chapter,
            volume=volume,
            word_count_target=words,
            target_summary=summary,
        )
    )

    agent = WriterAgent()
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                  transient=True) as progress:
        t = progress.add_task("正在生成章节草稿...", total=None)
        try:
            draft = _run_async(agent.write(minimal_plan, ctx))
            progress.update(t, description="草稿生成完成 ✓")
        except Exception as exc:
            _print_error(f"写作失败：{exc}")
            raise typer.Exit(code=1)

    if output:
        output.write_text(draft.draft_text, encoding="utf-8")
        _print_success(f"草稿已写入 {output}（{draft.total_words:,} 字）")
    else:
        console.rule("[dim]章节草稿[/dim]")
        console.print(draft.draft_text)
        console.print(f"\n[dim]字数：{draft.total_words:,}[/dim]")


# ------------------------------------------------------------------ #
# narrative interactive                                                 #
# ------------------------------------------------------------------ #

@app.command("interactive")
def run_interactive(
    project: str = typer.Option("default", "--project", "-p", help="项目 ID"),
    session_id: Optional[str] = typer.Option(None, "--session", help="恢复会话 ID"),
    density: str = typer.Option("normal", "--density",
                                 help="决策密度 dense|normal|sparse"),
    opening: str = typer.Option("", "--opening", help="开场白提示"),
) -> None:
    """启动 TRPG 互动模式（终端界面）。"""
    import time as _time
    from narrative_os.agents.interactive import (
        InteractiveAgent, SessionConfig, SessionPhase,
    )

    if density not in {"dense", "normal", "sparse"}:
        _print_error(f"density 必须为 dense|normal|sparse，当前：{density}")
        raise typer.Exit(code=1)

    agent = InteractiveAgent()
    cfg = SessionConfig(
        project_id=project,
        opening_prompt=opening or "一段未知的旅途即将开始。",
        density_override=density,  # type: ignore[arg-type]
    )
    session = agent.create_session(cfg)

    console.print(Panel(
        f"项目：{project}  |  密度：{density}\n"
        "输入 [bold]/rollback[/bold] 回滚  |  [bold]/bangui <指令>[/bold] 帮回  "
        "|  [bold]/end[/bold] 结束",
        title="Narrative OS — TRPG 互动模式",
        border_style="magenta",
    ))

    async def _run():
        turn = await agent.start(session)
        # 打字机效果输出
        for ch in turn.content:
            console.print(ch, end="", highlight=False)
            _time.sleep(0.02)
        console.print()
        if turn.decision and turn.decision.options:
            for i, opt in enumerate(turn.decision.options, start=ord("A")):
                console.print(f"  [bold cyan][选项 {chr(i)}][/bold cyan]：{opt}")
        console.print()

        while session.phase not in {SessionPhase.ENDED, SessionPhase.LANDING}:
            try:
                user_input = typer.prompt("你的行动")
            except (typer.Abort, EOFError, KeyboardInterrupt):
                user_input = "/end"

            if user_input.startswith("/rollback"):
                session_after = agent.rollback(session, steps=1)
                console.print("[yellow]已回滚一步。[/yellow]")
                continue
            elif user_input.startswith("/bangui"):
                parts = user_input.split(maxsplit=1)
                cmd = parts[1] if len(parts) > 1 else "帮回主动1"
                turn = await agent.interrupt(session, cmd)
            elif user_input.strip() in {"/end", "/quit", "/q"}:
                break
            else:
                turn = await agent.step(session, user_input)

            for ch in turn.content:
                console.print(ch, end="", highlight=False)
                _time.sleep(0.02)
            console.print()
            if turn.decision and turn.decision.options:
                for i, opt in enumerate(turn.decision.options, start=ord("A")):
                    console.print(f"  [bold cyan][选项 {chr(i)}][/bold cyan]：{opt}")
            console.print()

            if session.phase == SessionPhase.PACING_ALERT:
                console.print("[bold yellow]⚠ 节奏警报 — 剧情即将收尾[/bold yellow]")

        summary = agent.land(session)
        console.print(Panel(
            f"会话结束 | 共 {summary['turns']} 轮 | "
            f"最终压力 {summary['final_pressure']:.1f}/10",
            title="TRPG 会话结束",
            border_style="green",
        ))

    try:
        _run_async(_run())
    except KeyboardInterrupt:
        agent.land(session)
        console.print("\n[yellow]已退出互动模式。[/yellow]")


# ------------------------------------------------------------------ #
# narrative check                                                       #
# ------------------------------------------------------------------ #

@app.command("check")
def check_chapter(
    chapter: int = typer.Option(..., "--chapter", "-c", help="章节号"),
    draft: Optional[Path] = typer.Option(None, "--draft", "-d", help="草稿文件路径"),
    project: str = typer.Option("default", "--project", "-p", help="项目 ID"),
) -> None:
    """对草稿进行多维一致性检查。有硬冲突时以红色警告并退出码 1。"""
    from narrative_os.skills.consistency import ConsistencyChecker

    if draft:
        if not draft.exists():
            _print_error(f"找不到文件：{draft}")
            raise typer.Exit(code=1)
        text = draft.read_text(encoding="utf-8")
    else:
        _print_error("请使用 --draft 指定草稿文件路径。")
        raise typer.Exit(code=1)

    checker = ConsistencyChecker()
    report = checker.check(text=text, chapter=chapter)

    if report.issues:
        table = Table("维度", "严重性", "描述", "建议", title=f"第{chapter}章一致性检查结果")
        for issue in report.issues:
            color = "red" if issue.severity == "hard" else "yellow" if issue.severity == "soft" else "dim"
            table.add_row(
                issue.dimension,
                f"[{color}]{issue.severity}[/{color}]",
                issue.description[:60],
                issue.suggestion[:40],
            )
        console.print(table)
    else:
        _print_success(f"第{chapter}章一致性检查通过，无任何冲突。")
        return

    console.print(f"\n{report.summary()}")
    if report.hard_issues:
        _print_error(f"发现 {len(report.hard_issues)} 个硬冲突，请修复后再提交。")
        raise typer.Exit(code=1)


# ------------------------------------------------------------------ #
# narrative humanize                                                    #
# ------------------------------------------------------------------ #

@app.command("humanize")
def humanize_text(
    input_file: Optional[Path] = typer.Option(None, "--input", "-i", help="输入文件"),
    chapter: Optional[int] = typer.Option(None, "--chapter", "-c", help="章节号（从状态读取）"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="输出文件"),
    project: str = typer.Option("default", "--project", "-p", help="项目 ID"),
) -> None:
    """对草稿进行去AI味/人味注入改写。"""
    import time as _time
    from narrative_os.skills.humanize import Humanizer

    if input_file:
        if not input_file.exists():
            _print_error(f"找不到文件：{input_file}")
            raise typer.Exit(code=1)
        text = input_file.read_text(encoding="utf-8")
    else:
        _print_error("请使用 --input 指定输入文件。")
        raise typer.Exit(code=1)

    humanizer = Humanizer()
    start = _time.time()
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                  transient=True) as progress:
        t = progress.add_task("正在润色...", total=None)
        try:
            result = _run_async(humanizer.humanize(text))
            progress.update(t, description="润色完成 ✓")
        except Exception as exc:
            _print_error(f"润色失败：{exc}")
            raise typer.Exit(code=1)
    elapsed = _time.time() - start

    orig_wc = len(text.replace(" ", "").replace("\n", ""))
    out_wc = len(result.humanized_text.replace(" ", "").replace("\n", ""))
    console.print(f"[dim]输入：{orig_wc:,} 字 → 输出：{out_wc:,} 字 | 改写率：{result.change_ratio:.0%} | 耗时：{elapsed:.1f}s[/dim]")

    if output:
        output.write_text(result.humanized_text, encoding="utf-8")
        _print_success(f"已写入 {output}")
    else:
        console.rule("[dim]润色结果[/dim]")
        console.print(result.humanized_text)


# ------------------------------------------------------------------ #
# narrative rollback                                                    #
# ------------------------------------------------------------------ #

@app.command("rollback")
def rollback_project(
    steps: int = typer.Option(1, "--steps", "-n", help="回滚章节数"),
    project: str = typer.Option("default", "--project", "-p", help="项目 ID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认提示"),
) -> None:
    """回滚项目到最近 N 章之前的状态。"""
    from narrative_os.core.state import StateManager
    from narrative_os.infra.config import settings

    mgr = StateManager(project_id=project)
    try:
        state = mgr.load_state()
    except FileNotFoundError:
        _print_error(f"项目 '{project}' 尚无已保存状态。")
        raise typer.Exit(code=1)

    target_chapter = max(0, state.current_chapter - steps)

    if not yes:
        confirmed = typer.confirm(
            f"确认回滚项目 '{project}' 最近 {steps} 章（当前第{state.current_chapter}章 → 第{target_chapter}章）？"
        )
        if not confirmed:
            console.print("[yellow]已取消。[/yellow]")
            raise typer.Exit()

    try:
        if target_chapter == 0:
            # 回到初始状态
            state.current_chapter = 0
            mgr.save_state()
            _print_success(f"已回滚到项目初始状态。")
        else:
            mgr.rollback(chapter=target_chapter)
            _print_success(f"已回滚到第 {target_chapter} 章快照。")
    except FileNotFoundError as exc:
        _print_error(f"回滚失败：{exc}")
        raise typer.Exit(code=1)

    # 打印回滚后的状态
    try:
        new_state = mgr.load_state()
        console.print(f"[dim]当前章节：第{new_state.current_chapter}章 卷{new_state.current_volume}[/dim]")
    except Exception:
        pass


# ------------------------------------------------------------------ #
# narrative dev                                                         #
# ------------------------------------------------------------------ #

@app.command("dev")
def dev(
    host: str = typer.Option("127.0.0.1", "--host", help="监听地址"),
    api_port: int = typer.Option(8000, "--api-port", help="后端 API 端口"),
    frontend_port: int = typer.Option(5173, "--frontend-port", help="前端开发服务器端口"),
    api_only: bool = typer.Option(False, "--api-only", help="仅启动后端 API"),
    frontend_only: bool = typer.Option(False, "--frontend-only", help="仅启动前端"),
) -> None:
    """一键启动前后端开发服务，退出时自动清理进程和端口。"""
    from narrative_os.infra.dev_server import DevServerManager, PortInUseError

    manager = DevServerManager()
    try:
        manager.start_all(
            host=host,
            api_port=api_port,
            frontend_port=frontend_port,
            api_only=api_only,
            frontend_only=frontend_only,
        )
        # 阻塞直到用户按 Ctrl+C（信号处理在 start_all 中注册）
        while True:
            import time as _time
            _time.sleep(1)
    except PortInUseError as exc:
        _print_error(str(exc))
        raise typer.Exit(code=1)
    except KeyboardInterrupt:
        pass  # cleanup 已通过 atexit 和信号处理注册


# ------------------------------------------------------------------ #
# 内部帮助                                                              #
# ------------------------------------------------------------------ #

def _show_chapter_summary(chapter, volume, word_count, change_ratio, critic) -> None:
    passed = critic.passed if critic else True
    qs = f"{critic.quality_score:.2f}" if critic else "N/A"
    hs = f"{critic.hook_score:.2f}" if critic else "N/A"
    status_color = "green" if passed else "yellow"

    console.print(Panel(
        f"[bold]卷{volume} 第{chapter}章[/bold] 生成完成\n"
        f"字数：{word_count:,}  |  改写比：{change_ratio:.0%}\n"
        f"质量分：{qs}  |  钩子分：{hs}  |  "
        f"审查：[{status_color}]{'通过' if passed else '警告'}[/{status_color}]",
        title="生成摘要",
        border_style=status_color,
    ))


# ================================================================== #
# narrative world — 世界管理命令组                                      #
# ================================================================== #

world_app = typer.Typer(name="world", help="世界状态管理（校验/编译/发布）", no_args_is_help=True)
app.add_typer(world_app, name="world")


@world_app.command("publish")
def world_publish(
    project: str = typer.Argument(..., help="项目 ID"),
) -> None:
    """校验 + 编译 + 发布运行态世界。"""
    import httpx
    api_base = "http://127.0.0.1:8000"
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                  transient=True) as progress:
        t = progress.add_task("正在发布世界...", total=None)
        try:
            resp = httpx.post(f"{api_base}/projects/{project}/world/publish", timeout=30)
            progress.update(t, description="完成 ✓")
        except httpx.ConnectError:
            _print_error("无法连接到 API 服务，请先运行 `narrative dev`。")
            raise typer.Exit(code=1)

    if resp.status_code == 200:
        data = resp.json()
        _print_success(f"世界发布成功（项目：{project}）")
        console.print(f"[dim]{data}[/dim]")
    else:
        _print_error(f"发布失败（{resp.status_code}）：{resp.text[:200]}")
        raise typer.Exit(code=1)


@world_app.command("validate")
def world_validate(
    project: str = typer.Argument(..., help="项目 ID"),
) -> None:
    """仅校验世界数据，输出 errors/warnings。"""
    import httpx
    api_base = "http://127.0.0.1:8000"
    try:
        resp = httpx.get(f"{api_base}/projects/{project}/world/validate", timeout=30)
    except httpx.ConnectError:
        _print_error("无法连接到 API 服务，请先运行 `narrative dev`。")
        raise typer.Exit(code=1)

    data = resp.json()
    errors = data.get("errors", [])
    warnings = data.get("warnings", [])
    if errors:
        for e in errors:
            console.print(f"[bold red]ERROR[/bold red] {e}")
        _print_error(f"校验失败，{len(errors)} 个错误。")
        raise typer.Exit(code=1)
    if warnings:
        for w in warnings:
            console.print(f"[bold yellow]WARN[/bold yellow] {w}")
    _print_success(f"世界校验通过（{len(warnings)} 个警告）。")


@world_app.command("status")
def world_status(
    project: str = typer.Argument(..., help="项目 ID"),
) -> None:
    """查看当前世界发布版本和状态。"""
    import httpx
    api_base = "http://127.0.0.1:8000"
    try:
        resp = httpx.get(f"{api_base}/projects/{project}/world/status", timeout=30)
    except httpx.ConnectError:
        _print_error("无法连接到 API 服务，请先运行 `narrative dev`。")
        raise typer.Exit(code=1)

    data = resp.json()
    table = Table("字段", "值", title=f"世界状态（{project}）")
    for k, v in data.items():
        table.add_row(str(k), str(v)[:80])
    console.print(table)


# ================================================================== #
# narrative character — 角色管理命令组                                  #
# ================================================================== #

character_app = typer.Typer(name="character", help="角色管理（列出/查看/更新运行态）", no_args_is_help=True)
app.add_typer(character_app, name="character")


@character_app.command("list")
def character_list(
    project: str = typer.Argument(..., help="项目 ID"),
) -> None:
    """列出项目所有角色。"""
    import httpx
    api_base = "http://127.0.0.1:8000"
    try:
        resp = httpx.get(f"{api_base}/projects/{project}/characters", timeout=30)
    except httpx.ConnectError:
        _print_error("无法连接到 API 服务，请先运行 `narrative dev`。")
        raise typer.Exit(code=1)

    data = resp.json()
    characters = data if isinstance(data, list) else data.get("characters", [])
    table = Table("名称", "角色类型", "当前位置", title=f"角色列表（{project}）")
    for c in characters:
        name = c.get("name", "?")
        role = c.get("role", "?")
        loc = ""
        if isinstance(c.get("runtime"), dict):
            loc = c["runtime"].get("current_location", "")
        table.add_row(name, role, loc)
    console.print(table)


@character_app.command("show")
def character_show(
    project: str = typer.Argument(..., help="项目 ID"),
    name: str = typer.Argument(..., help="角色名称"),
) -> None:
    """查看指定角色详细信息（四层模型）。"""
    import httpx
    api_base = "http://127.0.0.1:8000"
    try:
        resp = httpx.get(f"{api_base}/projects/{project}/characters/{name}", timeout=30)
    except httpx.ConnectError:
        _print_error("无法连接到 API 服务，请先运行 `narrative dev`。")
        raise typer.Exit(code=1)

    if resp.status_code == 404:
        _print_error(f"角色 '{name}' 不存在。")
        raise typer.Exit(code=1)

    data = resp.json()
    import json as _json
    console.print(Panel(_json.dumps(data, ensure_ascii=False, indent=2),
                        title=f"角色详情：{name}", border_style="cyan"))


@character_app.command("update-runtime")
def character_update_runtime(
    project: str = typer.Argument(..., help="项目 ID"),
    name: str = typer.Argument(..., help="角色名称"),
    agenda: str = typer.Option("", "--agenda", help="更新 agenda"),
    location: str = typer.Option("", "--location", help="更新当前位置"),
) -> None:
    """更新角色运行态（agenda / location）。"""
    import httpx
    api_base = "http://127.0.0.1:8000"
    payload = CharacterRuntimeUpdateRequest(
        agenda=agenda or None,
        location=location or None,
    )

    if not payload.model_dump(exclude_none=True):
        _print_error("请至少提供 --agenda 或 --location 参数。")
        raise typer.Exit(code=1)

    try:
        resp = httpx.patch(
            f"{api_base}/projects/{project}/characters/{name}/runtime",
            json=payload.model_dump(exclude_none=True),
            timeout=30,
        )
    except httpx.ConnectError:
        _print_error("无法连接到 API 服务，请先运行 `narrative dev`。")
        raise typer.Exit(code=1)

    if resp.status_code in (200, 204):
        _print_success(f"角色 '{name}' 运行态已更新。")
    else:
        _print_error(f"更新失败（{resp.status_code}）：{resp.text[:200]}")
        raise typer.Exit(code=1)


# ================================================================== #
# narrative sl — 存档管理命令组                                         #
# ================================================================== #

sl_app = typer.Typer(name="sl", help="TRPG 存档管理（列出/存档/读档）", no_args_is_help=True)
app.add_typer(sl_app, name="sl")


@sl_app.command("list")
def sl_list(
    project: str = typer.Argument(..., help="项目 ID"),
    session_id: str = typer.Argument(..., help="会话 ID"),
) -> None:
    """列出指定会话的所有存档。"""
    import httpx
    api_base = "http://127.0.0.1:8000"
    try:
        resp = httpx.get(
            f"{api_base}/projects/{project}/sessions/{session_id}/saves",
            timeout=30,
        )
    except httpx.ConnectError:
        _print_error("无法连接到 API 服务，请先运行 `narrative dev`。")
        raise typer.Exit(code=1)

    saves = resp.json() if isinstance(resp.json(), list) else []
    table = Table("存档 ID", "触发方式", "轮数", "时间", title=f"存档列表（{session_id}）")
    for s in saves:
        table.add_row(
            s.get("save_id", "?"), s.get("trigger", "?"),
            str(s.get("turn", 0)), str(s.get("timestamp", "?"))[:19]
        )
    console.print(table)


@sl_app.command("save")
def sl_save(
    project: str = typer.Argument(..., help="项目 ID"),
    session_id: str = typer.Argument(..., help="会话 ID"),
) -> None:
    """手动存档当前会话。"""
    import httpx
    api_base = "http://127.0.0.1:8000"
    payload = SaveRequest(trigger="manual")
    try:
        resp = httpx.post(
            f"{api_base}/projects/{project}/sessions/{session_id}/save",
            json=payload.model_dump(),
            timeout=30,
        )
    except httpx.ConnectError:
        _print_error("无法连接到 API 服务，请先运行 `narrative dev`。")
        raise typer.Exit(code=1)

    if resp.status_code in (200, 201):
        data = resp.json()
        _print_success(f"存档成功，save_id：{data.get('save_id', '?')}")
    else:
        _print_error(f"存档失败（{resp.status_code}）：{resp.text[:200]}")
        raise typer.Exit(code=1)


@sl_app.command("load")
def sl_load(
    project: str = typer.Argument(..., help="项目 ID"),
    session_id: str = typer.Argument(..., help="会话 ID"),
    save_id: str = typer.Argument(..., help="存档 ID"),
) -> None:
    """从指定存档恢复会话（软回退）。"""
    import httpx
    api_base = "http://127.0.0.1:8000"
    try:
        resp = httpx.post(
            f"{api_base}/projects/{project}/sessions/{session_id}/load/{save_id}",
            timeout=30,
        )
    except httpx.ConnectError:
        _print_error("无法连接到 API 服务，请先运行 `narrative dev`。")
        raise typer.Exit(code=1)

    if resp.status_code == 200:
        data = resp.json()
        _print_success(f"读档成功，已恢复到第 {data.get('restored_turn', '?')} 轮。")
    else:
        _print_error(f"读档失败（{resp.status_code}）：{resp.text[:200]}")
        raise typer.Exit(code=1)


# ================================================================== #
# narrative canon — 变更集审批命令组                                    #
# ================================================================== #

canon_app = typer.Typer(name="canon", help="Canon 变更集审批（列出/查看/批准/驳回）", no_args_is_help=True)
app.add_typer(canon_app, name="canon")


@canon_app.command("list")
def canon_list(
    project: str = typer.Argument(..., help="项目 ID"),
) -> None:
    """列出项目所有待审变更集。"""
    import httpx
    api_base = "http://127.0.0.1:8000"
    try:
        resp = httpx.get(f"{api_base}/projects/{project}/changesets", timeout=30)
    except httpx.ConnectError:
        _print_error("无法连接到 API 服务，请先运行 `narrative dev`。")
        raise typer.Exit(code=1)

    changesets = resp.json() if isinstance(resp.json(), list) else []
    table = Table("变更集 ID", "来源", "提交方式", "待审数", "已确认数", "创建时间",
                  title=f"变更集列表（{project}）")
    for cs in changesets:
        table.add_row(
            cs.get("changeset_id", "?")[:18] + "...",
            cs.get("source", "?"),
            cs.get("commit_mode", "?"),
            str(cs.get("pending_count", 0)),
            str(cs.get("confirmed_count", 0)),
            str(cs.get("created_at", "?"))[:19],
        )
    console.print(table)


@canon_app.command("review")
def canon_review(
    project: str = typer.Argument(..., help="项目 ID"),
    cs_id: str = typer.Argument(..., help="变更集 ID"),
) -> None:
    """查看变更集详情（含每条变更的 before/after）。"""
    import httpx
    import json as _json
    api_base = "http://127.0.0.1:8000"
    try:
        resp = httpx.get(f"{api_base}/projects/{project}/changesets/{cs_id}", timeout=30)
    except httpx.ConnectError:
        _print_error("无法连接到 API 服务，请先运行 `narrative dev`。")
        raise typer.Exit(code=1)

    if resp.status_code == 404:
        _print_error(f"变更集 '{cs_id}' 不存在。")
        raise typer.Exit(code=1)

    data = resp.json()
    console.print(Panel(
        _json.dumps(data, ensure_ascii=False, indent=2),
        title=f"变更集详情：{cs_id[:18]}...",
        border_style="cyan",
    ))


@canon_app.command("approve")
def canon_approve(
    project: str = typer.Argument(..., help="项目 ID"),
    cs_id: str = typer.Argument(..., help="变更集 ID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认提示"),
) -> None:
    """批准变更集并提交正史。"""
    import httpx
    if not yes:
        confirmed = typer.confirm(f"确认批准变更集 '{cs_id[:18]}...' 并提交正史？")
        if not confirmed:
            console.print("[yellow]已取消。[/yellow]")
            raise typer.Exit()

    api_base = "http://127.0.0.1:8000"
    try:
        resp = httpx.post(
            f"{api_base}/projects/{project}/changesets/{cs_id}/approve",
            timeout=30,
        )
    except httpx.ConnectError:
        _print_error("无法连接到 API 服务，请先运行 `narrative dev`。")
        raise typer.Exit(code=1)

    if resp.status_code == 200:
        data = resp.json()
        _print_success(
            f"批准成功：{data.get('approved_count', 0)} 条已审批，"
            f"{data.get('committed_count', 0)} 条已提交正史。"
        )
    else:
        _print_error(f"批准失败（{resp.status_code}）：{resp.text[:200]}")
        raise typer.Exit(code=1)


@canon_app.command("reject")
def canon_reject(
    project: str = typer.Argument(..., help="项目 ID"),
    cs_id: str = typer.Argument(..., help="变更集 ID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认提示"),
) -> None:
    """驳回整个变更集。"""
    import httpx
    if not yes:
        confirmed = typer.confirm(f"确认驳回变更集 '{cs_id[:18]}...'？")
        if not confirmed:
            console.print("[yellow]已取消。[/yellow]")
            raise typer.Exit()

    api_base = "http://127.0.0.1:8000"
    try:
        resp = httpx.post(
            f"{api_base}/projects/{project}/changesets/{cs_id}/reject",
            timeout=30,
        )
    except httpx.ConnectError:
        _print_error("无法连接到 API 服务，请先运行 `narrative dev`。")
        raise typer.Exit(code=1)

    if resp.status_code == 200:
        data = resp.json()
        _print_success(f"驳回成功：{data.get('rejected_count', 0)} 条已驳回。")
    else:
        _print_error(f"驳回失败（{resp.status_code}）：{resp.text[:200]}")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
