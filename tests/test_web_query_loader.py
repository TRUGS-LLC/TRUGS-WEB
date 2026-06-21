"""Tests for trugs_web.query.loader — Node, Edge, Graph, GraphLoader."""

import json


from trugs_web.query.loader import (
    Node,
    Edge,
    GraphMeta,
    Graph,
    GraphLoader,
    load_graph,
)


# ============================================================================
# Node Tests
# ============================================================================


class TestNode:
    def test_name_from_properties(self):
        node = Node(id="test", type="T", properties={"name": "Test Node"})
        assert node.name == "Test Node"

    def test_name_fallback_to_id(self):
        node = Node(id="test", type="T", properties={})
        assert node.name == "test"

    def test_credibility_from_properties(self):
        node = Node(id="n", type="T", properties={"credibility": 0.85})
        assert node.credibility == 0.85

    def test_credibility_default(self):
        node = Node(id="n", type="T", properties={})
        assert node.credibility == 0.5

    def test_url_from_properties(self):
        node = Node(id="n", type="T", properties={"url": "https://example.com"})
        assert node.url == "https://example.com"

    def test_url_from_source_url(self):
        node = Node(id="n", type="T", properties={"source_url": "https://example.com"})
        assert node.url == "https://example.com"

    def test_description_from_properties(self):
        node = Node(id="n", type="T", properties={"description": "A description"})
        assert node.description == "A description"

    def test_matches_type(self):
        node = Node(id="n1", type="CONCEPT", properties={})
        assert node.matches(type="CONCEPT")
        assert not node.matches(type="PROJECT")

    def test_matches_id(self):
        node = Node(id="n1", type="T", properties={})
        assert node.matches(id="n1")
        assert not node.matches(id="n2")

    def test_matches_properties_exact(self):
        node = Node(id="n", type="T", properties={"name": "Foo"})
        assert node.matches(properties__name="Foo")
        assert not node.matches(properties__name="Bar")

    def test_matches_properties_contains(self):
        node = Node(id="n", type="T", properties={"name": "LangGraph"})
        assert node.matches(properties__name__contains="Lang")
        assert not node.matches(properties__name__contains="Python")


# ============================================================================
# Edge Tests
# ============================================================================


class TestEdge:
    def test_edge_matches_relation(self):
        edge = Edge(from_id="a", to_id="b", relation="CITES", weight=0.8)
        assert edge.matches(relation="CITES")
        assert not edge.matches(relation="USES")

    def test_edge_matches_min_weight(self):
        edge = Edge(from_id="a", to_id="b", relation="R", weight=0.8)
        assert edge.matches(min_weight=0.5)
        assert not edge.matches(min_weight=0.9)

    def test_edge_matches_max_weight(self):
        edge = Edge(from_id="a", to_id="b", relation="R", weight=0.3)
        assert edge.matches(max_weight=0.5)
        assert not edge.matches(max_weight=0.2)

    def test_edge_matches_from_to(self):
        edge = Edge(from_id="a", to_id="b", relation="R", weight=0.5)
        assert edge.matches(from_id="a", to_id="b")
        assert not edge.matches(from_id="x")


# ============================================================================
# Graph Tests
# ============================================================================


