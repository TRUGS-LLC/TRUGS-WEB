"""
Graph Loader Module

Loads TRUGS 1.0-format graphs and provides a query interface.

TRUGS 1.0 node fields: id, type, properties, metric_level, parent_id,
                        contains, dimension
TRUGS 1.0 edge fields: from_id, to_id, relation, weight
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class Node:
    """A graph node (TRUGS 1.0 format)."""

    id: str
    type: str
    properties: dict = field(default_factory=dict)
    metric_level: str = ""

    @property
    def name(self) -> str:
        return self.properties.get("name", self.id)

    @property
    def url(self) -> Optional[str]:
        return self.properties.get("url") or self.properties.get("source_url")

    @property
    def description(self) -> str:
        return self.properties.get("description", "")

    @property
    def credibility(self) -> float:
        return float(self.properties.get("credibility", 0.5))

    def matches(self, **criteria) -> bool:
        """Check if node matches criteria."""
        for key, value in criteria.items():
            if key == "type" and self.type != value:
                return False
            if key == "id" and self.id != value:
                return False
            if key.startswith("properties__"):
                prop_key = key[12:]
                if "__contains" in prop_key:
                    field_name = prop_key.replace("__contains", "")
                    field_val = str(self.properties.get(field_name, "")).lower()
                    if value.lower() not in field_val:
                        return False
                elif self.properties.get(prop_key) != value:
                    return False
        return True


@dataclass
class Edge:
    """A graph edge (TRUGS 1.0 format)."""

    from_id: str
    to_id: str
    relation: str
    weight: float = 0.5

    def matches(self, **criteria) -> bool:
        """Check if edge matches criteria."""
        for key, value in criteria.items():
            if key == "from_id" and self.from_id != value:
                return False
            if key == "to_id" and self.to_id != value:
                return False
            if key == "relation" and self.relation != value:
                return False
            if key == "min_weight" and self.weight < value:
                return False
            if key == "max_weight" and self.weight > value:
                return False
        return True


@dataclass
class GraphMeta:
    """Graph metadata."""

    id: str
    title: str
    description: str = ""
    topic: str = ""
    created: str = ""
    modified: str = ""
    source_count: int = 0
    node_count: int = 0
    edge_count: int = 0


class Graph:
    """
    In-memory graph with query interface.

    Supports:
    - Node/edge lookup by ID
    - Filtering by type, relation, weight
    - Traversal operations
    """

    def __init__(self, meta, nodes, edges):
        self.meta = meta
        self._nodes = {n.id: n for n in nodes}
        self._edges = list(edges)

        # Build edge indexes for fast lookup
        self._outgoing = {}
        self._incoming = {}

        for edge in self._edges:
            self._outgoing.setdefault(edge.from_id, []).append(edge)
            self._incoming.setdefault(edge.to_id, []).append(edge)

    @property
    def nodes(self):
        return list(self._nodes.values())

    @property
    def edges(self):
        return self._edges

    def __len__(self):
        return len(self._nodes)

    # ========================================================================
    # Node Operations
    # ========================================================================

    def get_node(self, node_id):
        """Get node by ID."""
        return self._nodes.get(node_id)

    def find_nodes(self, **criteria):
        """
        Find nodes matching criteria.

        Examples::

            graph.find_nodes(type="CONCEPT")
            graph.find_nodes(properties__name__contains="lang")
        """
        return [n for n in self._nodes.values() if n.matches(**criteria)]

    def find_nodes_by_type(self, node_type):
        """Find all nodes of a given type."""
        return self.find_nodes(type=node_type)

    def search_nodes(self, query):
        """
        Search nodes by name/description containing query.
        Case-insensitive.
        """
        query = query.lower()
        results = []
        for node in self._nodes.values():
            name = node.name.lower()
            desc = node.description.lower()
            if query in name or query in desc:
                results.append(node)
        return results

    # ========================================================================
    # Edge Operations
    # ========================================================================

    def get_edges(self, **criteria):
        """
        Get edges matching criteria.

        Examples::

            graph.get_edges(relation="CITES")
            graph.get_edges(min_weight=0.7)
            graph.get_edges(from_id="node1", relation="USES")
        """
        return [e for e in self._edges if e.matches(**criteria)]

    def get_outgoing(self, node_id, relation=None, min_weight=0.0):
        """Get outgoing edges from a node."""
        edges = self._outgoing.get(node_id, [])
        if relation:
            edges = [e for e in edges if e.relation == relation]
        if min_weight > 0:
            edges = [e for e in edges if e.weight >= min_weight]
        return edges

    def get_incoming(self, node_id, relation=None, min_weight=0.0):
        """Get incoming edges to a node."""
        edges = self._incoming.get(node_id, [])
        if relation:
            edges = [e for e in edges if e.relation == relation]
        if min_weight > 0:
            edges = [e for e in edges if e.weight >= min_weight]
        return edges

    def get_neighbors(self, node_id, direction="both", min_weight=0.0):
        """
        Get neighbouring nodes.

        Args:
            node_id: Starting node
            direction: "outgoing", "incoming", or "both"
            min_weight: Minimum edge weight filter
        """
        neighbor_ids = set()

        if direction in ("outgoing", "both"):
            for edge in self.get_outgoing(node_id, min_weight=min_weight):
                neighbor_ids.add(edge.to_id)

        if direction in ("incoming", "both"):
            for edge in self.get_incoming(node_id, min_weight=min_weight):
                neighbor_ids.add(edge.from_id)

        return [self._nodes[nid] for nid in neighbor_ids if nid in self._nodes]

    # ========================================================================
    # Traversal Operations
    # ========================================================================

    def traverse(
        self,
        start_id,
        relation=None,
        direction="outgoing",
        min_weight=0.0,
        max_depth=1,
    ):
        """
        Traverse graph from starting node.

        Args:
            start_id: Starting node ID
            relation: Optional relation type filter
            direction: "outgoing" or "incoming"
            min_weight: Minimum edge weight
            max_depth: Maximum traversal depth

        Returns:
            List of (node, edge, depth) tuples
        """
        results = []
        visited = {start_id}
        frontier = [(start_id, 0)]

        while frontier:
            current_id, depth = frontier.pop(0)

            if depth >= max_depth:
                continue

            if direction == "outgoing":
                edges = self.get_outgoing(current_id, relation, min_weight)
                next_ids = [(e.to_id, e) for e in edges]
            else:
                edges = self.get_incoming(current_id, relation, min_weight)
                next_ids = [(e.from_id, e) for e in edges]

            for next_id, edge in next_ids:
                if next_id not in visited:
                    visited.add(next_id)
                    node = self.get_node(next_id)
                    if node:
                        results.append((node, edge, depth + 1))
                        frontier.append((next_id, depth + 1))

        return results

    def find_path(self, start_id, end_id, max_depth=5):
        """
        Find path between two nodes (BFS).

        Returns list of (node, edge) tuples representing the path,
        or None if no path exists.
        """
        if start_id == end_id:
            return []

        visited = {start_id}
        queue = [(start_id, [])]

        while queue:
            current_id, path = queue.pop(0)

            if len(path) >= max_depth:
                continue

            for edge in self.get_outgoing(current_id):
                next_id = edge.to_id
                next_node = self.get_node(next_id)

                if next_node is None:
                    continue

                new_path = path + [(next_node, edge)]

                if next_id == end_id:
                    return new_path

                if next_id not in visited:
                    visited.add(next_id)
                    queue.append((next_id, new_path))

        return None

    # ========================================================================
    # Aggregation Operations
    # ========================================================================

    def get_top_nodes(self, n=10, node_type=None, sort_by="credibility"):
        """Get top N nodes by credibility or other metric."""
        nodes = self.nodes
        if node_type:
            nodes = [node for node in nodes if node.type == node_type]

        if sort_by == "credibility":
            nodes.sort(key=lambda node: node.credibility, reverse=True)
        elif sort_by == "connections":
            nodes.sort(
                key=lambda node: (
                    len(self.get_outgoing(node.id)) + len(self.get_incoming(node.id))
                ),
                reverse=True,
            )

        return nodes[:n]

    def get_edge_stats(self):
        """Get edge statistics."""
        if not self._edges:
            return {"count": 0}

        weights = [e.weight for e in self._edges]
        relations = {}
        for e in self._edges:
            relations[e.relation] = relations.get(e.relation, 0) + 1

        return {
            "count": len(self._edges),
            "avg_weight": sum(weights) / len(weights),
            "min_weight": min(weights),
            "max_weight": max(weights),
            "relations": relations,
        }


class GraphLoader:
    """
    Loads TRUGS 1.0-format graphs from files or dicts.

    Accepts output from ``TRUGSWebGraphBuilder.to_dict()`` directly.
    """

    def load(self, path):
        """Load graph from a JSON file path or a pre-parsed dict."""
        if isinstance(path, dict):
            return self._parse(path)
        path = Path(path)
        data = json.loads(path.read_text())
        return self._parse(data)

    def loads(self, json_string):
        """Load graph from a JSON string."""
        data = json.loads(json_string)
        return self._parse(data)

    def _parse(self, data):
        """Parse TRUGS 1.0 graph data into a Graph object."""
        # Extract topic from first dimension (if present)
        dimensions = data.get("dimensions") or {}
        dim_keys = list(dimensions.keys())
        topic = dimensions[dim_keys[0]].get("description", "") if dim_keys else ""

        # Top-level metadata
        meta = GraphMeta(
            id=data.get("name", data.get("id", "unknown")),
            title=data.get("name", data.get("title", "Untitled")),
            description=data.get("description", ""),
            topic=topic,
            node_count=len(data.get("nodes", [])),
            edge_count=len(data.get("edges", [])),
        )

        # Parse nodes (TRUGS 1.0: properties, metric_level)
        nodes = []
        for node_data in data.get("nodes", []):
            nodes.append(
                Node(
                    id=node_data.get("id", ""),
                    type=node_data.get("type", "UNKNOWN"),
                    properties=node_data.get("properties", {}),
                    metric_level=node_data.get("metric_level", ""),
                )
            )

        # Parse edges (TRUGS 1.0: from_id, to_id, relation, weight)
        edges = []
        for edge_data in data.get("edges", []):
            edges.append(
                Edge(
                    from_id=edge_data.get("from_id", ""),
                    to_id=edge_data.get("to_id", ""),
                    relation=edge_data.get("relation", "RELATED_TO"),
                    weight=float(edge_data.get("weight", 0.5)),
                )
            )

        return Graph(meta=meta, nodes=nodes, edges=edges)


def load_graph(path):
    """
    Load a TRUGS 1.0 graph from a file path or dict.

    Args:
        path: File path (str or Path) or a pre-parsed dict.

    Returns:
        Graph instance ready for querying.
    """
    return GraphLoader().load(path)
