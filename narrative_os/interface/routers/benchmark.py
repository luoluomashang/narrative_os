"""routers/benchmark.py — Benchmark Phase 2 路由。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from narrative_os.infra.database import get_db
from narrative_os.interface.services.benchmark_service import (
    BenchmarkService,
    get_benchmark_service,
)
from narrative_os.schemas.benchmark import (
    AuthorSkillProfile,
    BenchmarkJobCreateRequest,
    BenchmarkJobCreateResponse,
    BenchmarkJobDetailResponse,
    BenchmarkProfile,
    BenchmarkProfileActivateRequest,
    BenchmarkSkillApplyRequest,
    BenchmarkSkillApplyResponse,
    BenchmarkSkillListResponse,
    BenchmarkSnippetListResponse,
)

router = APIRouter(tags=["benchmark"])


def _svc() -> BenchmarkService:
    return get_benchmark_service()


@router.post(
    "/projects/{project_id}/benchmark/jobs",
    response_model=BenchmarkJobCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="创建 benchmark job",
)
async def create_benchmark_job(
    project_id: str,
    req: BenchmarkJobCreateRequest,
    db: AsyncSession = Depends(get_db),
    svc: BenchmarkService = Depends(_svc),
) -> BenchmarkJobCreateResponse:
    return await svc.create_job(db, project_id, req)


@router.get(
    "/projects/{project_id}/benchmark/jobs/{run_id}",
    response_model=BenchmarkJobDetailResponse,
    summary="查询 benchmark job 详情",
)
async def get_benchmark_job(
    project_id: str,
    run_id: str,
    db: AsyncSession = Depends(get_db),
    svc: BenchmarkService = Depends(_svc),
) -> BenchmarkJobDetailResponse:
    return await svc.get_job(db, project_id, run_id)


@router.get(
    "/projects/{project_id}/benchmark/profile",
    response_model=BenchmarkProfile | None,
    summary="获取项目当前 benchmark profile",
)
async def get_benchmark_profile(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    svc: BenchmarkService = Depends(_svc),
) -> BenchmarkProfile | None:
    return await svc.get_profile(db, project_id)


@router.get(
    "/projects/{project_id}/benchmark/snippets",
    response_model=BenchmarkSnippetListResponse,
    summary="获取 benchmark snippets",
)
async def list_benchmark_snippets(
    project_id: str,
    profile_id: str | None = Query(default=None),
    scene_type: str | None = Query(default=None),
    limit: int = Query(default=60, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    svc: BenchmarkService = Depends(_svc),
) -> BenchmarkSnippetListResponse:
    return await svc.list_snippets(db, project_id, profile_id=profile_id, scene_type=scene_type, limit=limit)


@router.post(
    "/projects/{project_id}/benchmark/profile/activate",
    response_model=BenchmarkProfile,
    summary="激活项目 benchmark profile",
)
async def activate_benchmark_profile(
    project_id: str,
    req: BenchmarkProfileActivateRequest,
    db: AsyncSession = Depends(get_db),
    svc: BenchmarkService = Depends(_svc),
) -> BenchmarkProfile:
    return await svc.activate_profile(db, project_id, req)


@router.get(
    "/projects/{project_id}/benchmark/skills",
    response_model=BenchmarkSkillListResponse,
    summary="获取作者蒸馏 skill 列表",
)
async def list_benchmark_skills(
    project_id: str,
    author_name: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    svc: BenchmarkService = Depends(_svc),
) -> BenchmarkSkillListResponse:
    return await svc.list_skills(db, project_id, author_name=author_name, limit=limit)


@router.get(
    "/projects/{project_id}/benchmark/skills/{skill_id}",
    response_model=AuthorSkillProfile,
    summary="获取作者蒸馏 skill 详情",
)
async def get_benchmark_skill(
    project_id: str,
    skill_id: str,
    db: AsyncSession = Depends(get_db),
    svc: BenchmarkService = Depends(_svc),
) -> AuthorSkillProfile:
    return await svc.get_skill(db, project_id, skill_id)


@router.post(
    "/projects/{project_id}/benchmark/skills/{skill_id}/apply",
    response_model=BenchmarkSkillApplyResponse,
    summary="应用作者蒸馏 skill 到当前项目",
)
async def apply_benchmark_skill(
    project_id: str,
    skill_id: str,
    req: BenchmarkSkillApplyRequest,
    db: AsyncSession = Depends(get_db),
    svc: BenchmarkService = Depends(_svc),
) -> BenchmarkSkillApplyResponse:
    return await svc.apply_skill(db, project_id, skill_id, req)