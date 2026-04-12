"""
core/plot.py — Phase 1: PlotGraph（剧情图）

数据结构：
  PlotNode  — 剧情节点（带张力/节奏/副作用/分支概率）
  PlotEdge  — 有向边（因果/时序/条件）
  StateUpdate — 副作用触发的状态更新指令
  PlotGraph — NetworkX DiGraph 容器（带可视化与张力曲线）

UI 映射：无限画布 → 节点卡片 / 贝塞尔连线 / 张力波形图
"""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Any, Literal

import networkx as nx
from pydantic import BaseModel, Field, field_validator


# ------------------------------------------------------------------ #
# Enums                                                                #
# ------------------------------------------------------------------ #

class PacingType(str, Enum):
    RISING = "rising"
    PEAK = "peak"
    FALLING = "falling"
    BUFFER = "buffer"


class KeyBeat(str, Enum):
    PAYOFF = "爽点"
    TWIST = "转折"
    REVEAL = "信息揭露"
    EMOTIONAL_PEAK = "情感高潮"
    SETUP = "铺垫"
    CONFRONTATION = "正面冲突"


class NodeStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    SKIPPED = "skipped"


class EdgeRelation(str, Enum):
    CAUSAL = "causal"          # 因果
    TEMPORAL = "temporal"      # 时序
    CONDITIONAL = "conditional"  # 条件触发


class NodeType(str, Enum):
    SETUP = "setup"
    CONFLICT = "conflict"
    CLIMAX = "climax"
    RESOLUTION = "resolution"
    TRANSITION = "transition"
    FORESHADOWING = "foreshadowing"
    BRANCH = "branch"


# ------------------------------------------------------------------ #
# Side Effects                                                          #
# ------------------------------------------------------------------ #

class StateUpdate(BaseModel):
    """
    副作用：PlotNode 执行时自动触发的状态更新指令。
    代码硬控，不依赖 LLM 软判断。

    示例：
        StateUpdate(target_type="character", target_id="mc",
                    field="emotion", value="愤怒")
    """
    target_type: Literal["character", "world", "faction"]
    target_id: str
    field: str
    value: Any
    op: Literal["set", "add", "append"] = "set"

    model_config = {"frozen": True}


# ------------------------------------------------------------------ #
# PlotNode                                                              #
# ------------------------------------------------------------------ #

class PlotNode(BaseModel):
    """
    剧情节点 Pydantic V2 模型。

    tension: 0.0 ~ 1.0，UI 张力滑块对应值（冷蓝 → 警红渐变）
    branch_probability: {"branch_id": probability}，轻量条件分支
    """
    id: str
    type: NodeType = NodeType.CONFLICT
    summary: str
    tension: float = Field(default=0.5, ge=0.0, le=1.0)
    pacing_type: PacingType = PacingType.RISING
    key_beat: KeyBeat = KeyBeat.CONFRONTATION
    characters: list[str] = Field(default_factory=list)
    location: str = ""
    status: NodeStatus = NodeStatus.PENDING
    side_effects: list[StateUpdate] = Field(default_factory=list)
    branch_probability: dict[str, float] = Field(default_factory=dict)
    chapter_ref: int | None = None
    notes: str = ""

    @field_validator("branch_probability")
    @classmethod
    def _validate_branch_probs(cls, v: dict[str, float]) -> dict[str, float]:
        if v and abs(sum(v.values()) - 1.0) > 0.01:
            raise ValueError(
                f"branch_probability 概率之和应为 1.0，当前为 {sum(v.values()):.3f}"
            )
        return v

    model_config = {"frozen": False}


# ------------------------------------------------------------------ #
# PlotEdge                                                              #
# ------------------------------------------------------------------ #

class PlotEdge(BaseModel):
    """有向边，连接两个 PlotNode。"""
    from_id: str
    to_id: str
    relation: EdgeRelation = EdgeRelation.CAUSAL
    weight: float = Field(default=1.0, ge=0.0, le=1.0)
    condition: str = ""  # conditional 类型时的条件描述

    model_config = {"frozen": True}


# ------------------------------------------------------------------ #
# PlotGraph                                                             #
# ------------------------------------------------------------------ #

