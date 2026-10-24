"""Stable JSON and readable text for existing traversal results."""

from dataclasses import asdict

from .traverse import TraversalResult


def result_object(result: TraversalResult) -> dict:
    data = asdict(result)
    data["schema_version"] = "1.0.0"
    return data


def result_text(result: TraversalResult) -> str:
    lines = [
        f"Query: {result.query}",
        f"{len(result.nodes)} node(s), {len(result.edges)} edge(s)",
    ]
    for node in result.nodes:
        lines.append(f"  {node.id} [{node.type}]: {node.name}")
        if node.url:
            lines.append(f"    {node.url}")
    for edge in result.edges:
        lines.append(
            f"  {edge.from_id} {edge.relation} {edge.to_id} (weight {edge.weight:g})"
        )
    return "\n".join(lines)
