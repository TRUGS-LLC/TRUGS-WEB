"""Tests for trugs_web.query.synthesize — Finding, Report, ReportSynthesizer, generate_report."""

import pytest

from trugs_web.query.loader import load_graph
from trugs_web.query.traverse import TraversalResult, GraphTraverser
from trugs_web.query.synthesize import (
    Finding,
    Report,
    ReportSynthesizer,
    generate_report,
)
from trugs_web.extractor import MockLLMClient


# ============================================================================
# Finding Tests
# ============================================================================


class TestFinding:
    def test_high_confidence_markdown(self):
        finding = Finding(
            statement="LangChain is a framework",
            source_name="LangChain Docs",
            source_url="https://docs.langchain.com",
            weight=0.85,
        )
        md = finding.to_markdown()
        assert "🟢" in md
        assert "LangChain" in md
        assert "0.85" in md

    def test_medium_confidence_markdown(self):
        finding = Finding(
            statement="Medium claim",
            source_name="Source",
            source_url=None,
            weight=0.5,
        )
        md = finding.to_markdown()
        assert "🟡" in md

    def test_low_confidence_markdown(self):
        finding = Finding(
            statement="Low claim",
            source_name="Source",
            source_url=None,
            weight=0.2,
        )
        md = finding.to_markdown()
        assert "🔴" in md

    def test_no_url_markdown(self):
        finding = Finding(
            statement="Claim",
            source_name="Source",
            source_url=None,
            weight=0.7,
        )
        md = finding.to_markdown()
        assert "Source" in md
        assert "http" not in md


# ============================================================================
# Report Tests
# ============================================================================


class TestReport:
    def test_to_markdown_basic(self):
        report = Report(
            title="Test Report",
            query="test query",
            graph_id="test-graph",
            summary="This is a test.",
            findings=[
                Finding(
                    statement="Finding 1",
                    source_name="Source A",
                    source_url="https://example.com",
                    weight=0.8,
                )
            ],
            source_count=1,
            high_credibility_count=1,
            avg_weight=0.8,
        )
        md = report.to_markdown()
        assert "# Test Report" in md
        assert "test query" in md
        assert "Finding 1" in md
        assert "Sources" in md

    def test_to_markdown_contradictions(self):
        a = Finding(statement="Claim A", source_name="SA", source_url=None, weight=0.8)
        b = Finding(statement="Claim B", source_name="SB", source_url=None, weight=0.6)
        report = Report(
            title="R",
            query="q",
            graph_id="g",
            contradictions=[(a, b)],
        )
        md = report.to_markdown()
        assert "Contradictions" in md
        assert "Claim A" in md

    def test_to_markdown_recommendations(self):
        report = Report(
            title="R",
            query="q",
            graph_id="g",
            recommendations=["Do this first.", "Then do that."],
        )
        md = report.to_markdown()
        assert "Recommendations" in md
        assert "Do this first" in md

    def test_save_to_file(self, tmp_path):
        report = Report(title="R", query="q", graph_id="g")
        out = tmp_path / "report.md"
        report.save(out)
        assert out.exists()
        assert "# R" in out.read_text()

    def test_no_findings_sections_hidden(self):
        report = Report(title="R", query="q", graph_id="g")
        md = report.to_markdown()
        assert "Key Findings" not in md


# ============================================================================
# ReportSynthesizer Tests
# ============================================================================


class TestReportSynthesizer:
    @pytest.mark.asyncio
    async def test_basic_mode(self, sample_graph):
        traverser = GraphTraverser(sample_graph)
        result = traverser.concept_sources("graph")
        synthesizer = ReportSynthesizer(use_llm=False)
        report = await synthesizer.synthesize(sample_graph, result)
        assert report.title
        assert report.graph_id == sample_graph.meta.id
        assert isinstance(report.summary, str)
        assert isinstance(report.recommendations, list)

    @pytest.mark.asyncio
    async def test_llm_mode(self, sample_graph):
        traverser = GraphTraverser(sample_graph)
        result = traverser.concept_sources("graph")
        mock_llm = MockLLMClient()
        synthesizer = ReportSynthesizer(llm_client=mock_llm, use_llm=True)
        report = await synthesizer.synthesize(sample_graph, result)
        # MockLLMClient is used; summary is a non-empty string
        assert isinstance(report.summary, str)
        assert len(report.summary) > 0

    @pytest.mark.asyncio
    async def test_custom_title(self, sample_graph):
        traverser = GraphTraverser(sample_graph)
        result = traverser.high_credibility_sources(0.5)
        synthesizer = ReportSynthesizer()
        report = await synthesizer.synthesize(sample_graph, result, title="My Report")
        assert report.title == "My Report"

    @pytest.mark.asyncio
    async def test_no_findings_summary(self, sample_graph):
        result = TraversalResult(query="empty query")
        synthesizer = ReportSynthesizer()
        report = await synthesizer.synthesize(sample_graph, result)
        assert "No relevant findings" in report.summary

    @pytest.mark.asyncio
    async def test_low_credibility_recommendation(self, sample_graph):
        # Result with avg_weight = 0 and no high credibility
        result = TraversalResult(query="low", nodes=[], edges=[])
        synthesizer = ReportSynthesizer()
        report = await synthesizer.synthesize(sample_graph, result)
        assert any(
            "peer-reviewed" in r or "credibility" in r.lower()
            for r in report.recommendations
        )

    @pytest.mark.asyncio
    async def test_contradictions_extracted(self):
        """Contradictions are extracted from graph CONTRADICTS edges."""
        data = {
            "name": "conflict-graph",
            "nodes": [
                {
                    "id": "a",
                    "type": "T",
                    "properties": {
                        "name": "A",
                        "credibility": 0.8,
                        "description": "Claim A",
                    },
                },
                {
                    "id": "b",
                    "type": "T",
                    "properties": {
                        "name": "B",
                        "credibility": 0.6,
                        "description": "Claim B",
                    },
                },
            ],
            "edges": [
                {
                    "from_id": "a",
                    "to_id": "b",
                    "relation": "CONTRADICTS",
                    "weight": 0.6,
                },
            ],
        }
        graph = load_graph(data)
        traverser = GraphTraverser(graph)
        result = traverser.find_by_relation("CONTRADICTS")
        synthesizer = ReportSynthesizer()
        report = await synthesizer.synthesize(graph, result)
        assert len(report.contradictions) >= 1


# ============================================================================
# generate_report Convenience Function Tests
# ============================================================================


class TestGenerateReport:
    @pytest.mark.asyncio
    async def test_generate_report_basic(self, sample_graph):
        report = await generate_report(sample_graph, "langchain", use_llm=False)
        assert isinstance(report, Report)
        assert report.title

    @pytest.mark.asyncio
    async def test_generate_report_saves_file(self, sample_graph, tmp_path):
        out = tmp_path / "out.md"
        await generate_report(sample_graph, "langchain", use_llm=False, output_path=out)
        assert out.exists()
        assert "langchain" in out.read_text().lower()

    @pytest.mark.asyncio
    async def test_generate_report_with_mock_llm(self, sample_graph):
        mock_llm = MockLLMClient()
        report = await generate_report(
            sample_graph,
            "neo4j",
            use_llm=True,
            llm_client=mock_llm,
        )
        assert isinstance(report, Report)
