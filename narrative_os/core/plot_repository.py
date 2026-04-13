from __future__ import annotations

import json
from pathlib import Path

from narrative_os.core.plot import PlotGraph
from narrative_os.core.state_snapshot_store import load_runtime_snapshot_payload, save_runtime_snapshot_payload
from narrative_os.infra.config import settings


class PlotRepository:
    def __init__(self) -> None:
        self._state_root = Path(settings.state_dir)

    def get_plot_graph(self, project_id: str) -> PlotGraph | None:
        snapshot = None
        if self._state_root == Path(settings.state_dir):
            snapshot = load_runtime_snapshot_payload(project_id)
        if snapshot is not None:
            plot_data = snapshot.get("plot_graph")
            if isinstance(plot_data, dict) and plot_data:
                try:
                    return PlotGraph.from_dict(plot_data)
                except Exception:
                    pass

        kb_path = self._state_root / project_id / "knowledge_base.json"
        if not kb_path.exists():
            return None
        try:
            kb = json.loads(kb_path.read_text(encoding="utf-8"))
        except Exception:
            return None
        plot_data = kb.get("plot_graph")
        if not isinstance(plot_data, dict) or not plot_data:
            return None
        try:
            return PlotGraph.from_dict(plot_data)
        except Exception:
            return None

    def save_plot_graph(self, project_id: str, plot_graph: PlotGraph) -> None:
        payload = plot_graph.to_dict()
        if self._state_root == Path(settings.state_dir):
            save_runtime_snapshot_payload(project_id, plot_graph=payload)

        kb_path = self._state_root / project_id / "knowledge_base.json"
        if kb_path.exists():
            try:
                kb = json.loads(kb_path.read_text(encoding="utf-8"))
            except Exception:
                kb = {}
        else:
            kb_path.parent.mkdir(parents=True, exist_ok=True)
            kb = {}
        kb["plot_graph"] = payload
        kb_path.write_text(json.dumps(kb, ensure_ascii=False, indent=2), encoding="utf-8")


_repo: PlotRepository | None = None


def get_plot_repository() -> PlotRepository:
    global _repo
    if _repo is None:
        _repo = PlotRepository()
    return _repo