"""Integration tests for trugs_web.query — TRUGSWebGraphBuilder end-to-end."""

import pytest

from trugs_web.graph_builder import TRUGSWebGraphBuilder
from trugs_web.query.loader import load_graph
from trugs_web.query.synthesize import Report, generate_report


class TestWithTRUGSWebGraphBuilder:
    def test_load_graph_from_builder(self):
        builder = TRUGSWebGraphBuilder(name="integration-graph", topic="AI")
        builder.graph["nodes"].append(
            {
                "id": "concept1",
                "type": "CONCEPT",
                "properties": {"name": "Neural Networks", "credibility": 0.9},
                "metric_level": "BASE_CONCEPT",
                "parent_id": None,
                "contains": [],
                "dimension": "web_structure",
            }
        )
        graph = load_graph(builder.to_dict())
        assert graph is not None
        node = graph.get_node("concept1")
        assert node is not None
        assert node.name == "Neural Networks"
        assert node.credibility == 0.9

    @pytest.mark.asyncio
    async def test_full_pipeline(self):
        builder = TRUGSWebGraphBuilder(name="pipeline-test", topic="testing")
        builder.graph["nodes"].extend(
            [
                {
                    "id": "src1",
                    "type": "WEB_SOURCE",
                    "properties": {"name": "Source 1", "credibility": 0.8},
                    "metric_level": "BASE_WEB_SOURCE",
                    "parent_id": None,
                    "contains": [],
                    "dimension": "web_structure",
                },
                {
                    "id": "concept_a",
                    "type": "CONCEPT",
                    "properties": {"name": "Concept A", "credibility": 0.7},
                    "metric_level": "BASE_CONCEPT",
                    "parent_id": None,
                    "contains": [],
                    "dimension": "web_structure",
                },
            ]
        )
        builder.graph["edges"].append(
            {
                "from_id": "src1",
                "to_id": "concept_a",
                "relation": "DEFINES",
                "weight": 0.75,
            }
        )
        graph = load_graph(builder.to_dict())
        report = await generate_report(graph, "concept", use_llm=False)
        assert isinstance(report, Report)
        md = report.to_markdown()
        assert md.startswith("#")
