from __future__ import annotations

import asyncio

from narrative_os.core.character import CharacterState
from narrative_os.core.character_repository import CharacterRepository
from narrative_os.core.plot import NodeStatus, NodeType, PlotGraph
from narrative_os.core.plot_repository import PlotRepository
from narrative_os.core.world import FactionState, WorldState
from narrative_os.core.world_repository import WorldRepository
from narrative_os.infra.config import settings
from narrative_os.infra.database import init_db


def _configure_state_dir(tmp_path, monkeypatch):
    state_dir = tmp_path / "state"
    monkeypatch.setattr(settings, "state_dir", str(state_dir))
    monkeypatch.delenv("NARRATIVE_DB_URL", raising=False)
    asyncio.run(init_db())
    return state_dir


def test_plot_repository_reads_db_snapshot_after_kb_delete(tmp_path, monkeypatch):
    state_dir = _configure_state_dir(tmp_path, monkeypatch)
    repo = PlotRepository()

    graph = PlotGraph.from_dict(
        {
            "nodes": [
                {
                    "id": "goal-1",
                    "type": NodeType.SETUP.value,
                    "summary": "卷一：进入黑石镇",
                    "tension": 0.5,
                    "status": NodeStatus.ACTIVE.value,
                    "chapter_ref": 1,
                }
            ],
            "edges": [],
        }
    )
    repo.save_plot_graph("proj_plot", graph)

    kb_path = state_dir / "proj_plot" / "knowledge_base.json"
    kb_path.unlink()

    loaded = repo.get_plot_graph("proj_plot")
    assert loaded is not None
    assert loaded.get_current_volume_goal("proj_plot") == "卷一：进入黑石镇"


def test_character_repository_reads_db_snapshot_after_kb_delete(tmp_path, monkeypatch):
    state_dir = _configure_state_dir(tmp_path, monkeypatch)
    repo = CharacterRepository()

    repo.save_character("proj_char", CharacterState(name="林枫", arc_stage="觉醒"))

    kb_path = state_dir / "proj_char" / "knowledge_base.json"
    kb_path.unlink()

    chars = repo.list_characters("proj_char")
    assert len(chars) == 1
    assert chars[0].name == "林枫"
    assert chars[0].arc_stage == "觉醒"


def test_world_repository_reads_db_runtime_after_kb_delete(tmp_path, monkeypatch):
    state_dir = _configure_state_dir(tmp_path, monkeypatch)
    repo = WorldRepository()

    world = WorldState()
    world.factions["f1"] = FactionState(id="f1", name="正道")
    repo.save_runtime_world_state("proj_world", world)

    kb_path = state_dir / "proj_world" / "knowledge_base.json"
    kb_path.unlink()

    loaded = repo.get_published_world_state("proj_world")
    assert loaded is not None
    assert "f1" in loaded.factions
    assert loaded.factions["f1"].name == "正道"
