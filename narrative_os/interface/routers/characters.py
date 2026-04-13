"""routers/characters.py — 角色管理路由模块。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, status

from narrative_os.core.character_repository import get_character_repository
from narrative_os.execution.prompt_utils import build_character_voice_block, plain_text_contract
from narrative_os.core.plot import NodeStatus, NodeType, PlotGraph
from narrative_os.core.plot_repository import get_plot_repository
from narrative_os.core.project_repository import ProjectHandle
from narrative_os.schemas.characters import (
    CharacterCreateRequest,
    CharacterDetail,
    CharacterDrive,
    CharacterRuntime,
    CharacterRuntimeUpdateRequest,
    CharacterSummary,
    DeleteCharacterResponse,
    PlotGraphData,
    PlotVolumeGoalUpdateRequest,
    RelationshipProfile,
    TestVoiceRequest,
    TestVoiceResponse,
)
from narrative_os.interface.services.project_service import ProjectService, get_project_service

router = APIRouter(tags=["characters"])


def _svc() -> ProjectService:
    return get_project_service()


def _plot_graph_response(plot_graph: Any, project_id: str) -> PlotGraphData:
    payload = plot_graph.to_dict()
    edges = [
        {
            **edge,
            "source": edge.get("source") or edge.get("from_id"),
            "target": edge.get("target") or edge.get("to_id"),
        }
        for edge in payload.get("edges", [])
    ]
    return PlotGraphData(
        nodes=payload.get("nodes", []),
        edges=edges,
        current_volume_goal=plot_graph.get_current_volume_goal(project_id),
    )


def _compat_mgr(project_id: str, svc: ProjectService):
    import sys

    from narrative_os.core.state import StateManager as RuntimeStateManager

    _api = sys.modules.get("narrative_os.interface.api")
    _try = getattr(_api, "_try_load_project", None) if _api else None
    mgr = _try(project_id) if _try else svc.try_load_project(project_id)
    if mgr is None:
        return None
    if isinstance(mgr, ProjectHandle):
        if isinstance(mgr.manager, RuntimeStateManager):
            return None
        return mgr.manager
    return mgr


# ------------------------------------------------------------------ #
# C2: 角色列表 + 详情（基于 KB）                                         #
# ------------------------------------------------------------------ #


@router.get("/projects/{project_id}/plot", response_model=PlotGraphData, summary="获取项目情节图")
async def get_project_plot(
    project_id: str, svc: ProjectService = Depends(_svc)
) -> PlotGraphData:
    mgr = _compat_mgr(project_id, svc)
    if mgr is not None:
        kb = mgr.load_kb()
        plot_data = kb.get("plot_graph")
        if plot_data and isinstance(plot_data, dict):
            try:
                plot_graph = PlotGraph.from_dict(plot_data)
                return _plot_graph_response(plot_graph, project_id)
            except Exception:
                pass
        return PlotGraphData(**PlotGraph().to_dict(), current_volume_goal="")
    plot_graph = get_plot_repository().get_plot_graph(project_id)
    if plot_graph is not None:
        return _plot_graph_response(plot_graph, project_id)
    return PlotGraphData(**PlotGraph().to_dict(), current_volume_goal="")


@router.put("/projects/{project_id}/plot/volume-goal", response_model=PlotGraphData, summary="更新当前卷目标")
async def update_project_plot_volume_goal(
    project_id: str,
    req: PlotVolumeGoalUpdateRequest,
    svc: ProjectService = Depends(_svc),
) -> PlotGraphData:
    mgr = _compat_mgr(project_id, svc)
    handle = svc.try_load_project(project_id)
    if mgr is None and handle is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"detail": f"项目 '{project_id}' 不存在。", "code": "NOT_FOUND"},
        )

    if mgr is not None:
        kb = mgr.load_kb() or {}
        plot_data = kb.get("plot_graph") if isinstance(kb, dict) else None
        plot_graph = PlotGraph.from_dict(plot_data) if isinstance(plot_data, dict) and plot_data else PlotGraph()
    else:
        plot_graph = get_plot_repository().get_plot_graph(project_id) or PlotGraph()
    plot_payload = plot_graph.to_dict()
    nodes = plot_payload.setdefault("nodes", [])
    current_goal = req.current_volume_goal.strip()

    if nodes:
        target_node = next((node for node in nodes if node.get("status") == NodeStatus.ACTIVE.value), nodes[0])
        target_node["summary"] = current_goal
        target_node["status"] = NodeStatus.ACTIVE.value
        target_node.setdefault("type", NodeType.SETUP.value)
        target_node.setdefault("tension", 0.5)
        target_node.setdefault("chapter_ref", 1)
    else:
        nodes.append({
            "id": "volume-goal-1",
            "type": NodeType.SETUP.value,
            "summary": current_goal,
            "tension": 0.5,
            "status": NodeStatus.ACTIVE.value,
            "chapter_ref": 1,
        })

    updated_graph = PlotGraph.from_dict(plot_payload)
    if mgr is not None:
        kb["plot_graph"] = updated_graph.to_dict()
        mgr.save_kb(kb)
    else:
        get_plot_repository().save_plot_graph(project_id, updated_graph)
    return _plot_graph_response(updated_graph, project_id)


@router.get("/projects/{project_id}/characters", response_model=list[CharacterSummary], summary="角色列表摘要")
async def get_project_characters(
    project_id: str, svc: ProjectService = Depends(_svc)
) -> list[CharacterSummary]:
    mgr = _compat_mgr(project_id, svc)
    if mgr is not None:
        kb = mgr.load_kb()
        characters = kb.get("characters", [])
        if not isinstance(characters, list):
            return []
    else:
        characters = get_character_repository().list_character_payloads(project_id)
    return [
        {
            "name": c.get("name", ""),
            "emotion": c.get("emotion", "平静"),
            "health": c.get("health", 100),
            "arc_stage": c.get("arc_stage", ""),
            "faction": c.get("faction", ""),
            "is_alive": c.get("is_alive", True),
        }
        for c in characters
        if isinstance(c, dict)
    ]


@router.get("/projects/{project_id}/characters/{name}", response_model=CharacterDetail, summary="角色详情")
async def get_character_detail(
    project_id: str, name: str, svc: ProjectService = Depends(_svc)
) -> CharacterDetail:
    mgr = _compat_mgr(project_id, svc)
    if mgr is not None:
        kb = mgr.load_kb()
        characters = kb.get("characters", [])
        for c in characters if isinstance(characters, list) else []:
            if isinstance(c, dict) and c.get("name") == name:
                return c
    else:
        payload = get_character_repository().get_character_payload(project_id, name)
        if payload is not None:
            return payload
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"detail": f"角色 '{name}' 不存在。", "code": "NOT_FOUND"},
    )


@router.post("/projects/{project_id}/characters", response_model=CharacterDetail, summary="创建角色")
async def create_character(
    project_id: str,
    req: CharacterCreateRequest,
    svc: ProjectService = Depends(_svc),
) -> CharacterDetail:
    mgr = _compat_mgr(project_id, svc)
    if mgr is None and svc.try_load_project(project_id) is None:
        raise HTTPException(
            status_code=404,
            detail={"detail": "项目不存在", "code": "NOT_FOUND"},
        )
    repo = get_character_repository()
    if mgr is not None:
        kb = mgr.load_kb()
        characters = kb.get("characters", [])
        if not isinstance(characters, list):
            characters = []
    else:
        characters = repo.list_character_payloads(project_id)
    if any(isinstance(c, dict) and c.get("name") == req.name for c in characters):
        raise HTTPException(status_code=409, detail={"detail": f"角色「{req.name}」已存在", "code": "CONFLICT"})
    new_char = req.model_dump()
    new_char.update({
        "emotion": "平静", "health": 1.0, "relationships": {}, "arc_stage": "防御",
        "memory": [], "behavior_constraints": [], "voice_fingerprint": {},
        "snapshot_history": [], "is_alive": True, "chapter_introduced": 1,
    })
    characters.append(new_char)
    if mgr is not None:
        kb["characters"] = characters
        mgr.save_kb(kb)
    else:
        repo.save_character_payloads(project_id, characters)
    return new_char


@router.put("/projects/{project_id}/characters/{name}", response_model=CharacterDetail, summary="更新角色")
async def update_character(
    project_id: str,
    name: str,
    req: dict = Body(...),
    svc: ProjectService = Depends(_svc),
) -> CharacterDetail:
    mgr = _compat_mgr(project_id, svc)
    if mgr is None and svc.try_load_project(project_id) is None:
        raise HTTPException(status_code=404, detail={"detail": "项目不存在", "code": "NOT_FOUND"})
    repo = get_character_repository()
    if mgr is not None:
        kb = mgr.load_kb()
        characters = kb.get("characters", [])
    else:
        characters = repo.list_character_payloads(project_id)
    if not isinstance(characters, list):
        raise HTTPException(status_code=404, detail={"detail": f"角色「{name}」不存在", "code": "NOT_FOUND"})
    for i, c in enumerate(characters):
        if isinstance(c, dict) and c.get("name") == name:
            merged = {**c, **req}
            merged["name"] = name
            characters[i] = merged
            if mgr is not None:
                kb["characters"] = characters
                mgr.save_kb(kb)
            else:
                repo.save_character_payloads(project_id, characters)
            return merged
    raise HTTPException(status_code=404, detail={"detail": f"角色「{name}」不存在", "code": "NOT_FOUND"})


@router.delete("/projects/{project_id}/characters/{name}", response_model=DeleteCharacterResponse, summary="删除角色")
async def delete_character(
    project_id: str, name: str, svc: ProjectService = Depends(_svc)
) -> DeleteCharacterResponse:
    mgr = _compat_mgr(project_id, svc)
    if mgr is None and svc.try_load_project(project_id) is None:
        raise HTTPException(status_code=404, detail={"detail": "项目不存在", "code": "NOT_FOUND"})
    repo = get_character_repository()
    if mgr is not None:
        kb = mgr.load_kb()
        characters = kb.get("characters", [])
    else:
        characters = repo.list_character_payloads(project_id)
    if not isinstance(characters, list):
        raise HTTPException(status_code=404, detail={"detail": f"角色「{name}」不存在", "code": "NOT_FOUND"})
    original_count = len(characters)
    characters = [c for c in characters if not (isinstance(c, dict) and c.get("name") == name)]
    if len(characters) == original_count:
        raise HTTPException(status_code=404, detail={"detail": f"角色「{name}」不存在", "code": "NOT_FOUND"})
    if mgr is not None:
        kb["characters"] = characters
        mgr.save_kb(kb)
    else:
        repo.save_character_payloads(project_id, characters)
    return DeleteCharacterResponse(deleted=name)


@router.post("/projects/{project_id}/characters/{name}/test-voice", response_model=TestVoiceResponse, summary="口吻试戏")
async def test_character_voice(
    project_id: str,
    name: str,
    req: TestVoiceRequest,
    svc: ProjectService = Depends(_svc),
) -> TestVoiceResponse:
    mgr = _compat_mgr(project_id, svc)
    if mgr is None and svc.try_load_project(project_id) is None:
        raise HTTPException(status_code=404, detail={"detail": "项目不存在", "code": "NOT_FOUND"})
    if mgr is not None:
        kb = mgr.load_kb()
        characters = kb.get("characters", [])
        char = next(
            (c for c in characters if isinstance(c, dict) and c.get("name") == name), None
        )
    else:
        char = get_character_repository().get_character_payload(project_id, name)
    if char is None:
        raise HTTPException(status_code=404, detail={"detail": f"角色「{name}」不存在", "code": "NOT_FOUND"})

    vf = char.get("voice_fingerprint", {})
    prompt = "\n\n".join(
        [
            f"你是角色「{char.get('name', name)}」。",
            build_character_voice_block(
                personality=str(char.get("personality", char.get("backstory", ""))),
                speech_style=str(char.get("speech_style", "")),
                catchphrases=char.get("catchphrases", []),
                under_pressure=str(vf.get("under_pressure", "")),
                dialogue_examples=char.get("dialogue_examples", [])[:3],
            ),
            f"当前场景：{req.scenario}",
            plain_text_contract(
                "请以该角色的口吻，用 1-2 句话（可含动作描写）回应当前场景。",
                "直接输出对话，不要前缀。",
            ),
        ]
    )

    from narrative_os.execution.llm_router import LLMRequest, LLMRouter
    r = LLMRouter()
    try:
        llm_req = LLMRequest(
            task_type="voice_test",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.8,
            skill_name="test_voice",
        )
        resp = await r.call(llm_req)
        return TestVoiceResponse(dialogue=resp.content.strip())
    except Exception as e:
        raise HTTPException(status_code=500, detail={"detail": f"生成失败：{e}", "code": "LLM_ERROR"})


# ------------------------------------------------------------------ #
# 四层角色端点                                                          #
# ------------------------------------------------------------------ #


@router.get("/projects/{project_id}/characters/{name}/drive", summary="获取角色Drive层")
async def get_character_drive(project_id: str, name: str) -> dict[str, Any]:
    from narrative_os.core.character_repository import get_character_repository
    char = get_character_repository().get_character(project_id, name)
    if char is None:
        raise HTTPException(status_code=404, detail={"detail": f"角色「{name}」不存在", "code": "NOT_FOUND"})
    if char.drive is None:
        return {}
    return char.drive.model_dump()


@router.put("/projects/{project_id}/characters/{name}/drive", response_model=CharacterDrive, summary="更新角色Drive层")
async def update_character_drive(
    project_id: str, name: str, req: dict = Body(...)
) -> CharacterDrive:
    from narrative_os.core.character_repository import get_character_repository
    from narrative_os.core.character import CharacterDrive
    repo = get_character_repository()
    char = repo.get_character(project_id, name)
    if char is None:
        raise HTTPException(status_code=404, detail={"detail": f"角色「{name}」不存在", "code": "NOT_FOUND"})
    existing = char.drive.model_dump() if char.drive else {}
    merged = {**existing, **req}
    char.drive = CharacterDrive.model_validate(merged)
    repo.save_character(project_id, char)
    return char.drive


@router.put("/projects/{project_id}/characters/{name}/runtime", response_model=CharacterRuntime, summary="更新角色Runtime层")
async def update_character_runtime(
    project_id: str, name: str, req: CharacterRuntimeUpdateRequest
) -> CharacterRuntime:
    from narrative_os.core.character_repository import get_character_repository
    from narrative_os.core.character import CharacterRuntime
    repo = get_character_repository()
    char = repo.get_character(project_id, name)
    if char is None:
        raise HTTPException(status_code=404, detail={"detail": f"角色「{name}」不存在", "code": "NOT_FOUND"})
    existing = char.runtime.model_dump()
    payload = req.model_dump(exclude_none=True)
    if "location" in payload and "current_location" not in payload:
        payload["current_location"] = payload.pop("location")
    if "agenda" in payload and "current_agenda" not in payload:
        payload["current_agenda"] = payload.pop("agenda")
    merged = {**existing, **payload}
    char.runtime = CharacterRuntime.model_validate(merged)
    repo.save_character(project_id, char)
    return char.runtime


@router.get("/projects/{project_id}/characters/{name}/social-matrix", response_model=dict[str, RelationshipProfile], summary="获取Social矩阵")
async def get_character_social_matrix(project_id: str, name: str) -> dict[str, RelationshipProfile]:
    from narrative_os.core.character_repository import get_character_repository
    char = get_character_repository().get_character(project_id, name)
    if char is None:
        raise HTTPException(status_code=404, detail={"detail": f"角色「{name}」不存在", "code": "NOT_FOUND"})
    return {k: v.model_dump() for k, v in char.social_matrix.items()}


@router.put("/projects/{project_id}/characters/{name}/social-matrix", response_model=dict[str, RelationshipProfile], summary="更新Social矩阵")
async def update_character_social_matrix(
    project_id: str, name: str, req: dict = Body(...)
) -> dict[str, RelationshipProfile]:
    from narrative_os.core.character_repository import get_character_repository
    from narrative_os.core.character import RelationshipProfile
    repo = get_character_repository()
    char = repo.get_character(project_id, name)
    if char is None:
        raise HTTPException(status_code=404, detail={"detail": f"角色「{name}」不存在", "code": "NOT_FOUND"})
    new_matrix: dict = {}
    for target, profile_data in req.items():
        if not isinstance(profile_data, dict):
            continue
        profile_data.setdefault("target_name", target)
        new_matrix[target] = RelationshipProfile.model_validate(profile_data)
    char.social_matrix = new_matrix
    for target, profile in new_matrix.items():
        char.relationships[target] = profile.affinity
    repo.save_character(project_id, char)
    return {k: v.model_dump() for k, v in char.social_matrix.items()}
