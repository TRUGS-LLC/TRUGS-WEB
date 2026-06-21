"""
Report Synthesis Module

Generates Markdown reports from graph traversal results.
Optionally uses LLMs for richer insights.

LLMClient and MockLLMClient are reused from trugs_tools.web.extractor.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..extractor import LLMClient, MockLLMClient  # noqa: F401 – re-exported
from .traverse import GraphTraverser


# ============================================================================
# Report Data Structures
# ============================================================================


@dataclass
class Finding:
    """A single finding from the graph."""

    statement: str
    source_name: str
    source_url: Optional[str]
    weight: float
    evidence: str = ""

    def to_markdown(self):
        """Render as markdown."""
        weight_indicator = (
            "🟢" if self.weight >= 0.7 else "🟡" if self.weight >= 0.4 else "🔴"
        )

        if self.source_url:
            source_ref = f"[{self.source_name}]({self.source_url})"
        else:
            source_ref = self.source_name

        return (
            f"- {weight_indicator} **{self.statement}** (weight: {self.weight:.2f})\n"
            f"  - Source: {source_ref}"
        )


@dataclass
class Report:
    """A synthesized report from graph data."""

    title: str
    query: str
    graph_id: str
    generated: str = field(default_factory=lambda: datetime.now().isoformat()[:19])

    # Content
    summary: str = ""
    findings: list = field(default_factory=list)
    contradictions: list = field(default_factory=list)
    recommendations: list = field(default_factory=list)

    # Metadata
    source_count: int = 0
    high_credibility_count: int = 0
    avg_weight: float = 0.0

    def to_markdown(self):
        """Render full report as markdown."""
        lines = [
            f"# {self.title}",
            "",
            f"**Query:** {self.query}",
            f"**Generated:** {self.generated}",
            f"**Graph:** {self.graph_id}",
            "",
            "---",
            "",
        ]

        if self.summary:
            lines.extend(
                [
                    "## Summary",
                    "",
                    self.summary,
                    "",
                ]
            )

        lines.extend(
            [
                "## Statistics",
                "",
                f"- **Sources analyzed:** {self.source_count}",
                f"- **High-credibility sources:** {self.high_credibility_count}",
                f"- **Average weight:** {self.avg_weight:.2f}",
                "",
            ]
        )

        if self.findings:
            lines.extend(["## Key Findings", ""])

            high = [f for f in self.findings if f.weight >= 0.7]
            medium = [f for f in self.findings if 0.4 <= f.weight < 0.7]
            low = [f for f in self.findings if f.weight < 0.4]

            if high:
                lines.append("### High Confidence")
                lines.append("")
                for finding in high[:5]:
                    lines.append(finding.to_markdown())
                lines.append("")

            if medium:
                lines.append("### Medium Confidence")
                lines.append("")
                for finding in medium[:5]:
                    lines.append(finding.to_markdown())
                lines.append("")

            if low:
                lines.append("### Low Confidence ⚠️")
                lines.append("")
                for finding in low[:3]:
                    lines.append(finding.to_markdown())
                lines.append("")

        if self.contradictions:
            lines.extend(
                [
                    "## Contradictions Detected",
                    "",
                    "| Claim A | Claim B | Weights |",
                    "|---------|---------|---------|",
                ]
            )
            for a, b in self.contradictions:
                lines.append(
                    f"| {a.statement} | {b.statement} | {a.weight:.2f} vs {b.weight:.2f} |"
                )
            lines.append("")

        if self.recommendations:
            lines.extend(["## Recommendations", ""])
            for i, rec in enumerate(self.recommendations, 1):
                lines.append(f"{i}. {rec}")
            lines.append("")

        lines.extend(["---", "", "## Sources", ""])

        seen_sources = set()
        for finding in self.findings:
            if finding.source_name not in seen_sources:
                seen_sources.add(finding.source_name)
                if finding.source_url:
                    lines.append(f"- [{finding.source_name}]({finding.source_url})")
                else:
                    lines.append(f"- {finding.source_name}")

        return "\n".join(lines)

    def save(self, path):
        """Save report to file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_markdown())


# ============================================================================
# Report Synthesizer
# ============================================================================

SYNTHESIS_PROMPT = """Analyze these findings from a knowledge graph and provide a concise summary.

QUERY: {query}

FINDINGS:
{findings}

HIGH CREDIBILITY SOURCES ({high_count}):
{high_sources}

Provide:
1. A 2-3 sentence summary of the key insights
2. Any notable patterns or trends
3. Recommendations based on the data

Keep response under 300 words. Be factual and cite sources by name."""


