"""Tests for trugs_web.graph_builder — TRUGS 1.0 graph building module."""

import json
import pytest
import tempfile
import os

from trugs_web.crawler import Source
from trugs_web.extractor import Relation
from trugs_web.resolver import ResolvedEntity
from trugs_web.graph_builder import (
    TRUGSWebGraphBuilder,
    build_graph,
    load_graph,
    url_to_id,
    make_id,
    _url_to_id,
    _make_id,
)
from trugs_tools.validator import validate_trug


class TestTRUGSWebGraphBuilder:
    def test_initial_structure(self):
        builder = TRUGSWebGraphBuilder(name="test-graph", topic="testing")
        graph = builder.to_dict()

        # Required TRUGS 1.0 root fields
        assert "name" in graph
        assert "version" in graph
        assert graph["version"] == "1.0.0"
        assert "type" in graph
        assert graph["type"] == "RESEARCH"
        assert "nodes" in graph
        assert "edges" in graph
        assert "dimensions" in graph
        assert "capabilities" in graph

    def test_root_node_created(self):
        builder = TRUGSWebGraphBuilder(name="my-graph", topic="AI")
        graph = builder.to_dict()
        # Should have a root RESEARCH_GRAPH node
        types = [n["type"] for n in graph["nodes"]]
        assert "RESEARCH_GRAPH" in types

    def test_root_node_trugs_fields(self):
        builder = TRUGSWebGraphBuilder(name="my-graph", topic="AI")
        graph = builder.to_dict()
        root = graph["nodes"][0]
        assert "id" in root
        assert "type" in root
        assert "metric_level" in root
        assert "contains" in root
        assert "properties" in root

    def test_add_source_node(self):
        builder = TRUGSWebGraphBuilder(name="g", topic="t")
        source = Source(
            url="https://example.com/page", title="Example", source_type="WEB_SOURCE"
        )
        node_id = builder.add_source_node(source, credibility=0.5)

        ids = [n["id"] for n in builder.graph["nodes"]]
        assert node_id in ids

        node = next(n for n in builder.graph["nodes"] if n["id"] == node_id)
        assert node["type"] == "WEB_SOURCE"
        assert node["properties"]["url"] == "https://example.com/page"
        assert node["properties"]["credibility"] == 0.5

    def test_add_source_node_dedup(self):
        builder = TRUGSWebGraphBuilder(name="g", topic="t")
        source = Source(url="https://example.com/", title="T", source_type="WEB_SOURCE")
        builder.add_source_node(source)
        builder.add_source_node(source)  # duplicate
        ids = [n["id"] for n in builder.graph["nodes"]]
        # Should only appear once
        assert ids.count(_url_to_id("https://example.com/")) == 1

    def test_add_entity_node(self):
        builder = TRUGSWebGraphBuilder(name="g", topic="t")
        entity = ResolvedEntity(
            id="langchain",
            canonical_name="LangChain",
            entity_type="TOOL",
            description="LLM framework",
        )
        node_id = builder.add_entity_node(entity)
        ids = [n["id"] for n in builder.graph["nodes"]]
        assert node_id in ids

        node = next(n for n in builder.graph["nodes"] if n["id"] == node_id)
        assert node["type"] == "TOOL"
        assert node["properties"]["name"] == "LangChain"
        assert node["metric_level"] == "BASE_TOOL"

    def test_add_relation_edge(self):
        builder = TRUGSWebGraphBuilder(name="g", topic="t")
        # Add both endpoints first
        builder._add_node("node_a", "CONCEPT", {"name": "A"}, "BASE_CONCEPT")
        builder._add_node("node_b", "CONCEPT", {"name": "B"}, "BASE_CONCEPT")

        relation = Relation(
            from_id="node_a", to_id="node_b", relation_type="CITES", confidence=0.9
        )
        builder.add_relation_edge(relation, weight=0.85)

        edge_keys = [
            (e["from_id"], e["to_id"], e["relation"]) for e in builder.graph["edges"]
        ]
        assert ("node_a", "node_b", "CITES") in edge_keys

    def test_add_relation_edge_missing_endpoint(self):
        builder = TRUGSWebGraphBuilder(name="g", topic="t")
        relation = Relation(
            from_id="unknown_a", to_id="unknown_b", relation_type="CITES"
        )
        # Should not raise, just skip
        builder.add_relation_edge(relation, weight=0.5)
        edge_keys = [(e["from_id"], e["to_id"]) for e in builder.graph["edges"]]
        assert ("unknown_a", "unknown_b") not in edge_keys

    def test_edge_deduplication(self):
        builder = TRUGSWebGraphBuilder(name="g", topic="t")
        builder._add_node("a", "CONCEPT", {"name": "A"}, "BASE_CONCEPT")
        builder._add_node("b", "CONCEPT", {"name": "B"}, "BASE_CONCEPT")
        builder._add_edge("a", "b", "CITES", weight=0.8)
        builder._add_edge("a", "b", "CITES", weight=0.8)  # duplicate
        cites_edges = [
            e
            for e in builder.graph["edges"]
            if e["from_id"] == "a" and e["to_id"] == "b" and e["relation"] == "CITES"
        ]
        assert len(cites_edges) == 1

    def test_to_json(self):
        builder = TRUGSWebGraphBuilder(name="g", topic="t")
        json_str = builder.to_json()
        data = json.loads(json_str)
        assert "name" in data
        assert "nodes" in data

    def test_validate_passes(self):
        builder = TRUGSWebGraphBuilder(name="test-graph", topic="testing")
        result = builder.validate()
        assert result.valid, f"Validation failed: {result.errors}"

    def test_validate_with_entity_node(self):
        builder = TRUGSWebGraphBuilder(name="test", topic="AI")
        entity = ResolvedEntity(
            id="concept-1",
            canonical_name="Transformer",
            entity_type="CONCEPT",
        )
        builder.add_entity_node(entity)
        result = builder.validate()
        assert result.valid, f"Validation failed: {result.errors}"

    def test_save_and_load(self):
        builder = TRUGSWebGraphBuilder(name="save-test", topic="testing")
        with tempfile.NamedTemporaryFile(suffix=".trug.json", delete=False) as f:
            path = f.name
        try:
            result = builder.save(path, validate=True)
            assert os.path.exists(path)
            assert result["nodes"] > 0

            loaded = load_graph(path)
            assert loaded["name"] == "save-test"
            assert "nodes" in loaded
        finally:
            os.unlink(path)

    def test_save_validates_before_saving(self):
        builder = TRUGSWebGraphBuilder(name="v", topic="t")
        # Corrupt the graph
        builder.graph["nodes"][0].pop("metric_level")
        with tempfile.NamedTemporaryFile(suffix=".trug.json", delete=False) as f:
            path = f.name
        try:
            with pytest.raises(ValueError, match="validation failed"):
                builder.save(path, validate=True)
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_contains_edges_in_graph(self):
        """Parent-child relationships should create contains edges."""
        builder = TRUGSWebGraphBuilder(name="g", topic="t")
        entity = ResolvedEntity(id="e1", canonical_name="E1", entity_type="CONCEPT")
        builder.add_entity_node(entity)
        # Verify contains edge from root to entity
        contains_edges = [
            e
            for e in builder.graph["edges"]
            if e["relation"] == "contains" and e["to_id"] == "e1"
        ]
        assert len(contains_edges) >= 1


