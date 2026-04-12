"""routers/characters.py — 角色管理路由模块。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, status

from narrative_os.core.state import StateManager
from narrative_os.schemas.characters import (
    CharacterCreateRequest,
    CharacterDetail,
    CharacterDrive,
    CharacterRuntime,
    CharacterRuntimeUpdateRequest,
    CharacterSummary,
    DeleteCharacterResponse,
    PlotGraphData,
    RelationshipProfile,
    TestVoiceRequest,
    TestVoiceResponse,
)
from narrative_os.interface.services.project_service import ProjectService, get_project_service

router = APIRouter(tags=["characters"])


def _svc() -> ProjectService:
    return get_project_service()


# ------------------------------------------------------------------ #
# C2: 角色列表 + 详情（基于 KB）                                         #
# ------------------------------------------------------------------ #


@router.get("/projects/{project_id}/plot", response_model=PlotGraphData, summary="获取项目情节图")
async def get_project_plot(
    project_id: str, svc: ProjectService = Depends(_svc)
) -> PlotGraphData:
    import sys
    from narrative_os.core.plot import PlotGraph
    _api = sys.modules.get("narrative_os.interface.api")
    _try = getattr(_api, "_try_load_project", None) if _api else None
    mgr = _try(project_id) if _try else svc.try_load_project(project_id)
    if mgr is not None:
        kb = mgr.load_kb()
        plot_data = kb.get("plot_graph")
        if plot_data and isinstance(plot_data, dict):
            try:
                return PlotGraph.from_dict(plot_data).to_dict()
            except Exception:
                pass
    return PlotGraph().to_dict()


@router.get("/projects/{project_id}/characters", response_model=list[CharacterSummary], summary="角色列表摘要")
async def get_project_characters(
    project_id: str, svc: ProjectService = Depends(_svc)
) -> list[CharacterSummary]:
    import sys
    _api = sys.modules.get("narrative_os.interface.api")
    _try = getattr(_api, "_try_load_project", None) if _api else None
    mgr = _try(project_id) if _try else svc.try_load_project(project_id)
    if mgr is None:
        return []
    kb = mgr.load_kb()
    characters = kb.get("characters", [])
    if not isinstance(characters, list):
        return []
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
    import sys
    _api = sys.modules.get("narrative_os.interface.api")
    _try = getattr(_api, "_try_load_project", None) if _api else None
    mgr = _try(project_id) if _try else svc.try_load_project(project_id)
    if mgr is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"detail": f"角色 '{name}' 不存在。", "code": "NOT_FOUND"},
        )
    kb = mgr.load_kb()
    characters = kb.get("characters", [])
    for c in characters if isinstance(characters, list) else []:
        if isinstance(c, dict) and c.get("name") == name:
            return c
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"detail": f"角色 '{name}' 不存在。", "code": "NOT_FOUND"},
    )


# ------------------------------------------------------------------ #
# Character CRUD                                                        #
# ------------------------------------------------------------------ #


@router.post("/projects/{project_id}/characters", response_model=CharacterDetail, summary="创建角色")
async def create_character(
    project_id: str,
    req: CharacterCreateRequest,
    svc: ProjectService = Depends(_svc),
) -> CharacterDetail:
    import sys
    _api = sys.modules.get("narrative_os.interface.api")
    _try = getattr(_api, "_try_load_project", None) if _api else None
    mgr = _try(project_id) if _try else svc.try_load_project(project_id)
    if mgr is None:
        raise HTTPException(status_code=404, detail={"detail": "项目不存在", "code": "NOT_FOUND"})
    kb = mgr.load_kb()
    characters = kb.get("characters", [])
    if not isinstance(characters, list):
        characters = []
    if any(isinstance(c, dict) and c.get("name") == req.name for c in characters):
        raise HTTPException(status_code=409, detail={"detail": f"角色「{req.name}」已存在", "code": "CONFLICT"})
    new_char = req.model_dump()
    new_char.update({
        "emotion": "平静", "health": 1.0, "relationships": {}, "arc_stage": "防御",
        "memory": [], "behavior_constraints": [], "voice_fingerprint": {},
        "snapshot_history": [], "is_alive": True, "chapter_introduced": 1,
    })
    characters.append(new_char)
    kb["characters"] = characters
    mgr.save_kb(kb)
    return new_char


@router.put("/projects/{project_id}/characters/{name}", response_model=CharacterDetail, summary="更新角色")
async def update_character(
    project_id: str,
    name: str,
    req: dict = Body(...),
    svc: ProjectService = Depends(_svc),
) -> CharacterDetail:
    import sys
    _api = sys.modules.get("narrative_os.interface.api")
    _try = getattr(_api, "_try_load_project", None) if _api else None
    mgr = _try(project_id) if _try else svc.try_load_project(project_id)
    if mgr is None:
        raise HTTPException(status_code=404, detail={"detail": "项目不存在", "code": "NOT_FOUND"})
    kb = mgr.load_kb()
    characters = kb.get("characters", [])
    if not isinstance(characters, list):
        raise HTTPException(status_code=404, detail={"detail": f"角色「{name}」不存在", "code": "NOT_FOUND"})
    for i, c in enumerate(characters):
        if isinstance(c, dict) and c.get("name") == name:
            merged = {**c, **req}
            merged["name"] = name
            characters[i] = merged
            kb["characters"] = characters
            mgr.save_kb(kb)
            return merged
    raise HTTPException(status_code=404, detail={"detail": f"角色「{name}」不存在", "code": "NOT_FOUND"})


@router.delete("/projects/{project_id}/characters/{name}", response_model=DeleteCharacterResponse, summary="删除角色")
async def delete_character(
    project_id: str, name: str, svc: ProjectService = Depends(_svc)
) -> DeleteCharacterResponse:
    import sys
    _api = sys.modules.get("narrative_os.interface.api")
    _try = getattr(_api, "_try_load_project", None) if _api else None
    mgr = _try(project_id) if _try else svc.try_load_project(project_id)
    if mgr is None:
        raise HTTPException(status_code=404, detail={"detail": "项目不存在", "code": "NOT_FOUND"})
    kb = mgr.load_kb()
    characters = kb.get("characters", [])
    if not isinstance(characters, list):
        raise HTTPException(status_code=404, detail={"detail": f"角色「{name}」不存在", "code": "NOT_FOUND"})
    original_count = len(characters)
    characters = [c for c in characters if not (isinstance(c, dict) and c.get("name") == name)]
    if len(characters) == original_count:
        raise HTTPException(status_code=404, detail={"detail": f"角色「{name}」不存在", "code": "NOT_FOUND"})
    kb["characters"] = characters
    mgr.save_kb(kb)
    return DeleteCharacterResponse(deleted=name)


@router.post("/projects/{project_id}/characters/{name}/test-voice", response_model=TestVoiceResponse, summary="口吻试戏")
async def test_character_voice(
    project_id: str,
    name: str,
    req: TestVoiceRequest,
    svc: ProjectService = Depends(_svc),
) -> TestVoiceResponse:
    import sys
    _api = sys.modules.get("narrative_os.interface.api")
    _try = getattr(_api, "_try_load_project", None) if _api else None
    mgr = _try(project_id) if _try else svc.try_load_project(project_id)
    if mgr is None:
        raise HTTPException(status_code=404, detail={"detail": "项目不存在", "code": "NOT_FOUND"})
    kb = mgr.load_kb()
    characters = kb.get("characters", [])
    char = next(
        (c for c in characters if isinstance(c, dict) and c.get("name") == name), None
    )
    if char is None:
        raise HTTPException(status_code=404, detail={"detail": f"角色「{name}」不存在", "code": "NOT_FOUND"})

    vf = char.get("voice_fingerprint", {})
    examples = char.get("dialogue_examples", [])
    examples_text = "\n".join(
        f'[{e.get("context", "")}] {e.get("dialogue", "")}' for e in examples[:3]
    ) if examples else "（无示例）"

    prompt = (
        f"你是角色「{char.get('name', name)}」。\n"
        f"性格：{char.get('personality', char.get('backstory', ''))}\n"
        f"语言风格：{char.get('speech_style', '自然')}\n"
        f"口头禅：{'、'.join(char.get('catchphrases', [])) or '无'}\n"
        f"高压时的说话方式：{vf.get('under_pressure', '') or '无特殊表现'}\n"
        f"历史对话示例：\n{examples_text}\n\n"
        f"当前场景：{req.scenario}\n"
        f"请以该角色的口吻，用 1-2 句话（可含动作描写）回应当前场景。直接输出对话，无需前缀。"
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
