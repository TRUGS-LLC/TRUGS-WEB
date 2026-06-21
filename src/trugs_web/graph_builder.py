"""
TRUGS Web Graph Builder

Orchestrates the Phase 1 pipeline (discover → extract → resolve → score)
and emits TRUGS 1.0-format graphs validated by trugs_tools.validator.

Output structure follows TRUGS_RESEARCH/CRAWLER/graph_builder.py:
  {
    "name": <topic>,
    "version": "1.0.0",
    "type": "RESEARCH",
    "dimensions": {...},
    "capabilities": {...},
    "nodes": [...],
    "edges": [...]
  }

Node fields: id, type, properties, metric_level, parent_id, contains, dimension
Edge fields: from_id, to_id, relation  (+ optional weight)
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Optional
from urllib.parse import urlparse

from .crawler import Source, SourceDiscoverer
from .extractor import Entity, Relation, create_extractor
from .resolver import EntityResolver, ResolvedEntity, CrossReferenceMapper
from .credibility import CredibilityScorer

if TYPE_CHECKING:
    from trugs_tools.validator import ValidationResult


# ============================================================================
# TRUGS 1.0 Graph Builder
# ============================================================================


class TRUGSWebGraphBuilder:
    """
    Builds a TRUGS 1.0 research graph from web sources.

    Usage (async):
        builder = TRUGSWebGraphBuilder(llm_provider="mock")
        graph = await builder.build("machine learning", seed_urls)
        builder.save("output.trug.json")
    """

    def __init__(self, name: str, topic: str, description: str = ""):
        self.graph: dict = {
            "name": name,
            "version": "1.0.0",
            "type": "RESEARCH",
            "dimensions": {
                "web_structure": {
                    "description": topic,
                    "base_level": "BASE",
                }
            },
            "capabilities": {
                "extensions": [],
                "vocabularies": ["research_v1"],
                "profiles": [],
            },
            "nodes": [],
            "edges": [],
        }
        self._ids: set = set()

        # Root node
        root_id = f"research_graph_{re.sub(r'[^a-z0-9]', '_', name.lower())}"
        self._add_node(
            node_id=root_id,
            node_type="RESEARCH_GRAPH",
            properties={
                "name": name,
                "topic": topic,
                "description": description,
                "created_date": datetime.now().strftime("%Y-%m-%d"),
            },
            metric_level="KILO_RESEARCH_GRAPH",
            parent_id=None,
        )
        self._root_id = root_id

    def _add_node(
        self,
        node_id: str,
        node_type: str,
        properties: dict,
        metric_level: str,
        parent_id: Optional[str] = None,
    ) -> str:
        """Add a node to the graph (internal). Returns node_id."""
        if node_id in self._ids:
            return node_id  # Idempotent: skip duplicates

        effective_parent = (
            parent_id
            if parent_id is not None
            else (self._root_id if hasattr(self, "_root_id") else None)
        )

        node: dict = {
            "id": node_id,
            "type": node_type,
            "properties": properties,
            "metric_level": metric_level,
            "parent_id": effective_parent,
            "contains": [],
            "dimension": "web_structure",
        }
        self.graph["nodes"].append(node)
        self._ids.add(node_id)

        # Update parent contains list + add contains edge
        if effective_parent:
            for n in self.graph["nodes"]:
                if n["id"] == effective_parent and node_id not in n["contains"]:
                    n["contains"].append(node_id)
                    break
            self.graph["edges"].append(
                {
                    "from_id": effective_parent,
                    "to_id": node_id,
                    "relation": "contains",
                }
            )

        return node_id

    def add_source_node(self, source: Source, credibility: float = 0.5) -> str:
        """Add a WEB_SOURCE node. Returns node_id."""
        node_id = _url_to_id(source.url)
        self._add_node(
            node_id=node_id,
            node_type=source.source_type,
            properties={
                "name": source.title or source.url,
                "url": source.url,
                "description": source.description,
                "domain": source.domain,
                "credibility": round(credibility, 3),
            },
            metric_level=f"BASE_{source.source_type}",
        )
        return node_id

    def add_entity_node(self, entity: ResolvedEntity) -> str:
        """Add an entity node from a ResolvedEntity. Returns node_id."""
        node = entity.to_node()
        # Parent defaults to root via _add_node logic
        self._add_node(
            node_id=node["id"],
            node_type=node["type"],
            properties=node["properties"],
            metric_level=node["metric_level"],
        )
        return node["id"]

    def add_relation_edge(self, relation: Relation, weight: float) -> None:
        """Add a relation edge with computed weight."""
        if not relation.from_id or not relation.to_id:
            return
        # Only add if both endpoints exist
        if relation.from_id not in self._ids or relation.to_id not in self._ids:
            return
        self._add_edge(
            from_id=relation.from_id,
            to_id=relation.to_id,
            relation=relation.relation_type,
            weight=round(weight, 3),
        )

    def has_node(self, node_id: str) -> bool:
        """Return True if a node with *node_id* exists in the graph."""
        return node_id in self._ids

    def add_edge(
        self,
        from_id: str,
        to_id: str,
        relation: str,
        weight: Optional[float] = None,
    ) -> None:
        """Add an edge if not already present (public API)."""
        self._add_edge(from_id=from_id, to_id=to_id, relation=relation, weight=weight)

    def _add_edge(
        self,
        from_id: str,
        to_id: str,
        relation: str,
        weight: Optional[float] = None,
    ) -> None:
        """Add an edge if not already present."""
        for existing in self.graph["edges"]:
            if (
                existing["from_id"] == from_id
                and existing["to_id"] == to_id
                and existing["relation"] == relation
            ):
                return
        edge: dict = {"from_id": from_id, "to_id": to_id, "relation": relation}
        if weight is not None:
            edge["weight"] = weight
        self.graph["edges"].append(edge)

    def to_dict(self) -> dict:
        """Return the graph as a plain dictionary."""
        return self.graph

    def to_json(self, indent: int = 2) -> str:
        """Return the graph as a JSON string."""
        return json.dumps(self.graph, indent=indent)

    def validate(self) -> "ValidationResult":
        """Validate the graph with trugs_tools.validator."""
        from trugs_tools.validator import validate_trug

        return validate_trug(self.graph)

    def save(self, filepath: str, validate: bool = True) -> dict:
        """
        Save graph to a .trug.json file.

        Args:
            filepath: Output path
            validate: If True, validate before saving (raises ValueError on failure)

        Returns:
            Summary dict with saved path and counts
        """
        if validate:
            result = self.validate()
            if not result.valid:
                raise ValueError(
                    "Graph validation failed:\n"
                    + "\n".join(str(e) for e in result.errors)
                )

        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json())
        return {
            "saved": filepath,
            "nodes": len(self.graph["nodes"]),
            "edges": len(self.graph["edges"]),
        }


# ============================================================================
# High-level orchestrator
# ============================================================================


class _WebPipeline:
    """
    Internal pipeline that runs: discover → extract → resolve → score → graph.
    """

    def __init__(
        self,
        llm_provider: str = "mock",
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        max_sources: int = 50,
        max_depth: int = 2,
    ):
        self.discoverer = SourceDiscoverer(max_sources=max_sources, max_depth=max_depth)
        self.entity_extractor, self.relation_extractor = create_extractor(
            provider=llm_provider, api_key=api_key, model=model
        )
        self.resolver = EntityResolver()
        self.scorer = CredibilityScorer()
        self.cross_ref_mapper = CrossReferenceMapper()

    async def run(self, topic: str, seed_urls: list) -> TRUGSWebGraphBuilder:
        """Run the full pipeline and return a populated TRUGSWebGraphBuilder."""
        graph_id = make_id(topic)
        builder = TRUGSWebGraphBuilder(
            name=graph_id,
            topic=topic,
            description=f"Web research graph for: {topic}",
        )

        # Phase 1a: Discover sources
        sources: list = await self.discoverer.discover(seed_urls, topic)

        # Add source nodes
        for source in sources:
            factors = self.scorer.score_source(source)
            builder.add_source_node(source, credibility=factors.total)

        # Phase 1b: Extract entities
        all_entities: list = []
        for source in sources:
            if source.content:
                entities = await self.entity_extractor.extract(source)
                all_entities.extend(entities)
                for entity in entities:
                    self.cross_ref_mapper.map_entity_to_source(entity.id, source.url)

        # Phase 1c: Resolve entities
        resolved_entities = self.resolver.resolve(all_entities)

        # Add entity nodes
        for entity in resolved_entities:
            builder.add_entity_node(entity)

        # Phase 1d: Extract relations
        entity_list = [
            Entity(
                id=e.id,
                name=e.canonical_name,
                entity_type=e.entity_type,
                description=e.description,
                aliases=e.aliases,
            )
            for e in resolved_entities
        ]
        source_map = {s.url: s for s in sources}
        all_relations: list = []
        for source in sources:
            if source.content:
                relations = await self.relation_extractor.extract(source, entity_list)
                all_relations.extend(relations)

        # Phase 1e: Score edges
        for relation in all_relations:
            source = source_map.get(relation.source_url)
            weight = self.scorer.score_edge(relation, from_source=source)
            builder.add_relation_edge(relation, weight=weight)

        # Cross-reference MENTIONS edges
        cross_refs = self.cross_ref_mapper.find_cross_references(resolved_entities)
        for ref in cross_refs:
            for source_url in ref["sources"]:
                source_id = url_to_id(source_url)
                if builder.has_node(source_id) and builder.has_node(ref["entity_id"]):
                    builder.add_edge(
                        from_id=source_id,
                        to_id=ref["entity_id"],
                        relation="MENTIONS",
                        weight=0.5,
                    )

        return builder


# ============================================================================
# Convenience Functions
# ============================================================================


async def build_graph(
    topic: str,
    seed_urls: list,
    llm_provider: str = "mock",
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    output_path: Optional[str] = None,
    validate: bool = True,
) -> TRUGSWebGraphBuilder:
    """
    Build a TRUGS 1.0 research graph from web sources.

    Args:
        topic: Research topic
        seed_urls: Starting URLs to crawl
        llm_provider: "mock", "anthropic", or "openai"
        api_key: API key for LLM provider
        model: Optional model override
        output_path: Optional path to save the graph
        validate: Whether to validate before saving

    Returns:
        TRUGSWebGraphBuilder with the completed TRUGS 1.0 graph
    """
    pipeline = _WebPipeline(
        llm_provider=llm_provider,
        api_key=api_key,
        model=model,
    )
    builder = await pipeline.run(topic, seed_urls)

    if output_path:
        builder.save(output_path, validate=validate)

    return builder


def load_graph(filepath: str) -> dict:
    """Load a TRUGS 1.0 graph from a .trug.json file."""
    path = Path(filepath)
    return json.loads(path.read_text())


# ============================================================================
# Helpers
# ============================================================================


def url_to_id(url: str) -> str:
    """Convert URL to valid TRUGS node ID."""
    parsed = urlparse(url)
    id_str = f"{parsed.netloc}{parsed.path}".lower()
    id_str = re.sub(r"[^a-z0-9]", "-", id_str)
    id_str = re.sub(r"-+", "-", id_str).strip("-")
    return id_str[:80]


def make_id(text: str) -> str:
    """Make valid ID from text."""
    id_str = text.lower()
    id_str = re.sub(r"[^a-z0-9\s]", "", id_str)
    id_str = re.sub(r"\s+", "-", id_str)
    return id_str[:50]


# Backward-compatible aliases (deprecated)
_url_to_id = url_to_id
_make_id = make_id