class ReportSynthesizer:
    """
    Generates reports from graph traversal results.

    Modes:

    * **Basic** – no LLM, structured findings only.
    * **Enhanced** – uses ``LLMClient`` from ``trugs_tools.web.extractor``
      for richer synthesis.
    """

    def __init__(self, llm_client=None, use_llm=False):
        self.llm = llm_client
        self.use_llm = use_llm and llm_client is not None

    async def synthesize(self, graph, result, title=None):
        """
        Synthesize a report from traversal results.

        Args:
            graph: The source graph.
            result: TraversalResult to synthesize.
            title: Optional report title.

        Returns:
            Report object.
        """
        report = Report(
            title=title or f"Report: {result.query}",
            query=result.query,
            graph_id=graph.meta.id,
            source_count=len(result.nodes),
            high_credibility_count=result.high_credibility_count,
            avg_weight=result.avg_weight,
        )

        report.findings = self._extract_findings(result)

        traverser = GraphTraverser(graph)
        contradictions = traverser.find_by_relation("CONTRADICTS")
        report.contradictions = self._extract_contradictions(contradictions)

        if self.use_llm:
            report.summary = await self._llm_summary(result, report.findings)
            report.recommendations = await self._llm_recommendations(
                result, report.findings
            )
        else:
            report.summary = self._basic_summary(result, report.findings)
            report.recommendations = self._basic_recommendations(
                result, report.findings
            )

        return report

    def _extract_findings(self, result):
        """Extract findings from traversal result."""
        findings = []

        for edge in result.edges:
            source_node = None
            for node in result.nodes:
                if node.id == edge.from_id:
                    source_node = node
                    break

            if source_node:
                findings.append(
                    Finding(
                        statement=f"{source_node.name} → {edge.relation} → {edge.to_id}",
                        source_name=source_node.name,
                        source_url=source_node.url,
                        weight=edge.weight,
                    )
                )

        if not findings:
            for node in result.nodes:
                findings.append(
                    Finding(
                        statement=node.description or f"{node.name} ({node.type})",
                        source_name=node.name,
                        source_url=node.url,
                        weight=node.credibility,
                    )
                )

        findings.sort(key=lambda f: f.weight, reverse=True)
        return findings

    def _extract_contradictions(self, result):
        """Extract contradiction pairs."""
        contradictions = []

        for edge in result.edges:
            if edge.relation == "CONTRADICTS":
                from_node = None
                to_node = None

                for node in result.nodes:
                    if node.id == edge.from_id:
                        from_node = node
                    if node.id == edge.to_id:
                        to_node = node

                if from_node and to_node:
                    a = Finding(
                        statement=from_node.description or from_node.name,
                        source_name=from_node.name,
                        source_url=from_node.url,
                        weight=from_node.credibility,
                    )
                    b = Finding(
                        statement=to_node.description or to_node.name,
                        source_name=to_node.name,
                        source_url=to_node.url,
                        weight=to_node.credibility,
                    )
                    contradictions.append((a, b))

        return contradictions

    def _basic_summary(self, result, findings):
        """Generate basic summary without LLM."""
        if not findings:
            return "No relevant findings for this query."

        high_cred = [f for f in findings if f.weight >= 0.7]
        parts = []

        if high_cred:
            parts.append(
                f"Found {len(high_cred)} high-confidence source(s) "
                f"out of {len(findings)} total."
            )
            top = high_cred[0]
            parts.append(
                f"Top source: **{top.source_name}** (weight: {top.weight:.2f})."
            )
        else:
            parts.append(
                f"Found {len(findings)} source(s), but none with high confidence (>0.7)."
            )
            parts.append("Results should be verified with additional research.")

        return " ".join(parts)

    def _basic_recommendations(self, result, findings):
        """Generate basic recommendations without LLM."""
        recommendations = []

        if result.high_credibility_count == 0:
            recommendations.append(
                "Consider finding peer-reviewed sources to validate these findings."
            )

        if result.avg_weight < 0.5:
            recommendations.append(
                "Average source credibility is low. "
                "Cross-reference with authoritative sources."
            )

        if len(findings) < 3:
            recommendations.append(
                "Limited sources found. Expand search to build more comprehensive "
                "understanding."
            )

        if not recommendations:
            recommendations.append("Results appear well-supported by credible sources.")

        return recommendations

    async def _llm_summary(self, result, findings):
        """Generate LLM-enhanced summary."""
        if not self.llm:
            return self._basic_summary(result, findings)

        findings_text = "\n".join(
            [
                f"- {f.source_name}: {f.statement} (weight: {f.weight:.2f})"
                for f in findings[:10]
            ]
        )

        high_sources = "\n".join(
            [f"- {f.source_name}" for f in findings if f.weight >= 0.7][:5]
        )

        prompt = SYNTHESIS_PROMPT.format(
            query=result.query,
            findings=findings_text,
            high_count=result.high_credibility_count,
            high_sources=high_sources or "None",
        )

        try:
            response = await self.llm.complete(prompt)
            return response
        except Exception:  # noqa: BLE001 – unknown client error type; fall back gracefully
            return self._basic_summary(result, findings)

    async def _llm_recommendations(self, result, findings):
        """LLM recommendations (delegates to basic for now)."""
        return self._basic_recommendations(result, findings)


# ============================================================================
# Convenience Function
# ============================================================================


async def generate_report(
    graph,
    query,
    min_weight=0.5,
    use_llm=False,
    llm_client=None,
    output_path=None,
):
    """
    Generate a report for a query against a graph.

    Args:
        graph: The knowledge graph.
        query: User query string.
        min_weight: Minimum edge weight for filtering.
        use_llm: Whether to use LLM for synthesis.
        llm_client: LLM client for enhanced synthesis.
        output_path: Optional path to save the report.

    Returns:
        Report object.
    """
    from .traverse import query_graph

    result = query_graph(graph, query, min_weight)
    synthesizer = ReportSynthesizer(llm_client, use_llm)
    report = await synthesizer.synthesize(graph, result)

    if output_path is not None:
        report.save(output_path)

    return report
