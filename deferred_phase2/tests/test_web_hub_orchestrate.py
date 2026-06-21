"""Tests for trugs_tools.web.hub.orchestrate — full pipeline."""

import json
import os
import tempfile

import pytest

from trugs_tools.web.hub.orchestrate import Orchestrator, PipelineResult
from trugs_tools.web.graph_builder import TRUGSWebGraphBuilder


# ============================================================================
# PipelineResult
# ============================================================================

class TestPipelineResult:
    def test_empty_result(self):
        r = PipelineResult()
        assert r.node_count == 0
        assert r.edge_count == 0
        assert r.graph_dict is None
        assert r.sources == []
        assert r.entities == []
        assert r.relations == []
        assert r.errors == []

    def test_with_builder(self):
        builder = TRUGSWebGraphBuilder(
            name="test", topic="testing", description="A test graph"
        )
        r = PipelineResult(builder=builder)
        # Builder creates a root node + no edges by default
        assert r.node_count == 1
        assert r.edge_count == 0
        d = r.graph_dict
        assert d is not None
        assert d["name"] == "test"


# ============================================================================
# Orchestrator — mock provider (no real HTTP)
# ============================================================================

class TestOrchestratorMock:
    @pytest.mark.asyncio
    async def test_run_with_mock_provider(self):
        """Run the full pipeline with the mock LLM (no HTTP calls)."""
        orch = Orchestrator(
            topic="machine learning",
            llm_provider="mock",
            max_sources=5,
        )
        result = await orch.run(
            seed_urls=["https://example.com/ml-article"]
        )
        assert isinstance(result, PipelineResult)
        assert result.builder is not None
        # Should have at least the root node
        assert result.node_count >= 1

    @pytest.mark.asyncio
    async def test_run_empty_seeds(self):
        orch = Orchestrator(topic="empty", llm_provider="mock")
        result = await orch.run(seed_urls=[])
        assert result.builder is not None
        assert result.node_count >= 1  # root node
        assert result.errors == []

    @pytest.mark.asyncio
    async def test_graph_dict_structure(self):
        orch = Orchestrator(topic="test graph", llm_provider="mock")
        result = await orch.run(seed_urls=[])
        d = result.graph_dict
        assert d is not None
        assert "name" in d
        assert "version" in d
        assert "type" in d
        assert "nodes" in d
        assert "edges" in d
        assert d["version"] == "1.0.0"
        assert d["type"] == "RESEARCH"

    @pytest.mark.asyncio
    async def test_run_and_save(self):
        orch = Orchestrator(topic="save test", llm_provider="mock")
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "output.trug.json")
            result = await orch.run_and_save(
                seed_urls=[],
                output_path=path,
                validate=True,
            )
            assert os.path.exists(path)
            with open(path) as f:
                data = json.load(f)
            assert data["type"] == "RESEARCH"

    @pytest.mark.asyncio
    async def test_description_default(self):
        orch = Orchestrator(topic="my topic")
        assert "my topic" in orch.description

    @pytest.mark.asyncio
    async def test_description_custom(self):
        orch = Orchestrator(topic="my topic", description="Custom desc")
        assert orch.description == "Custom desc"


# ============================================================================
# Orchestrator — integration with hub __init__
# ============================================================================

class TestOrchestratorImport:
    def test_import_from_hub(self):
        from trugs_tools.web.hub import Orchestrator as O, PipelineResult as PR
        assert O is Orchestrator
        assert PR is PipelineResult

    def test_import_from_web(self):
        from trugs_tools.web import Orchestrator as O, PipelineResult as PR
        assert O is Orchestrator
        assert PR is PipelineResult