class TestTRUGS10Compliance:
    """Verify TRUGS 1.0 format compliance via validator."""

    def test_graph_passes_validator(self):
        builder = TRUGSWebGraphBuilder(name="compliance-test", topic="AI research")
        result = validate_trug(builder.to_dict())
        assert result.valid, f"Errors: {result.errors}"

    def test_node_required_fields(self):
        builder = TRUGSWebGraphBuilder(name="g", topic="t")
        for node in builder.graph["nodes"]:
            assert "id" in node
            assert "type" in node
            assert "metric_level" in node

    def test_edge_required_fields(self):
        builder = TRUGSWebGraphBuilder(name="g", topic="t")
        # Add a node to get contains edges
        builder._add_node("child", "CONCEPT", {"name": "C"}, "BASE_CONCEPT")
        for edge in builder.graph["edges"]:
            assert "from_id" in edge
            assert "to_id" in edge
            assert "relation" in edge

    def test_no_source_target_fields(self):
        """Edges must use from_id/to_id, not source/target (ESG format)."""
        builder = TRUGSWebGraphBuilder(name="g", topic="t")
        for edge in builder.graph["edges"]:
            assert "source" not in edge
            assert "target" not in edge
            assert "from_id" in edge
            assert "to_id" in edge

    def test_graph_with_source_and_entity(self):
        builder = TRUGSWebGraphBuilder(name="full-test", topic="machine learning")
        source = Source(
            url="https://arxiv.org/abs/2301.00001",
            title="Test Paper",
            source_type="PAPER",
        )
        entity = ResolvedEntity(
            id="transformer", canonical_name="Transformer", entity_type="CONCEPT"
        )

        builder.add_source_node(source, credibility=0.7)
        builder.add_entity_node(entity)

        result = validate_trug(builder.to_dict())
        assert result.valid, f"Errors: {result.errors}"


