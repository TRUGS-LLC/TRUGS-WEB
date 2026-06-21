"""Shared fixtures for trugs_web.query tests."""

import pytest

from trugs_web.graph_builder import TRUGSWebGraphBuilder
from trugs_web.query.loader import GraphLoader


def _make_trugs_graph():
    """Build a minimal TRUGS 1.0 graph dict for testing."""
    builder = TRUGSWebGraphBuilder(name="test-graph", topic="testing")

    # Manually inject nodes with credibility in properties
    builder.graph["nodes"].extend(
        [
            {
                "id": "langchain",
                "type": "PROJECT",
                "properties": {
                    "name": "LangChain",
                    "url": "https://github.com/langchain-ai/langchain",
                    "credibility": 0.9,
                },
                "metric_level": "BASE_PROJECT",
                "parent_id": None,
                "contains": [],
                "dimension": "web_structure",
            },
            {
                "id": "langgraph",
                "type": "PROJECT",
                "properties": {
                    "name": "LangGraph",
                    "url": "https://github.com/langchain-ai/langgraph",
                    "credibility": 0.85,
                },
                "metric_level": "BASE_PROJECT",
                "parent_id": None,
                "contains": [],
                "dimension": "web_structure",
            },
            {
                "id": "neo4j",
                "type": "PROJECT",
                "properties": {
                    "name": "Neo4j",
                    "description": "Graph database",
                    "credibility": 0.95,
                },
                "metric_level": "BASE_PROJECT",
                "parent_id": None,
                "contains": [],
                "dimension": "web_structure",
            },
            {
                "id": "graphrag",
                "type": "CONCEPT",
                "properties": {
                    "name": "GraphRAG",
                    "description": "Graph-based retrieval augmented generation",
                    "credibility": 0.8,
                },
                "metric_level": "BASE_CONCEPT",
                "parent_id": None,
                "contains": [],
                "dimension": "web_structure",
            },
        ]
    )

    builder.graph["edges"].extend(
        [
            {
                "from_id": "langgraph",
                "to_id": "langchain",
                "relation": "EXTENDS",
                "weight": 0.95,
            },
            {
                "from_id": "langchain",
                "to_id": "neo4j",
                "relation": "INTEGRATES",
                "weight": 0.7,
            },
            {
                "from_id": "neo4j",
                "to_id": "graphrag",
                "relation": "DEFINES",
                "weight": 0.85,
            },
            {
                "from_id": "langgraph",
                "to_id": "neo4j",
                "relation": "ALTERNATIVE_TO",
                "weight": 0.4,
            },
        ]
    )

    return builder.to_dict()


# AGENT claude SHALL DEFINE FUNCTION sample_graph_dict.
@pytest.fixture
def sample_graph_dict():
    return _make_trugs_graph()


# AGENT claude SHALL DEFINE FUNCTION sample_graph.
@pytest.fixture
def sample_graph(sample_graph_dict):
    return GraphLoader().load(sample_graph_dict)
