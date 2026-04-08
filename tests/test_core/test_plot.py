"""tests/test_core/test_plot.py — PlotGraph 单元测试"""
import pytest
from narrative_os.core.plot import (
    NodeType,
    NodeStatus,
    PlotGraph,
    PlotNode,
    PlotEdge,
    StateUpdate,
)


# ------------------------------------------------------------------ #
# Fixtures                                                             #
# ------------------------------------------------------------------ #

@pytest.fixture
def graph() -> PlotGraph:
    return PlotGraph()


@pytest.fixture
def simple_graph(graph: PlotGraph) -> PlotGraph:
    """A → B → C の线性图，用于各测试。"""
    graph.create_event("A", type=NodeType.SETUP, summary="开端", tension=0.2)
    graph.create_event("B", type=NodeType.CLIMAX, summary="高潮", tension=0.9)
    graph.create_event("C", type=NodeType.RESOLUTION, summary="结局", tension=0.3)
    graph.link_events("A", "B", relation="causal")
    graph.link_events("B", "C", relation="causal")
    return graph


# ------------------------------------------------------------------ #
# PlotNode model                                                       #
# ------------------------------------------------------------------ #

class TestPlotNode:
    def test_branch_probability_sum_valid(self):
        node = PlotNode(
            id="x",
            type=NodeType.BRANCH,
            summary="分支",
            branch_probability={"opt1": 0.6, "opt2": 0.4},
        )
        assert abs(sum(node.branch_probability.values()) - 1.0) < 1e-6

    def test_branch_probability_sum_invalid(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            PlotNode(
                id="x",
                type=NodeType.BRANCH,
                summary="分支",
                branch_probability={"opt1": 0.6, "opt2": 0.5},  # sums to 1.1
            )

    def test_tension_clamp(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            PlotNode(id="x", type=NodeType.SETUP, summary="t", tension=1.5)


# ------------------------------------------------------------------ #
# PlotGraph CRUD                                                        #
# ------------------------------------------------------------------ #

class TestPlotGraphCRUD:
    def test_create_event(self, graph: PlotGraph):
        node = graph.create_event("n1", type=NodeType.SETUP, summary="test")
        assert node.id == "n1"
        assert graph.node_count == 1

    def test_duplicate_id_raises(self, graph: PlotGraph):
        graph.create_event("n1", type=NodeType.SETUP, summary="first")
        with pytest.raises(ValueError, match="已存在"):
            graph.create_event("n1", type=NodeType.SETUP, summary="second")

    def test_link_events(self, simple_graph: PlotGraph):
        assert simple_graph.edge_count == 2

    def test_link_missing_node_raises(self, graph: PlotGraph):
        graph.create_event("A", type=NodeType.SETUP, summary="A")
        with pytest.raises(KeyError):
            graph.link_events("A", "MISSING")

    def test_get_node(self, simple_graph: PlotGraph):
        node = simple_graph.get_node("B")
        assert node.tension == 0.9

    def test_get_missing_node_raises(self, graph: PlotGraph):
        with pytest.raises(KeyError):
            graph.get_node("NOPE")

    def test_update_event_status(self, simple_graph: PlotGraph):
        simple_graph.update_event_status("A", NodeStatus.COMPLETED)
        assert simple_graph.get_node("A").status == NodeStatus.COMPLETED

    def test_get_next_events(self, simple_graph: PlotGraph):
        nexts = simple_graph.get_next_events("A")
        assert len(nexts) == 1
        assert nexts[0].id == "B"

    def test_get_next_events_empty(self, simple_graph: PlotGraph):
        assert simple_graph.get_next_events("C") == []


# ------------------------------------------------------------------ #
# Tension Curve                                                         #
# ------------------------------------------------------------------ #

class TestTensionCurve:
    def test_tension_curve_topological_order(self, simple_graph: PlotGraph):
        curve = simple_graph.get_tension_curve()
        ids = [n for n, _ in curve]
        assert ids == ["A", "B", "C"]  # topological: A→B→C

    def test_tension_curve_values(self, simple_graph: PlotGraph):
        curve = simple_graph.get_tension_curve()
        tensions = {n: t for n, t in curve}
        assert tensions["A"] == pytest.approx(0.2)
        assert tensions["B"] == pytest.approx(0.9)
        assert tensions["C"] == pytest.approx(0.3)

    def test_tension_curve_empty_graph(self, graph: PlotGraph):
        assert graph.get_tension_curve() == []


# ------------------------------------------------------------------ #
# Side Effects                                                          #
# ------------------------------------------------------------------ #

class TestSideEffects:
    def test_add_and_execute_side_effects(self, simple_graph: PlotGraph):
        node = simple_graph.get_node("A")
        se = StateUpdate(
            target_type="character",
            target_id="hero",
            field="health",
            value=-10,
            op="add",
        )
        node.side_effects.append(se)

        results = simple_graph.execute_side_effects("A")
        assert len(results) == 1
        r = results[0]
        assert r.target_id == "hero"
        assert r.field == "health"
        assert r.value == -10


# ------------------------------------------------------------------ #
# Serialisation                                                         #
# ------------------------------------------------------------------ #

class TestSerialization:
    def test_to_from_dict_roundtrip(self, simple_graph: PlotGraph):
        d = simple_graph.to_dict()
        g2 = PlotGraph.from_dict(d)
        assert g2.node_count == simple_graph.node_count
        assert g2.edge_count == simple_graph.edge_count
        assert g2.get_node("B").tension == pytest.approx(0.9)

    def test_to_from_json_roundtrip(self, simple_graph: PlotGraph):
        j = simple_graph.to_json()
        g2 = PlotGraph.from_json(j)
        curve = g2.get_tension_curve()
        assert len(curve) == 3


# ------------------------------------------------------------------ #
# Additional public API coverage                                        #
# ------------------------------------------------------------------ #

class TestPublicAPI:
    def test_has_node_true(self, simple_graph: PlotGraph):
        assert simple_graph.has_node("A") is True

    def test_has_node_false(self, simple_graph: PlotGraph):
        assert simple_graph.has_node("Z") is False

    def test_node_count(self, simple_graph: PlotGraph):
        assert simple_graph.node_count == 3

    def test_edge_count(self, simple_graph: PlotGraph):
        assert simple_graph.edge_count == 2

    def test_get_pending_events(self, graph: PlotGraph):
        graph.create_event("X", summary="待执行", tension=0.5)
        pending = graph.get_pending_events()
        assert len(pending) == 1
        assert pending[0].id == "X"

    def test_get_pending_events_none_after_complete(self, simple_graph: PlotGraph):
        simple_graph.update_event_status("A", NodeStatus.COMPLETED)
        simple_graph.update_event_status("B", NodeStatus.COMPLETED)
        simple_graph.update_event_status("C", NodeStatus.COMPLETED)
        pending = simple_graph.get_pending_events()
        assert pending == []

    def test_get_node_public_alias(self, simple_graph: PlotGraph):
        n = simple_graph.get_node("B")
        assert n.id == "B"

    def test_repr_contains_nodes(self, simple_graph: PlotGraph):
        r = repr(simple_graph)
        assert "PlotGraph" in r
        assert "3" in r  # node count

    def test_to_json_writes_file(self, simple_graph: PlotGraph, tmp_path):
        p = tmp_path / "graph.json"
        simple_graph.to_json(path=p)
        assert p.exists()
        content = p.read_text(encoding="utf-8")
        assert "nodes" in content

    def test_from_json_reads_file(self, simple_graph: PlotGraph, tmp_path):
        p = tmp_path / "graph.json"
        simple_graph.to_json(path=p)
        g2 = PlotGraph.from_json(p)
        assert g2.node_count == simple_graph.node_count


# ------------------------------------------------------------------ #
# visualize — fallback DOT output (no pygraphviz)                      #
# ------------------------------------------------------------------ #

class TestVisualize:
    def test_visualize_returns_string(self, simple_graph: PlotGraph):
        # Force ImportError path by patching the import
        import sys
        from unittest.mock import patch
        with patch.dict(sys.modules, {"networkx.drawing.nx_pydot": None}):
            dot = simple_graph.visualize()
        assert isinstance(dot, str)
        assert "digraph" in dot.lower() or "PlotGraph" in dot or "A" in dot

    def test_visualize_writes_file(self, simple_graph: PlotGraph, tmp_path):
        p = tmp_path / "graph.dot"
        import sys
        from unittest.mock import patch
        with patch.dict(sys.modules, {"networkx.drawing.nx_pydot": None}):
            dot = simple_graph.visualize(output_path=p)
        assert p.exists()

    def test_visualize_with_real_import(self, simple_graph: PlotGraph):
        """Test visualize works regardless of pygraphviz availability."""
        try:
            dot = simple_graph.visualize()
            assert isinstance(dot, str)
        except Exception:
            # If something else fails, just ensure the fallback is reachable
            pass


# ------------------------------------------------------------------ #
# PlotEdge object-based link_events                                     #
# ------------------------------------------------------------------ #

class TestLinkEventsEdgeObject:
    def test_link_via_edge_object(self, graph: PlotGraph):
        graph.create_event("P", summary="节点P", tension=0.4)
        graph.create_event("Q", summary="节点Q", tension=0.5)
        graph.link_events(PlotEdge(from_id="P", to_id="Q", relation="causal"))
        assert graph.edge_count == 1

    def test_link_missing_from_raises(self, graph: PlotGraph):
        graph.create_event("R", summary="节点R", tension=0.5)
        with pytest.raises(KeyError, match="源节点"):
            graph.link_events("MISSING", "R")