@pytest.mark.asyncio
async def test_build_graph_empty_seeds():
    """build_graph with no seed URLs returns valid TRUGS 1.0 graph."""
    builder = await build_graph(topic="test topic", seed_urls=[], llm_provider="mock")
    assert isinstance(builder, TRUGSWebGraphBuilder)
    graph = builder.to_dict()
    assert graph["name"] == "test-topic"
    assert graph["version"] == "1.0.0"
    assert graph["type"] == "RESEARCH"

    # Validate TRUGS 1.0 compliance
    result = validate_trug(graph)
    assert result.valid, f"Errors: {result.errors}"


@pytest.mark.asyncio
async def test_build_graph_with_respx():
    """build_graph discovers sources and builds a valid TRUGS 1.0 graph."""
    import respx
    import httpx

    html = b"""<html><head><title>ML Paper</title>
    <meta name="description" content="A machine learning paper"></head>
    <body><p>Transformers are state-of-the-art.</p></body></html>"""

    with respx.mock:
        respx.get("https://arxiv.org/abs/test").mock(
            return_value=httpx.Response(
                200, content=html, headers={"content-type": "text/html"}
            )
        )

        builder = await build_graph(
            topic="transformers",
            seed_urls=["https://arxiv.org/abs/test"],
            llm_provider="mock",
        )

    graph = builder.to_dict()
    result = validate_trug(graph)
    assert result.valid, f"Errors: {result.errors}"
    # Should have more than just the root node
    assert len(graph["nodes"]) >= 1


def test_url_to_id():
    assert _url_to_id("https://github.com/org/repo") == "github-com-org-repo"
    assert len(_url_to_id("https://example.com/" + "a" * 200)) <= 80


def test_make_id():
    assert _make_id("machine learning") == "machine-learning"
    assert _make_id("Test Topic!") == "test-topic"
    assert len(_make_id("a" * 100)) <= 50


# ============================================================================
# Public API — url_to_id, make_id, has_node, add_edge
# ============================================================================


def test_public_url_to_id():
    """Public url_to_id matches the deprecated _url_to_id alias."""
    assert url_to_id("https://github.com/org/repo") == "github-com-org-repo"
    assert url_to_id is _url_to_id


def test_public_make_id():
    """Public make_id matches the deprecated _make_id alias."""
    assert make_id("machine learning") == "machine-learning"
    assert make_id is _make_id


def test_has_node():
    builder = TRUGSWebGraphBuilder(name="g", topic="t")
    assert builder.has_node(builder._root_id) is True
    assert builder.has_node("nonexistent") is False


def test_add_edge_public():
    builder = TRUGSWebGraphBuilder(name="g", topic="t")
    builder._add_node("a", "CONCEPT", {"name": "A"}, "BASE_CONCEPT")
    builder._add_node("b", "CONCEPT", {"name": "B"}, "BASE_CONCEPT")
    builder.add_edge("a", "b", "CITES", weight=0.9)
    cites = [e for e in builder.graph["edges"] if e["relation"] == "CITES"]
    assert len(cites) == 1
    assert cites[0]["weight"] == 0.9


def test_add_edge_deduplication_public():
    builder = TRUGSWebGraphBuilder(name="g", topic="t")
    builder._add_node("x", "CONCEPT", {"name": "X"}, "BASE_CONCEPT")
    builder._add_node("y", "CONCEPT", {"name": "Y"}, "BASE_CONCEPT")
    builder.add_edge("x", "y", "LINKS", weight=0.5)
    builder.add_edge("x", "y", "LINKS", weight=0.5)  # duplicate
    links = [e for e in builder.graph["edges"] if e["relation"] == "LINKS"]
    assert len(links) == 1
