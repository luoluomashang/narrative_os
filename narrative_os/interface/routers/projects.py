"""routers/projects.py — 项目管理 CRUD 路由模块。"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from narrative_os.core.plot_repository import get_plot_repository
from narrative_os.schemas.projects import (
    CostHistoryItem,
    ProjectListItem,
    ProjectInitRequest,
    ProjectInitResponse,
    ProjectMutationResponse,
    ProjectRollbackResponse,
    ProjectStatusResponse,
    ProjectUpdateRequest,
    ProjectRollbackRequest,
    CostSummaryResponse,
    MetricsHistoryItem,
    ProjectSettingsResponse,
    SettingsUpdateRequest,
)
from narrative_os.interface.services.project_service import ProjectService, get_project_service

router = APIRouter(tags=["projects"])


def _svc() -> ProjectService:
    return get_project_service()


def _load_status_manager(project_id: str, svc: ProjectService):
    import sys

    from narrative_os.core.state import StateManager as RuntimeStateManager

    api_module = sys.modules.get("narrative_os.interface.api")
    state_manager_cls = getattr(api_module, "StateManager", None) if api_module else None
    if state_manager_cls is not None and state_manager_cls is not RuntimeStateManager:
        mgr = state_manager_cls(project_id=project_id, base_dir=".narrative_state")
        try:
            state = mgr.load_state()
        except FileNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"detail": f"项目 '{project_id}' 不存在。", "code": "NOT_FOUND"},
            )
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(exc),
            )
        if getattr(mgr, "state", None) is None and state is not None:
            mgr.state = state
        return mgr
    return svc.load_project_or_404(project_id)


# ------------------------------------------------------------------ #
# 项目 CRUD                                                            #
# ------------------------------------------------------------------ #


@router.get("/projects", summary="列出所有项目")
async def list_projects(svc: ProjectService = Depends(_svc)) -> list[ProjectListItem]:
    return [ProjectListItem.model_validate(item) for item in svc.list_projects()]


@router.post("/projects/init", response_model=ProjectInitResponse, status_code=status.HTTP_201_CREATED, summary="初始化项目")
async def init_project(req: ProjectInitRequest) -> ProjectInitResponse:
    try:
        handle = _svc().initialize_project(
            req.project_id,
            title=req.title,
            genre=req.genre,
            description=req.description,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"初始化失败：{exc}")
    state = handle.state
    return ProjectInitResponse(
        project_id=req.project_id,
        created_at=state.created_at,
        state_dir=handle.dir_path,
    )


@router.get("/projects/{project_id}/status", response_model=ProjectStatusResponse, summary="查看项目状态")
async def project_status(
    project_id: str,
    svc: ProjectService = Depends(_svc),
) -> ProjectStatusResponse:
    from narrative_os.core.character_repository import get_character_repository
    from narrative_os.core.canon_repository import get_canon_repository
    from narrative_os.core.world_repository import get_world_repository
    from narrative_os.infra.database import AsyncSessionLocal
    from narrative_os.interface.services.world_service import WorldService

    mgr = _load_status_manager(project_id, svc)
    state = mgr.state
    plot_graph = get_plot_repository().get_plot_graph(project_id)

    world_repo = get_world_repository()
    world_published = world_repo.has_published_world(project_id)
    characters = get_character_repository().list_characters(project_id)
    concept_ready = bool(state.one_sentence)
    try:
        async with AsyncSessionLocal() as db:
            concept = await WorldService().get_concept(project_id, db)
        concept_ready = bool(
            concept.one_sentence.strip()
            or concept.one_paragraph.strip()
            or concept.genre_tags
        )
    except Exception:
        pass
    pending_changes_count = get_canon_repository().pending_changes_count(project_id)
    current_volume_goal = plot_graph.get_current_volume_goal(project_id) if plot_graph is not None else ""

    workflow_nodes = [
        {
            "step_id": "concept",
            "label": "Concept",
            "status": "completed" if concept_ready else "pending",
            "href": f"/project/{project_id}/concept",
            "statistic": "概念已初始化" if concept_ready else "待补全概念",
        },
        {
            "step_id": "world",
            "label": "World",
            "status": "completed" if world_published else "pending",
            "href": f"/project/{project_id}/worldbuilder",
            "statistic": "世界已发布" if world_published else "世界未发布",
        },
        {
            "step_id": "characters",
            "label": "Characters",
            "status": "completed" if characters else "pending",
            "href": f"/project/{project_id}/characters",
            "statistic": f"{len(characters)} 个角色",
        },
        {
            "step_id": "plot",
            "label": "Plot",
            "status": "completed" if current_volume_goal else "pending",
            "href": f"/project/{project_id}/plot",
            "statistic": current_volume_goal or "未配置卷目标",
        },
        {
            "step_id": "chapter",
            "label": f"Chapter {state.current_chapter or 1}",
            "status": "in_progress" if state.current_chapter > 0 else "pending",
            "href": f"/project/{project_id}/write",
            "statistic": f"已写 {state.current_chapter} 章",
        },
        {
            "step_id": "maintenance",
            "label": "Maintenance",
            "status": "completed" if state.current_chapter > 0 else "pending",
            "href": f"/project/{project_id}/trace",
            "statistic": f"版本快照 {len(mgr.list_versions())} 个",
        },
        {
            "step_id": "canon",
            "label": "Canon",
            "status": "in_progress" if pending_changes_count else "pending",
            "href": f"/project/{project_id}/trace",
            "statistic": f"待确认变更 {pending_changes_count}",
        },
    ]

    return ProjectStatusResponse(
        project_id=project_id,
        project_name=state.project_name,
        current_chapter=state.current_chapter,
        current_volume=state.current_volume,
        total_word_count=sum(c.word_count for c in state.chapters),
        versions=mgr.list_versions(),
        world_published=world_published,
        character_count=len(characters),
        characters_with_drive=sum(1 for character in characters if character.drive is not None),
        pending_changes_count=pending_changes_count,
        current_volume_goal=current_volume_goal,
        workflow_nodes=workflow_nodes,
    )


@router.put("/projects/{project_id}", response_model=ProjectMutationResponse, summary="更新项目元信息")
async def update_project(
    project_id: str, req: ProjectUpdateRequest, svc: ProjectService = Depends(_svc)
) -> ProjectMutationResponse:
    import sys
    _api = sys.modules.get("narrative_os.interface.api")
    _lp = getattr(_api, "_load_project_or_404", None) if _api else None
    mgr = _lp(project_id) if _lp else svc.load_project_or_404(project_id)
    if req.title and mgr.state:
        mgr.state.project_name = req.title
    if req.genre or req.description:
        try:
            kb = mgr.load_kb()
            if req.genre:
                kb["genre"] = req.genre
            if req.description:
                kb["description"] = req.description
            mgr.save_kb(kb)
        except Exception:
            pass
    if mgr.state:
        mgr.save_state()
    return ProjectMutationResponse(success=True, project_id=project_id)


@router.delete("/projects/{project_id}", response_model=ProjectMutationResponse, summary="软删除项目")
async def delete_project(
    project_id: str, svc: ProjectService = Depends(_svc)
) -> ProjectMutationResponse:
    import sys
    _api = sys.modules.get("narrative_os.interface.api")
    _lp = getattr(_api, "_load_project_or_404", None) if _api else None
    if _lp:
        _lp(project_id)
    else:
        svc.load_project_or_404(project_id)
    return ProjectMutationResponse(success=True, project_id=project_id, status="deleted")


@router.post("/projects/{project_id}/archive", response_model=ProjectMutationResponse, summary="归档项目")
async def archive_project(
    project_id: str, svc: ProjectService = Depends(_svc)
) -> ProjectMutationResponse:
    import sys
    _api = sys.modules.get("narrative_os.interface.api")
    _lp = getattr(_api, "_load_project_or_404", None) if _api else None
    if _lp:
        _lp(project_id)
    else:
        svc.load_project_or_404(project_id)
    return ProjectMutationResponse(success=True, project_id=project_id, status="archived")


@router.post("/projects/{project_id}/rollback", response_model=ProjectRollbackResponse, summary="项目状态回滚")
async def rollback_project(
    project_id: str, req: ProjectRollbackRequest, svc: ProjectService = Depends(_svc)
) -> ProjectRollbackResponse:
    import sys

    _api = sys.modules.get("narrative_os.interface.api")
    _lp = getattr(_api, "_load_project_or_404", None) if _api else None
    if _lp is not None:
        mgr = _lp(project_id)
        current = mgr.state.current_chapter if mgr.state else 0
        target = max(0, current - req.steps)
        versions = mgr.list_versions()
        if not versions:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"项目 '{project_id}' 没有可用的版本快照。",
            )
        available = [version for version in versions if version <= target]
        if not available:
            available = versions
        target = available[-1]
        snapshot = mgr.rollback(chapter=target)
    else:
        _, target, snapshot = svc.rollback_project(project_id, req.steps)
    return ProjectRollbackResponse(
        success=True,
        project_id=project_id,
        rolled_back_to_chapter=target,
        snapshot_timestamp=snapshot.get("timestamp", ""),
    )


# ------------------------------------------------------------------ #
# 成本汇总                                                              #
# ------------------------------------------------------------------ #


@router.get("/cost/summary", response_model=CostSummaryResponse, summary="成本汇总")
async def get_cost_summary(
    project_id: Optional[str] = Query(default=None),
) -> CostSummaryResponse:
    import sys
    _api = sys.modules.get("narrative_os.interface.api")
    _ctrl = getattr(_api, "cost_ctrl", None) if _api else None
    if _ctrl is None:
        from narrative_os.infra.cost import cost_ctrl as _ctrl
    s = _ctrl.summary()
    used = s["used"]
    return CostSummaryResponse(
        today_tokens=used,
        total_tokens=used,
        today_cost_usd=round(used / 1000 * 0.002, 6),
        by_agent=s.get("by_agent", {}),
        by_skill=s.get("by_skill", {}),
    )


@router.get("/cost/history", response_model=list[CostHistoryItem], summary="成本历史记录")
async def get_cost_history(
    days: int = Query(default=7, ge=1, le=90),
    project_id: Optional[str] = Query(default=None),
) -> list[CostHistoryItem]:
    import datetime as _dt
    import sys
    _api = sys.modules.get("narrative_os.interface.api")
    _ctrl = getattr(_api, "cost_ctrl", None) if _api else None
    if _ctrl is None:
        from narrative_os.infra.cost import cost_ctrl as _ctrl
    s = _ctrl.summary()
    if s["used"] == 0:
        return []
    today = _dt.date.today().isoformat()
    return [
        CostHistoryItem(
            date=today,
            tokens=s["used"],
            cost_usd=round(s["used"] / 1000 * 0.002, 6),
            by_skill=s.get("by_skill", {}),
            by_agent=s.get("by_agent", {}),
        )
    ]


@router.get("/projects/{project_id}/metrics/history", response_model=list[MetricsHistoryItem], summary="项目章节评分历史")
async def get_metrics_history(
    project_id: str, svc: ProjectService = Depends(_svc)
) -> list[MetricsHistoryItem]:
    import sys
    from narrative_os.core.benchmark_repository import get_benchmark_repository
    from narrative_os.infra.database import AsyncSessionLocal, ensure_database_runtime

    _api = sys.modules.get("narrative_os.interface.api")
    _lp = getattr(_api, "_load_project_or_404", None) if _api else None
    mgr = _lp(project_id) if _lp else svc.load_project_or_404(project_id)
    if not mgr.state or not mgr.state.chapters:
        return []
    score_by_chapter: dict[int, dict[str, float]] = {}
    try:
        await ensure_database_runtime()
        async with AsyncSessionLocal() as db:
            scores = await get_benchmark_repository().list_scores_by_project(db, project_id)
        for score in scores:
            if score.chapter in score_by_chapter:
                continue
            score_by_chapter[score.chapter] = {
                "benchmark_adherence_score": score.adherence_score,
                "benchmark_humanness_score": score.humanness_score,
            }
    except Exception:
        score_by_chapter = {}
    return [
        {
            "chapter": m.chapter,
            "summary": m.summary,
            "quality_score": m.quality_score,
            "hook_score": m.hook_score,
            "word_count": m.word_count,
            "timestamp": m.timestamp,
            "benchmark_adherence_score": score_by_chapter.get(m.chapter, {}).get("benchmark_adherence_score", 0.0),
            "benchmark_humanness_score": score_by_chapter.get(m.chapter, {}).get("benchmark_humanness_score", 0.0),
            "qd_01": round(m.quality_score * 0.9 + m.hook_score * 0.1, 3),
            "qd_02": round(m.quality_score * 0.85, 3),
            "qd_03": round((m.quality_score + m.hook_score) / 2, 3),
            "qd_04": round(m.quality_score * 0.7 + 0.2, 3),
            "qd_05": round(m.quality_score * 0.95, 3),
            "qd_06": round(m.quality_score * 0.8 + m.hook_score * 0.15, 3),
            "qd_07": round(m.hook_score, 3),
            "qd_08": round(min(1.0, m.quality_score * 1.05), 3),
        }
        for m in sorted(mgr.state.chapters, key=lambda c: c.chapter)
    ]


# ------------------------------------------------------------------ #
# 全局 + 项目级 Settings                                               #
# ------------------------------------------------------------------ #


@router.get("/settings", summary="读取全局设置")
async def get_global_settings() -> dict[str, Any]:
    import os
    defaults: dict[str, Any] = {
        "llm_provider": os.environ.get("LLM_PROVIDER", "openai"),
        "llm_model": os.environ.get("LLM_MODEL", "gpt-4o"),
        "token_budget": int(os.environ.get("TOKEN_BUDGET", "200000")),
    }
    try:
        from sqlalchemy import select
        from narrative_os.infra.models import SettingRecord
        from narrative_os.infra.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            rows = (await db.execute(
                select(SettingRecord).where(SettingRecord.scope == "global")
            )).scalars().all()
            for row in rows:
                try:
                    defaults[row.key] = json.loads(row.value_json)
                except Exception:
                    pass
    except Exception:
        pass
    return defaults


@router.put("/settings", summary="更新全局设置")
async def update_global_settings(req: SettingsUpdateRequest) -> dict[str, Any]:
    try:
        from narrative_os.infra.models import SettingRecord
        from narrative_os.infra.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            for key, value in req.settings.items():
                row = await db.get(SettingRecord, key)
                if row is None:
                    db.add(SettingRecord(
                        key=key,
                        value_json=json.dumps(value, ensure_ascii=False),
                        scope="global",
                    ))
                else:
                    row.value_json = json.dumps(value, ensure_ascii=False)
                    row.scope = "global"
            await db.commit()
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"设置更新失败：{exc}")
    return {"success": True, "updated_keys": list(req.settings.keys())}


@router.get("/projects/{project_id}/settings", response_model=ProjectSettingsResponse, summary="读取项目设置")
async def get_project_settings(
    project_id: str, svc: ProjectService = Depends(_svc)
) -> ProjectSettingsResponse:
    import os
    svc.load_project_or_404(project_id)
    global_settings: dict[str, Any] = {
        "llm_provider": os.environ.get("LLM_PROVIDER", "openai"),
        "llm_model": os.environ.get("LLM_MODEL", "gpt-4o"),
        "token_budget": int(os.environ.get("TOKEN_BUDGET", "200000")),
    }
    project_overrides: dict[str, Any] = {}
    try:
        from sqlalchemy import select
        from narrative_os.infra.models import SettingRecord
        from narrative_os.infra.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            rows = (await db.execute(
                select(SettingRecord).where(SettingRecord.scope.in_(["global", "project"]))
            )).scalars().all()
            for row in rows:
                try:
                    val = json.loads(row.value_json)
                    if row.scope == "global":
                        global_settings[row.key] = val
                    elif row.scope == "project" and getattr(row, "project_id", None) == project_id:
                        project_overrides[row.key] = val
                except Exception:
                    pass
    except Exception:
        pass
    return ProjectSettingsResponse(
        project_id=project_id,
        global_settings=global_settings,
        project_overrides=project_overrides,
        merged={**global_settings, **project_overrides},
    )


@router.put("/projects/{project_id}/settings", summary="更新项目设置")
async def update_project_settings(
    project_id: str, req: SettingsUpdateRequest, svc: ProjectService = Depends(_svc)
) -> dict[str, Any]:
    svc.load_project_or_404(project_id)
    try:
        from narrative_os.infra.models import SettingRecord
        from narrative_os.infra.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            for key, value in req.settings.items():
                compound_key = f"{project_id}__{key}"
                row = await db.get(SettingRecord, compound_key)
                if row is None:
                    db.add(SettingRecord(
                        key=compound_key,
                        value_json=json.dumps(value, ensure_ascii=False),
                        scope="project",
                        project_id=project_id,
                    ))
                else:
                    row.value_json = json.dumps(value, ensure_ascii=False)
            await db.commit()
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"项目设置更新失败：{exc}")
    return {"success": True, "project_id": project_id, "updated_keys": list(req.settings.keys())}
