"""DAG validation, topological sort, and input resolution."""

from collections import defaultdict, deque
from typing import Any


class DAG:
    """Validated directed acyclic graph of project nodes."""

    def __init__(self, nodes: list[dict], edges: list[dict]):
        self.nodes = nodes
        self.edges = edges
        self._node_ids = {n["id"] for n in nodes}
        self._adjacency: dict[str, list[str]] = defaultdict(list)
        self._in_degree: dict[str, int] = {n["id"]: 0 for n in nodes}
        for edge in edges:
            src = edge["source_node_id"]
            tgt = edge["target_node_id"]
            if src in self._node_ids and tgt in self._node_ids:
                self._adjacency[src].append(tgt)
                self._in_degree[tgt] = self._in_degree.get(tgt, 0) + 1

    def validate(self) -> list[dict]:
        """Check for cycles and invalid edges."""
        errors = []

        for edge in self.edges:
            src = edge["source_node_id"]
            tgt = edge["target_node_id"]
            if src not in self._node_ids or tgt not in self._node_ids:
                missing = src if src not in self._node_ids else tgt
                errors.append({
                    "type": "invalid_edge",
                    "message": f"Edge references unknown node '{missing}'",
                })

        if self._has_cycle():
            errors.append({
                "type": "cycle_detected",
                "message": "DAG contains a cycle",
            })

        return errors

    def topological_sort(self) -> list[dict]:
        """Return nodes in execution order. Raises ValueError on cycle."""
        in_degree = dict(self._in_degree)
        queue = deque(nid for nid, deg in in_degree.items() if deg == 0)
        result_ids = []

        while queue:
            nid = queue.popleft()
            result_ids.append(nid)
            for neighbor in self._adjacency[nid]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(result_ids) != len(self.nodes):
            raise ValueError("DAG contains a cycle; topological sort impossible")

        node_map = {n["id"]: n for n in self.nodes}
        return [node_map[nid] for nid in result_ids]

    def resolve_inputs(self, node: dict, upstream_outputs: dict[str, Any]) -> dict:
        """Follow edges backward to collect input values from upstream outputs."""
        resolved = {}
        node_id = node["id"]
        for edge in self.edges:
            if edge["target_node_id"] != node_id:
                continue
            src_id = edge["source_node_id"]
            src_field = edge["source_output"]
            tgt_field = edge["target_input"]
            src_outputs = upstream_outputs.get(src_id, {})
            resolved[tgt_field] = src_outputs.get(src_field) if src_outputs else None
        return resolved

    def _has_cycle(self) -> bool:
        """Kahn's algorithm: if topo sort doesn't include all nodes, there's a cycle."""
        in_degree = dict(self._in_degree)
        queue = deque(nid for nid, deg in in_degree.items() if deg == 0)
        visited = 0

        while queue:
            nid = queue.popleft()
            visited += 1
            for neighbor in self._adjacency[nid]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        return visited != len(self.nodes)
