"""
interface/api.py — Phase 2: 路由组装文件（精简至 ~200 行）

将 ~3,800 行的单体 api.py 收敛为 FastAPI APIRouter 子模块组装，
消除"路由即业务逻辑"的结构债。

架构：
  narrative_os/interface/
    ├── api.py                  ← 本文件：组装入口
    ├── routers/
    │   ├── world.py            世界沙盒 + AI 辅助路由
    │   ├── characters.py       角色 CRUD + 四层系统
    │   ├── trpg.py             TRPG 会话 + SL + WebSocket
    │   ├── chapters.py         章节生成 + 质量指标
    │   ├── projects.py         项目 CRUD + 成本 + Settings
    │   ├── memory.py           记忆搜索
    │   ├── settings.py         LLM 提供商配置
    │   ├── governance.py       变更集 / 正史提交（Phase 1）
    │   └── traces.py           链路追踪 + 插件 + 风格 + WorldBuilder
    └── services/
        ├── world_service.py
        ├── project_service.py
        ├── trpg_service.py
        └── ...
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from narrative_os import __version__
from narrative_os.infra.database import init_db

# ------------------------------------------------------------------ #
# 向后兼容别名：旧测试直接从 api 导入这些符号                            #
# ------------------------------------------------------------------ #

# TRPG 会话存储（来自 services/trpg_service.py）
from narrative_os.interface.services.trpg_service import (  # noqa: F401
    _sessions,
    _sessions_lock,
    SESSION_TTL_SECONDS,
    _cleanup_stale_sessions,
    _get_session,
    get_interactive_agent,
)

_interactive_agent = get_interactive_agent()

# WorldBuilder + 插件注册表存储（来自 routers/traces.py）
from narrative_os.interface.routers.traces import (  # noqa: F401
    _wb_sessions,
    _wb_sessions_lock,
    _plugin_registry,
    _plugin_lock,
)

# 可被测试 patch 的共享类引用（旧测试通过 patch("narrative_os.interface.api.X") 注入 mock）
from narrative_os.core.state import StateManager  # noqa: F401
from narrative_os.core.memory import MemorySystem  # noqa: F401
from narrative_os.skills.consistency import ConsistencyChecker  # noqa: F401
from narrative_os.infra.database import AsyncSessionLocal  # noqa: F401
from narrative_os.infra.cost import cost_ctrl  # noqa: F401
from narrative_os.core.world_builder import WorldBuilder  # noqa: F401
from narrative_os.agents.planner import PlannerAgent  # noqa: F401
from narrative_os.orchestrator.graph import run_chapter  # noqa: F401


# 可被测试 patch 的工具函数（旧测试通过 patch("narrative_os.interface.api._load_project_or_404") 注入）
def _load_project_or_404(project_id: str) -> "StateManager":  # type: ignore[name-defined]
    """加载项目状态，不存在时抛出 404（向后兼容别名）。"""
    from narrative_os.interface.services.project_service import get_project_service
    return get_project_service().load_project_or_404(project_id)


def _try_load_project(project_id: str) -> "StateManager | None":  # type: ignore[name-defined]
    """尝试加载项目状态（向后兼容别名）。"""
    from narrative_os.interface.services.project_service import get_project_service
    return get_project_service().try_load_project(project_id)


async def _get_sandbox(project_id: str, db=None) -> "object":  # type: ignore[misc]
    """向后兼容别名：获取世界沙盘数据（测试可 patch）。"""
    from narrative_os.interface.routers.world import _get_world_svc
    svc = _get_world_svc()
    if db is None:
        async with AsyncSessionLocal() as _db:
            return await svc.get_sandbox(project_id, _db)
    return await svc.get_sandbox(project_id, db)


async def _get_concept(project_id: str, db=None) -> "object":  # type: ignore[misc]
    """向后兼容别名：获取故事概念数据（测试可 patch）。"""
    from narrative_os.interface.routers.world import _get_world_svc
    svc = _get_world_svc()
    if db is None:
        async with AsyncSessionLocal() as _db:
            return await svc.get_concept(project_id, _db)
    return await svc.get_concept(project_id, db)


# ------------------------------------------------------------------ #
# FastAPI 应用 + 生命周期                                               #
# ------------------------------------------------------------------ #


@asynccontextmanager
async def _lifespan(app: FastAPI):  # type: ignore[type-arg]
    """应用启动时初始化 DB，关闭时清理（预留）。"""
    await init_db()
    yield


app = FastAPI(
    title="Narrative OS API",
    description="可编程叙事操作系统 REST API",
    version=__version__,
    lifespan=_lifespan,
)

# ------------------------------------------------------------------ #
# 请求追踪中间件                                                        #
# ------------------------------------------------------------------ #


@app.middleware("http")
async def _inject_correlation_id(request: Request, call_next):  # type: ignore[type-arg]
    """为每个请求生成 correlation_id，注入日志上下文并添加到响应头。"""
    from narrative_os.infra.logging import set_correlation_id
    cid = uuid.uuid4().hex[:8]
    set_correlation_id(cid)
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = cid
    return response


# ------------------------------------------------------------------ #
# 路由注册                                                              #
# ------------------------------------------------------------------ #

from narrative_os.interface.routers import (  # noqa: E402
    world,
    characters,
    trpg,
    chapters,
    projects,
    benchmark,
    memory,
    settings,
    governance,
    traces,
)

app.include_router(world.router)
app.include_router(characters.router)
app.include_router(trpg.router)
app.include_router(chapters.router)
app.include_router(projects.router)
app.include_router(benchmark.router)
app.include_router(memory.router)
app.include_router(settings.router)
app.include_router(governance.router)
app.include_router(traces.router)


# ------------------------------------------------------------------ #
# 直接挂载的轻量端点                                                    #
# ------------------------------------------------------------------ #


@app.get("/health", summary="健康检查")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": app.version}