class TestGraph:
    def test_get_node(self, sample_graph):
        node = sample_graph.get_node("langchain")
        assert node is not None
        assert node.name == "LangChain"

    def test_get_node_missing(self, sample_graph):
        assert sample_graph.get_node("nonexistent") is None

    def test_len(self, sample_graph):
        # root node from builder + 4 manual nodes
        assert len(sample_graph) >= 4

    def test_find_nodes_by_type(self, sample_graph):
        projects = sample_graph.find_nodes_by_type("PROJECT")
        assert len(projects) >= 3

    def test_search_nodes_case_insensitive(self, sample_graph):
        results = sample_graph.search_nodes("GRAPH")
        # Should find LangGraph, Neo4j (graph database), GraphRAG
        names = [n.name for n in results]
        assert any("Graph" in name or "graph" in name.lower() for name in names)

    def test_get_outgoing(self, sample_graph):
        edges = sample_graph.get_outgoing("langgraph")
        assert len(edges) == 2

    def test_get_incoming(self, sample_graph):
        edges = sample_graph.get_incoming("langchain")
        assert len(edges) == 1

    def test_get_neighbors_both(self, sample_graph):
        neighbors = sample_graph.get_neighbors("langchain", direction="both")
        ids = {n.id for n in neighbors}
        assert "langgraph" in ids or "neo4j" in ids

    def test_get_edges_by_relation(self, sample_graph):
        edges = sample_graph.get_edges(relation="EXTENDS")
        assert len(edges) == 1
        assert edges[0].from_id == "langgraph"

    def test_get_edges_min_weight(self, sample_graph):
        high = sample_graph.get_edges(min_weight=0.9)
        assert all(e.weight >= 0.9 for e in high)

    def test_traverse_outgoing(self, sample_graph):
        results = sample_graph.traverse("langgraph", direction="outgoing", max_depth=1)
        assert len(results) > 0
        for node, edge, depth in results:
            assert depth == 1

    def test_find_path(self, sample_graph):
        path = sample_graph.find_path("langgraph", "graphrag")
        # langgraph → neo4j → graphrag
        assert path is not None
        assert len(path) > 0

    def test_find_path_same_node(self, sample_graph):
        path = sample_graph.find_path("langchain", "langchain")
        assert path == []

    def test_find_path_no_path(self, sample_graph):
        path = sample_graph.find_path("graphrag", "langgraph")
        assert path is None

    def test_get_top_nodes_credibility(self, sample_graph):
        top = sample_graph.get_top_nodes(n=2, sort_by="credibility")
        assert len(top) <= 2
        if len(top) == 2:
            assert top[0].credibility >= top[1].credibility

    def test_get_top_nodes_connections(self, sample_graph):
        top = sample_graph.get_top_nodes(n=3, sort_by="connections")
        assert len(top) <= 3

    def test_get_top_nodes_by_type(self, sample_graph):
        concepts = sample_graph.get_top_nodes(n=5, node_type="CONCEPT")
        assert all(n.type == "CONCEPT" for n in concepts)

    def test_get_edge_stats(self, sample_graph):
        stats = sample_graph.get_edge_stats()
        assert stats["count"] >= 4
        assert 0 < stats["avg_weight"] <= 1.0
        assert "relations" in stats

    def test_get_edge_stats_empty(self):
        meta = GraphMeta(id="empty", title="Empty")
        graph = Graph(meta=meta, nodes=[], edges=[])
        stats = graph.get_edge_stats()
        assert stats["count"] == 0


# ============================================================================
# GraphLoader Tests
# ============================================================================


class TestGraphLoader:
    def test_load_from_dict(self, sample_graph_dict):
        graph = GraphLoader().load(sample_graph_dict)
        assert graph is not None
        assert graph.meta.id == "test-graph"

    def test_load_reads_properties(self, sample_graph_dict):
        graph = GraphLoader().load(sample_graph_dict)
        node = graph.get_node("langchain")
        assert node is not None
        assert node.name == "LangChain"
        assert node.credibility == 0.9

    def test_load_from_file(self, sample_graph_dict, tmp_path):
        path = tmp_path / "graph.json"
        path.write_text(json.dumps(sample_graph_dict))
        graph = GraphLoader().load(path)
        assert graph is not None
        assert graph.get_node("neo4j") is not None

    def test_loads_from_string(self, sample_graph_dict):
        json_str = json.dumps(sample_graph_dict)
        graph = GraphLoader().loads(json_str)
        assert graph is not None

    def test_load_edges(self, sample_graph_dict):
        graph = GraphLoader().load(sample_graph_dict)
        edge = graph.get_edges(relation="EXTENDS")
        assert len(edge) == 1
        assert edge[0].weight == 0.95

    def test_load_graph_convenience(self, sample_graph_dict):
        graph = load_graph(sample_graph_dict)
        assert isinstance(graph, Graph)

    def test_load_graph_from_path(self, sample_graph_dict, tmp_path):
        path = tmp_path / "g.json"
        path.write_text(json.dumps(sample_graph_dict))
        graph = load_graph(str(path))
        assert isinstance(graph, Graph)

    def test_minimal_graph(self):
        data = {
            "name": "minimal",
            "nodes": [],
            "edges": [],
        }
        graph = GraphLoader().load(data)
        assert graph.meta.id == "minimal"
        assert len(graph.nodes) == 0

    def test_empty_dimensions(self):
        data = {
            "name": "g",
            "dimensions": {},
            "nodes": [],
            "edges": [],
        }
        graph = GraphLoader().load(data)
        assert graph.meta.topic == ""

    def test_default_weight(self):
        data = {
            "name": "g",
            "nodes": [{"id": "n1", "type": "T", "properties": {}}],
            "edges": [{"from_id": "n1", "to_id": "n2", "relation": "R"}],
        }
        graph = GraphLoader().load(data)
        assert graph.edges[0].weight == 0.5