class PlotGraph:
    """
    剧情图 — NetworkX DiGraph 容器。

    核心 API：
        create_event(node)
        link_events(edge)
        get_next_events(node_id) -> list[PlotNode]
        update_event_status(node_id, status)
        get_tension_curve() -> list[tuple[str, float]]
        execute_side_effects(node_id) -> list[StateUpdate]
        visualize(output_path)  — 输出 Graphviz 图
        to_dict() / from_dict() — 序列化/反序列化
    """

    def __init__(self) -> None:
        self._graph: nx.DiGraph = nx.DiGraph()
        self._nodes: dict[str, PlotNode] = {}

    # ---------------------------------------------------------------- #
    # Mutations                                                          #
    # ---------------------------------------------------------------- #

    def create_event(
        self,
        node_or_id: "PlotNode | str",
        *,
        type: "NodeType | None" = None,
        summary: str = "",
        tension: float = 0.5,
        **kwargs: Any,
    ) -> "PlotNode":
        """
        添加剧情节点。

        两种调用方式:
          graph.create_event(PlotNode(...))               → 对象方式
          graph.create_event("A", type=NodeType.SETUP, ...) → 工厂方式
        """
        if isinstance(node_or_id, str):
            node_type = type or NodeType.SETUP
            node = PlotNode(id=node_or_id, type=node_type, summary=summary, tension=tension, **kwargs)
        else:
            node = node_or_id
        if node.id in self._nodes:
            raise ValueError(f"节点 '{node.id}' 已存在")
        self._nodes[node.id] = node
        self._graph.add_node(
            node.id,
            tension=node.tension,
            pacing_type=node.pacing_type.value,
            status=node.status.value,
        )
        return node

    def link_events(
        self,
        edge_or_from: "PlotEdge | str",
        to_id: str | None = None,
        *,
        relation: str = "causal",
        weight: float = 1.0,
        condition: str = "",
    ) -> None:
        """
        连接两个节点（有向边）。

        两种调用方式:
          graph.link_events(PlotEdge(...))               → 对象方式
          graph.link_events("A", "B", relation="causal") → 工厂方式
        """
        if isinstance(edge_or_from, str):
            from_id = edge_or_from
            if to_id is None:
                raise ValueError("link_events() 工厂模式需要 to_id 参数")
            try:
                rel = EdgeRelation(relation)
            except ValueError:
                rel = EdgeRelation.CAUSAL
            edge = PlotEdge(from_id=from_id, to_id=to_id, relation=rel, weight=weight, condition=condition)
        else:
            edge = edge_or_from
        if edge.from_id not in self._nodes:
            raise KeyError(f"源节点 '{edge.from_id}' 不存在")
        if edge.to_id not in self._nodes:
            raise KeyError(f"目标节点 '{edge.to_id}' 不存在")
        self._graph.add_edge(
            edge.from_id,
            edge.to_id,
            relation=edge.relation.value if hasattr(edge.relation, 'value') else edge.relation,
            weight=edge.weight,
            condition=edge.condition,
        )

    def update_event_status(self, node_id: str, status: NodeStatus) -> None:
        """更新节点状态（pending → active → completed）。"""
        if node_id not in self._nodes:
            raise KeyError(f"Node '{node_id}' not found")
        node = self._nodes[node_id]
        object.__setattr__(node, "status", status) if node.model_config.get("frozen") else setattr(node, "status", status)
        self._graph.nodes[node_id]["status"] = status.value

    def execute_side_effects(self, node_id: str) -> list[StateUpdate]:
        """
        返回该节点的所有副作用指令。
        调用方（Maintenance Agent）负责将这些指令应用到 CharacterState / WorldState。
        """
        node = self._get_node(node_id)
        return list(node.side_effects)

    # ---------------------------------------------------------------- #
    # Queries                                                            #
    # ---------------------------------------------------------------- #

    def get_next_events(self, node_id: str) -> list[PlotNode]:
        """返回指定节点的所有后续节点（有向邻居）。"""
        if node_id not in self._graph:
            return []
        return [self._nodes[nid] for nid in self._graph.successors(node_id)]

    def get_pending_events(self) -> list[PlotNode]:
        """返回所有 pending 状态的节点（待执行）。"""
        return [n for n in self._nodes.values() if n.status == NodeStatus.PENDING]

    def get_current_volume_goal(self, project_id: str | None = None) -> str:
        """返回当前卷的主目标摘要。"""
        del project_id  # 保留阶段五约定签名

        active_nodes = [
            node for node in self._nodes.values() if node.status == NodeStatus.ACTIVE
        ]
        if active_nodes:
            return "；".join(node.summary for node in active_nodes[:3] if node.summary)

        pending_nodes = self.get_pending_events()
        pending_nodes.sort(
            key=lambda node: (
                node.chapter_ref if node.chapter_ref is not None else 10**9,
                -node.tension,
            )
        )
        if pending_nodes:
            return pending_nodes[0].summary

        curve = self.get_tension_curve()
        if curve:
            peak_node_id = max(curve, key=lambda item: item[1])[0]
            peak_node = self._nodes.get(peak_node_id)
            if peak_node is not None:
                return peak_node.summary

        return ""

    def activate_next_nodes(self, completed_node_ids: list[str]) -> list[str]:
        """将已完成节点的直接后继激活。"""
        activated: list[str] = []
        for node_id in completed_node_ids:
            if node_id not in self._graph:
                continue
            for next_id in self._graph.successors(node_id):
                next_node = self._nodes.get(next_id)
                if next_node is None or next_node.status != NodeStatus.PENDING:
                    continue
                self.update_event_status(next_id, NodeStatus.ACTIVE)
                activated.append(next_id)
        return activated

    def get_tension_curve(self) -> list[tuple[str, float]]:
        """
        返回所有节点按拓扑排序的 (node_id, tension) 序列。
        UI 映射：横轴章节进度 / 纵轴张力值波形图。
        """
        try:
            order = list(nx.topological_sort(self._graph))
        except nx.NetworkXUnfeasible:
            order = list(self._nodes.keys())
        return [(nid, self._nodes[nid].tension) for nid in order if nid in self._nodes]

    def has_node(self, node_id: str) -> bool:
        return node_id in self._nodes

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    @property
    def edge_count(self) -> int:
        return self._graph.number_of_edges()

    # ---------------------------------------------------------------- #
    # Visualization                                                       #
    # ---------------------------------------------------------------- #

    def visualize(self, output_path: str | Path | None = None) -> str:
        """
        使用 NetworkX 输出 Graphviz DOT 格式字符串，并可选写入文件。
        UI 映射：剧情图谱无限画布的底层图数据。
        """
        try:
            from networkx.drawing.nx_pydot import to_pydot  # type: ignore
            pydot_graph = to_pydot(self._graph)
            # 给每个节点着色（张力值 → 颜色深度）
            for node in pydot_graph.get_nodes():
                nid = node.get_name().strip('"')
                if nid in self._nodes:
                    t = self._nodes[nid].tension
                    # 冷蓝(低张力) → 警红(高张力)
                    r = int(255 * t)
                    b = int(255 * (1 - t))
                    node.set_fillcolor(f"#{r:02x}00{b:02x}")
                    node.set_style("filled")
            dot_str = pydot_graph.to_string()
        except ImportError:
            # fallback: 简单 DOT 格式
            lines = ["digraph PlotGraph {"]
            for nid, node in self._nodes.items():
                label = f"{nid}\\n{node.summary[:20]}\\n张力:{node.tension:.1f}"
                lines.append(f'  "{nid}" [label="{label}"]')
            for u, v, data in self._graph.edges(data=True):
                lines.append(f'  "{u}" -> "{v}" [label="{data.get("relation","")}"]')
            lines.append("}")
            dot_str = "\n".join(lines)

        if output_path is not None:
            Path(output_path).write_text(dot_str, encoding="utf-8")
        return dot_str

    # ---------------------------------------------------------------- #
    # Serialization                                                       #
    # ---------------------------------------------------------------- #

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": [n.model_dump() for n in self._nodes.values()],
            "edges": [
                {
                    "from_id": u,
                    "to_id": v,
                    "relation": data.get("relation"),
                    "weight": data.get("weight", 1.0),
                    "condition": data.get("condition", ""),
                }
                for u, v, data in self._graph.edges(data=True)
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PlotGraph":
        graph = cls()
        for nd in data.get("nodes", []):
            graph.create_event(PlotNode(**nd))
        for ed in data.get("edges", []):
            graph.link_events(PlotEdge(**ed))
        return graph

    def to_json(self, path: str | Path | None = None) -> str:
        s = json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
        if path:
            Path(path).write_text(s, encoding="utf-8")
        return s

    @classmethod
    def from_json(cls, json_str_or_path: str | Path) -> "PlotGraph":
        p = Path(json_str_or_path)
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
        else:
            data = json.loads(str(json_str_or_path))  # treat as JSON string
        return cls.from_dict(data)

    # ---------------------------------------------------------------- #
    # Helpers                                                            #
    # ---------------------------------------------------------------- #

    def _get_node(self, node_id: str) -> PlotNode:
        if node_id not in self._nodes:
            raise KeyError(f"Node '{node_id}' not found")
        return self._nodes[node_id]

    def get_node(self, node_id: str) -> PlotNode:
        """Public alias for _get_node — raises KeyError if not found."""
        return self._get_node(node_id)

    def __repr__(self) -> str:
        return f"PlotGraph(nodes={self.node_count}, edges={self.edge_count})"
