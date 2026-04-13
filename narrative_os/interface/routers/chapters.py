"""routers/chapters.py — 章节生成路由模块。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from narrative_os.core.plot_repository import get_plot_repository
from narrative_os.core.project_repository import ProjectHandle
from narrative_os.interface.services.chapter_service import ChapterService, get_chapter_service
from narrative_os.schemas.chapters import (
    ChapterListItem,
    ChapterTextResponse,
    RunChapterRequest,
    RunChapterResponse,
    PlanChapterRequest,
    PlanChapterResponse,
    CheckChapterRequest,
    CheckChapterResponse,
    ExportNovelResponse,
    HumanizeRequest,
    HumanizeResponse,
    MetricsRequest,
    MetricsResponse,
    CostResponse,
    WritingContextCharacter,
    WritingBenchmarkSummary,
    WritingContextResponse,
    WritingPrecheckItem,
    WritingWorldSummary,
)

router = APIRouter(tags=["chapters"])


def _svc() -> ChapterService:
    return get_chapter_service()


# ------------------------------------------------------------------ #
# 章节生成                                                              #
# ------------------------------------------------------------------ #


@router.post("/chapters/run", response_model=RunChapterResponse, summary="完整生成一章")
async def run_chapter_route(
    req: RunChapterRequest,
    svc: ChapterService = Depends(_svc),
) -> RunChapterResponse:
    from narrative_os.execution.narrative_compiler import AuthoringInputError

    try:
        _, result = await svc.run_chapter(req)
    except TimeoutError:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="章节生成超时，请重试")
    except AuthoringInputError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"生成失败：{exc}")

    edited = result.get("edited_chapter")
    if edited is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="未能生成最终章节。")

    critic = result.get("critic_report")

    return RunChapterResponse(
        chapter=edited.chapter,
        volume=edited.volume,
        text=edited.text,
        word_count=edited.word_count,
        change_ratio=edited.change_ratio,
        quality_score=critic.quality_score if critic else 0.0,
        hook_score=critic.hook_score if critic else 0.0,
        passed=critic.passed if critic else True,
        retry_count=result.get("retry_count", 0),
        run_id=result.get("run_id", ""),
        benchmark_adherence_score=(result.get("benchmark_score") or {}).get("adherence_score"),
        benchmark_humanness_score=(result.get("benchmark_score") or {}).get("humanness_score"),
        benchmark_violations=(result.get("benchmark_score") or {}).get("violations", []),
    )


@router.get("/projects/{project_id}/writing-context", response_model=WritingContextResponse, summary="写作工作台上下文")
async def get_writing_context(
    project_id: str,
    chapter: int = 1,
    svc: ChapterService = Depends(_svc),
) -> WritingContextResponse:
    context = await svc.get_writing_context(project_id, chapter)
    published_world = context["published_world"]
    characters = context["characters"]
    volume_goal = context["current_volume_goal"]
    previous_hook = context["previous_hook"]
    pending_changes_count = context["pending_changes_count"]

    prechecks = [
        WritingPrecheckItem(
            key="world_published",
            passed=published_world is not None,
            severity="error",
            message="WorldState 已发布" if published_world is not None else "WorldState 尚未发布",
            action_path=f"/project/{project_id}/worldbuilder",
        ),
        WritingPrecheckItem(
            key="character_drive",
            passed=all(character.drive is not None for character in characters),
            severity="warning",
            message="角色 Drive 层完整" if all(character.drive is not None for character in characters) else "存在角色缺少 Drive 层",
            action_path=f"/project/{project_id}/characters",
        ),
        WritingPrecheckItem(
            key="volume_goal",
            passed=bool(volume_goal.strip()),
            severity="warning",
            message="当前卷目标已配置" if volume_goal.strip() else "PlotGraph 缺少当前卷目标",
            action_path=f"/project/{project_id}/plot",
        ),
    ]

    factions = [
        faction.name or faction_id
        for faction_id, faction in list((published_world.factions if published_world is not None else {}).items())[:5]
    ]
    geography = []
    for region_id, region in list((published_world.geography if published_world is not None else {}).items())[:5]:
        if isinstance(region, dict):
            geography.append(str(region.get("name") or region.get("id") or region_id))
        else:
            geography.append(str(region_id))
    rules = list((published_world.rules_of_world if published_world is not None else []))[:5]

    return WritingContextResponse(
        project_id=project_id,
        chapter=chapter,
        previous_hook=previous_hook,
        current_volume_goal=volume_goal,
        pending_changes_count=pending_changes_count,
        active_benchmark=(
            WritingBenchmarkSummary.model_validate(context["active_benchmark"])
            if context.get("active_benchmark")
            else None
        ),
        active_author_skill=(
            WritingBenchmarkSummary.model_validate(context["active_author_skill"])
            if context.get("active_author_skill")
            else None
        ),
        world=WritingWorldSummary(
            published=published_world is not None,
            factions=factions,
            regions=geography,
            rules=rules,
        ),
        characters=[
            WritingContextCharacter(
                name=character.name,
                current_location=character.runtime.current_location,
                current_agenda=character.runtime.current_agenda,
                current_pressure=character.runtime.current_pressure,
                recent_key_events=character.runtime.recent_key_events,
            )
            for character in characters
        ],
        prechecks=prechecks,
    )


@router.post("/chapters/plan", response_model=PlanChapterResponse, summary="仅生成章节剧情骨架")
async def plan_chapter_route(
    req: PlanChapterRequest,
    svc: ChapterService = Depends(_svc),
) -> PlanChapterResponse:
    try:
        plan = await svc.plan_chapter(req)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"规划失败：{exc}")
    return PlanChapterResponse(
        chapter_outline=plan.chapter_outline,
        planned_nodes=[n.model_dump() for n in plan.planned_nodes],
        dialogue_goals=plan.dialogue_goals,
        hook_suggestion=plan.hook_suggestion,
        hook_type=plan.hook_type,
        tension_curve=[v for _, v in plan.tension_curve],
    )


@router.post("/chapters/check", response_model=CheckChapterResponse, summary="检查章节质量")
async def check_chapter(req: CheckChapterRequest) -> CheckChapterResponse:
    import sys
    from narrative_os.core.plot import PlotGraph
    _api = sys.modules.get("narrative_os.interface.api")
    # Use api-level ConsistencyChecker so tests can patch it
    _CC = getattr(_api, "ConsistencyChecker", None) if _api else None
    if _CC is None:
        from narrative_os.skills.consistency import ConsistencyChecker as _CC
    _try = getattr(_api, "_try_load_project", None) if _api else None

    checker = _CC()
    plot_graph = get_plot_repository().get_plot_graph(req.project_id)
    mgr = _try(req.project_id) if _try else None
    if mgr is not None and not isinstance(mgr, ProjectHandle):
        try:
            kb = mgr.load_kb()
            plot_data = kb.get("plot_graph")
            if plot_data:
                plot_graph = PlotGraph.from_dict(plot_data)
        except Exception:
            pass
    report = checker.check(text=req.text, chapter=req.chapter, plot_graph=plot_graph)
    return CheckChapterResponse(
        issues=[i.model_dump() for i in report.issues],
        passed=report.passed,
    )


@router.post("/chapters/humanize", response_model=HumanizeResponse, summary="去AI痕迹")
async def humanize_chapter(req: HumanizeRequest) -> HumanizeResponse:
    import difflib
    from narrative_os.skills.humanize import Humanizer
    h = Humanizer()
    try:
        output = await h.humanize(req.text)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"人味化处理失败：{exc}")
    orig_words = req.text.split()
    new_words = output.humanized_text.split()
    matcher = difflib.SequenceMatcher(None, orig_words, new_words)
    diff_list: list[dict[str, str]] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag != "equal":
            diff_list.append({"type": tag, "old": " ".join(orig_words[i1:i2]), "new": " ".join(new_words[j1:j2])})
    return HumanizeResponse(
        original=req.text,
        humanized=output.humanized_text,
        changes_count=len(diff_list),
        diff=diff_list,
    )


# ------------------------------------------------------------------ #
# 质量指标 + 成本                                                       #
# ------------------------------------------------------------------ #


@router.post("/metrics", response_model=MetricsResponse, summary="计算叙事质量指标")
async def compute_metrics(req: MetricsRequest) -> MetricsResponse:
    from narrative_os.agents.writer import ChapterDraft
    from narrative_os.skills.metrics import NarrativeMetricsCalc
    try:
        draft = ChapterDraft.model_validate(req.draft)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"解析 ChapterDraft 失败：{exc}")
    calc = NarrativeMetricsCalc()
    m = calc.evaluate_chapter(draft, word_count_target=req.word_count_target)
    return MetricsResponse(
        chapter=m.chapter,
        overall_score=m.overall_score,
        avg_tension=m.avg_tension,
        hook_score=m.hook_score,
        payoff_density=m.payoff_density,
        pacing_score=m.pacing_score,
        tension_trend=m.tension_trend,
        consistency_score=m.consistency_score,
        word_efficiency=m.word_efficiency,
        qd_01_catharsis=round(min(m.avg_tension * 0.9, 10.0), 2),
        qd_02_golden_finger=round(m.payoff_density, 2),
        qd_03_rhythm=round(m.pacing_score, 2),
        qd_04_dialogue=round(m.word_efficiency * 0.8, 2),
        qd_05_char_consistency=round(m.consistency_score, 2),
        qd_06_meaning=round(m.overall_score * 0.85, 2),
        qd_07_hook=round(m.hook_score, 2),
        qd_08_readability=round(m.word_efficiency, 2),
    )


@router.get("/cost", response_model=CostResponse, summary="查看今日 Token 消耗")
async def get_cost() -> CostResponse:
    from narrative_os.infra.cost import cost_ctrl
    s = cost_ctrl.summary()
    return CostResponse(
        used_tokens=s["used"],
        budget_tokens=s["budget"],
        usage_ratio=s["ratio"],
        by_skill=s.get("by_skill", {}),
        by_agent=s.get("by_agent", {}),
    )


# ------------------------------------------------------------------ #
# 项目章节列表                                                           #
# ------------------------------------------------------------------ #


def _get_load_project_or_404():
    import sys
    _api = sys.modules.get("narrative_os.interface.api")
    if _api is not None and hasattr(_api, "_load_project_or_404"):
        return _api._load_project_or_404
    from narrative_os.interface.services.project_service import get_project_service
    return get_project_service().load_project_or_404


@router.get("/projects/{project_id}/chapters", response_model=list[ChapterListItem], summary="项目章节列表")
async def list_project_chapters(
    project_id: str,
    svc: ChapterService = Depends(_svc),
) -> list[ChapterListItem]:
    loader = _get_load_project_or_404()
    if loader is not None:
        mgr = loader(project_id)
        if not mgr.state:
            return []
        chapter_files = set(mgr.list_chapter_files())
        items = []
        for meta in sorted(mgr.state.chapters, key=lambda chapter_meta: chapter_meta.chapter):
            payload = meta.model_dump()
            payload["has_text"] = meta.chapter in chapter_files
            items.append(payload)
        return [ChapterListItem.model_validate(item) for item in items]
    items = await svc.list_project_chapters(project_id)
    return [ChapterListItem.model_validate(item) for item in items]


@router.get("/projects/{project_id}/chapters/{chapter_num}", response_model=ChapterTextResponse, summary="获取章节文本")
async def get_chapter_text(
    project_id: str,
    chapter_num: int,
    svc: ChapterService = Depends(_svc),
) -> ChapterTextResponse:
    loader = _get_load_project_or_404()
    if loader is not None:
        mgr = loader(project_id)
        text = mgr.load_chapter_text(chapter_num)
        if text is None:
            raise HTTPException(status_code=404, detail={"detail": f"章节 {chapter_num} 文本不存在。", "code": "NOT_FOUND"})
        meta = next(
            (item for item in (mgr.state.chapters if mgr.state else []) if item.chapter == chapter_num),
            None,
        )
        return ChapterTextResponse(
            chapter=chapter_num,
            text=text,
            word_count=len(text),
            summary=meta.summary if meta else "",
            quality_score=meta.quality_score if meta else 0.0,
            hook_score=meta.hook_score if meta else 0.0,
            timestamp=meta.timestamp if meta else "",
        )
    payload = await svc.get_project_chapter(project_id, chapter_num)
    if payload is None:
        raise HTTPException(status_code=404, detail={"detail": f"章节 {chapter_num} 文本不存在。", "code": "NOT_FOUND"})
    return ChapterTextResponse.model_validate(payload)


@router.get("/projects/{project_id}/export", response_model=ExportNovelResponse, summary="导出全本")
async def export_project(
    project_id: str,
    format: str = "txt",
    svc: ChapterService = Depends(_svc),
) -> ExportNovelResponse:
    loader = _get_load_project_or_404()
    if loader is not None:
        mgr = loader(project_id)
        chapter_nums = sorted(mgr.list_chapter_files())
        if not chapter_nums:
            raise HTTPException(status_code=404, detail={"detail": "该项目尚无已生成章节。", "code": "NOT_FOUND"})
        parts: list[str] = []
        total_words = 0
        for chapter_num in chapter_nums:
            text = mgr.load_chapter_text(chapter_num)
            if not text:
                continue
            parts.append(f"第{chapter_num}章\n\n{text}\n\n{'─' * 40}\n")
            total_words += len(text)
        title = mgr.state.project_name if mgr.state else project_id
        return ExportNovelResponse(
            project_id=project_id,
            title=title,
            chapter_count=len(parts),
            total_chapters=len(parts),
            total_words=total_words,
            format=format,
            content="\n".join(parts),
        )
    payload = await svc.export_project(project_id, format=format)
    if not payload.get("chapter_count"):
        raise HTTPException(status_code=404, detail={"detail": "该项目尚无已生成章节。", "code": "NOT_FOUND"})
    return ExportNovelResponse.model_validate(payload)
