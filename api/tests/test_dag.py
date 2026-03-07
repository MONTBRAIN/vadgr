"""Tests for DAG validation, topological sort, and input resolution.

RED phase -- these tests define the expected behavior of engine/dag.py.
"""

import pytest

from api.engine.dag import DAG


class TestDAGValidation:
    """Cycle detection and structural validation."""

    def test_empty_dag_is_valid(self):
        dag = DAG(nodes=[], edges=[])
        errors = dag.validate()
        assert errors == []

    def test_single_node_no_edges_is_valid(self, make_node):
        dag = DAG(nodes=[make_node("A")], edges=[])
        errors = dag.validate()
        assert errors == []

    def test_linear_chain_is_valid(self, make_node, make_edge):
        nodes = [make_node("A"), make_node("B"), make_node("C")]
        edges = [make_edge("A", "B"), make_edge("B", "C")]
        dag = DAG(nodes=nodes, edges=edges)
        errors = dag.validate()
        assert errors == []

    def test_two_node_cycle_detected(self, make_node, make_edge):
        nodes = [make_node("A"), make_node("B")]
        edges = [make_edge("A", "B"), make_edge("B", "A")]
        dag = DAG(nodes=nodes, edges=edges)
        errors = dag.validate()
        assert len(errors) == 1
        assert errors[0]["type"] == "cycle_detected"

    def test_three_node_cycle_detected(self, make_node, make_edge):
        nodes = [make_node("A"), make_node("B"), make_node("C")]
        edges = [make_edge("A", "B"), make_edge("B", "C"), make_edge("C", "A")]
        dag = DAG(nodes=nodes, edges=edges)
        errors = dag.validate()
        assert len(errors) == 1
        assert errors[0]["type"] == "cycle_detected"

    def test_self_loop_detected(self, make_node, make_edge):
        nodes = [make_node("A")]
        edges = [make_edge("A", "A")]
        dag = DAG(nodes=nodes, edges=edges)
        errors = dag.validate()
        assert len(errors) == 1
        assert errors[0]["type"] == "cycle_detected"

    def test_diamond_shape_is_valid(self, make_node, make_edge):
        """A -> B, A -> C, B -> D, C -> D (diamond, no cycle)."""
        nodes = [make_node("A"), make_node("B"), make_node("C"), make_node("D")]
        edges = [
            make_edge("A", "B"), make_edge("A", "C"),
            make_edge("B", "D"), make_edge("C", "D"),
        ]
        dag = DAG(nodes=nodes, edges=edges)
        errors = dag.validate()
        assert errors == []

    def test_edge_references_unknown_node(self, make_node, make_edge):
        nodes = [make_node("A")]
        edges = [make_edge("A", "MISSING")]
        dag = DAG(nodes=nodes, edges=edges)
        errors = dag.validate()
        assert any(e["type"] == "invalid_edge" for e in errors)


class TestTopologicalSort:
    """Execution order."""

    def test_single_node(self, make_node):
        dag = DAG(nodes=[make_node("A")], edges=[])
        order = dag.topological_sort()
        assert [n["id"] for n in order] == ["A"]

    def test_linear_chain_order(self, make_node, make_edge):
        nodes = [make_node("C"), make_node("A"), make_node("B")]
        edges = [make_edge("A", "B"), make_edge("B", "C")]
        dag = DAG(nodes=nodes, edges=edges)
        order = dag.topological_sort()
        ids = [n["id"] for n in order]
        assert ids.index("A") < ids.index("B") < ids.index("C")

    def test_diamond_respects_dependencies(self, make_node, make_edge):
        nodes = [make_node("A"), make_node("B"), make_node("C"), make_node("D")]
        edges = [
            make_edge("A", "B"), make_edge("A", "C"),
            make_edge("B", "D"), make_edge("C", "D"),
        ]
        dag = DAG(nodes=nodes, edges=edges)
        order = dag.topological_sort()
        ids = [n["id"] for n in order]
        assert ids.index("A") < ids.index("B")
        assert ids.index("A") < ids.index("C")
        assert ids.index("B") < ids.index("D")
        assert ids.index("C") < ids.index("D")

    def test_disconnected_nodes_all_present(self, make_node):
        nodes = [make_node("A"), make_node("B"), make_node("C")]
        dag = DAG(nodes=nodes, edges=[])
        order = dag.topological_sort()
        assert len(order) == 3
        assert {n["id"] for n in order} == {"A", "B", "C"}

    def test_sort_raises_on_cycle(self, make_node, make_edge):
        nodes = [make_node("A"), make_node("B")]
        edges = [make_edge("A", "B"), make_edge("B", "A")]
        dag = DAG(nodes=nodes, edges=edges)
        with pytest.raises(ValueError, match="cycle"):
            dag.topological_sort()


class TestInputResolution:
    """Follow edges to collect input values from upstream outputs."""

    def test_resolve_single_input(self, make_node, make_edge):
        nodes = [make_node("A"), make_node("B")]
        edges = [make_edge("A", "B", source_output="findings", target_input="content")]
        dag = DAG(nodes=nodes, edges=edges)

        upstream_outputs = {"A": {"findings": "some research data"}}
        resolved = dag.resolve_inputs(nodes[1], upstream_outputs)
        assert resolved == {"content": "some research data"}

    def test_resolve_multiple_inputs_from_different_sources(self, make_node, make_edge):
        nodes = [make_node("A"), make_node("B"), make_node("C")]
        edges = [
            make_edge("A", "C", source_output="findings", target_input="content"),
            make_edge("B", "C", source_output="style", target_input="tone"),
        ]
        dag = DAG(nodes=nodes, edges=edges)

        upstream_outputs = {
            "A": {"findings": "data"},
            "B": {"style": "formal"},
        }
        resolved = dag.resolve_inputs(nodes[2], upstream_outputs)
        assert resolved == {"content": "data", "tone": "formal"}

    def test_resolve_no_inputs(self, make_node):
        nodes = [make_node("A")]
        dag = DAG(nodes=nodes, edges=[])
        resolved = dag.resolve_inputs(nodes[0], {})
        assert resolved == {}

    def test_resolve_missing_upstream_returns_none(self, make_node, make_edge):
        nodes = [make_node("A"), make_node("B")]
        edges = [make_edge("A", "B", source_output="findings", target_input="content")]
        dag = DAG(nodes=nodes, edges=edges)

        resolved = dag.resolve_inputs(nodes[1], {})
        assert resolved == {"content": None}
