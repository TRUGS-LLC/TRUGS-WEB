"""
Orchestrator — full pipeline from URLs to a validated TRUGS 1.0 graph.

Pipeline stages:
  1. **Discover** — crawl seed URLs via ``SourceDiscoverer``.
  2. **Extract** — pull entities and relations via ``EntityExtractor`` /
     ``RelationExtractor``.
  3. **Resolve** — deduplicate entities via ``EntityResolver``.
  4. **Score** — weight edges via ``CredibilityScorer``.
  5. **Build** — assemble a TRUGS 1.0 graph via ``TRUGSWebGraphBuilder``.
  6. **Validate** — run the validator and return the result.

This was T-05 from Phase 1, deferred to Phase 3 because it needs the
full pipeline in place (crawler + extractor + resolver + credibility +
graph builder + query).

Reuses existing modules — no new dependencies.
"""

from dataclasses import dataclass, field
from typing import Optional

from ..crawler import Source, SourceDiscoverer
from ..extractor import (
    Entity,
    EntityExtractor,
    Relation,
    RelationExtractor,
    create_extractor,
)
from ..resolver import EntityResolver, ResolvedEntity, CrossReferenceMapper
from ..credibility import CredibilityScorer
from ..graph_builder import TRUGSWebGraphBuilder, url_to_id, make_id


# ============================================================================
# Result
# ============================================================================

@dataclass
class PipelineResult:
    """
    Outcome of a full orchestration run.

    Attributes:
        builder:   The populated TRUGSWebGraphBuilder.
        sources:   Discovered sources.
        entities:  Resolved entities.
        relations: Extracted relations.
        errors:    Non-fatal errors encountered during the run.
    """

    builder: Optional[TRUGSWebGraphBuilder] = None
    sources: list = field(default_factory=list)
    entities: list = field(default_factory=list)
    relations: list = field(default_factory=list)
    errors: list = field(default_factory=list)

    @property
    def node_count(self) -> int:
        if self.builder is None:
            return 0
        return len(self.builder.graph.get("nodes", []))

    @property
    def edge_count(self) -> int:
        if self.builder is None:
            return 0
        return len(self.builder.graph.get("edges", []))

    @property
    def graph_dict(self) -> Optional[dict]:
        if self.builder is None:
            return None
        return self.builder.to_dict()


# ============================================================================
# Orchestrator
# ============================================================================

class Orchestrator:
    """
    End-to-end pipeline: discover → extract → resolve → score → build.

    Wraps the same logic as ``graph_builder._WebPipeline`` but exposes
    each stage for inspection and provides a structured ``PipelineResult``.

    Usage::

        orch = Orchestrator(topic="machine learning")
        result = await orch.run(["https://example.com"])
        print(result.node_count, result.edge_count)
        result.builder.save("output.trug.json")

    Args:
        topic:         Research topic.
        description:   Graph description.
        llm_provider:  "mock", "anthropic", or "openai".
        api_key:       API key for real LLM providers.
        model:         Optional model override.
        max_sources:   Maximum number of sources to crawl.
        max_depth:     Maximum crawl depth.
    """

    def __init__(
        self,
        topic: str,
        description: str = "",
        llm_provider: str = "mock",
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        max_sources: int = 50,
        max_depth: int = 2,
    ):
        self.topic = topic
        self.description = description or f"Web research graph for: {topic}"
        self.llm_provider = llm_provider
        self.api_key = api_key
        self.model = model
        self.max_sources = max_sources
        self.max_depth = max_depth

    async def run(self, seed_urls: list) -> PipelineResult:
        """
        Execute the full pipeline.

        .. note::

           This method intentionally duplicates the logic of
           ``graph_builder._WebPipeline.run()`` so that each stage can
           be wrapped in per-stage error collection and the intermediate
           results (sources, entities, relations) can be surfaced in the
           returned ``PipelineResult``.  A future refactor may extract
           shared pipeline logic into a common helper.

        Args:
            seed_urls: Starting URLs to crawl.

        Returns:
            PipelineResult with builder, sources, entities, relations.
        """
        result = PipelineResult()

        # Init components
        discoverer = SourceDiscoverer(
            max_sources=self.max_sources,
            max_depth=self.max_depth,
        )
        entity_extractor, relation_extractor = create_extractor(
            provider=self.llm_provider,
            api_key=self.api_key,
            model=self.model,
        )
        resolver = EntityResolver()
        scorer = CredibilityScorer()
        cross_ref_mapper = CrossReferenceMapper()

        graph_id = make_id(self.topic)
        builder = TRUGSWebGraphBuilder(
            name=graph_id,
            topic=self.topic,
            description=self.description,
        )
        result.builder = builder

        # Stage 1: Discover
        try:
            sources: list = await discoverer.discover(seed_urls, self.topic)
        except Exception as exc:
            result.errors.append(f"Discovery failed: {exc}")
            sources = []
        result.sources = sources

        # Stage 2a: Add source nodes
        for source in sources:
            try:
                factors = scorer.score_source(source)
                builder.add_source_node(source, credibility=factors.total)
            except Exception as exc:
                result.errors.append(f"Source scoring failed for {source.url}: {exc}")

        # Stage 2b: Extract entities
        all_entities: list = []
        for source in sources:
            if source.content:
                try:
                    entities = await entity_extractor.extract(source)
                    all_entities.extend(entities)
                    for entity in entities:
                        cross_ref_mapper.map_entity_to_source(entity.id, source.url)
                except Exception as exc:
                    result.errors.append(
                        f"Entity extraction failed for {source.url}: {exc}"
                    )

        # Stage 3: Resolve entities
        try:
            resolved_entities = resolver.resolve(all_entities)
        except Exception as exc:
            result.errors.append(f"Entity resolution failed: {exc}")
            resolved_entities = []
        result.entities = resolved_entities

        # Add entity nodes
        for entity in resolved_entities:
            try:
                builder.add_entity_node(entity)
            except Exception as exc:
                result.errors.append(
                    f"Entity node creation failed for {entity.canonical_name}: {exc}"
                )

        # Stage 4: Extract and score relations
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
                try:
                    relations = await relation_extractor.extract(source, entity_list)
                    all_relations.extend(relations)
                except Exception as exc:
                    result.errors.append(
                        f"Relation extraction failed for {source.url}: {exc}"
                    )
        result.relations = all_relations

        # Stage 5: Add edges with weights
        for relation in all_relations:
            try:
                source = source_map.get(relation.source_url)
                weight = scorer.score_edge(relation, from_source=source)
                builder.add_relation_edge(relation, weight=weight)
            except Exception as exc:
                result.errors.append(f"Edge creation failed: {exc}")

        # Cross-reference MENTIONS edges
        try:
            cross_refs = cross_ref_mapper.find_cross_references(resolved_entities)
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
        except Exception as exc:
            result.errors.append(f"Cross-reference mapping failed: {exc}")

        return result

    async def run_and_save(
        self,
        seed_urls: list,
        output_path: str,
        validate: bool = True,
    ) -> PipelineResult:
        """
        Run the pipeline and save the resulting graph.

        Args:
            seed_urls:   Starting URLs.
            output_path: File path for the output .trug.json.
            validate:    Whether to validate before saving.

        Returns:
            PipelineResult.
        """
        result = await self.run(seed_urls)
        if result.builder is not None:
            try:
                result.builder.save(output_path, validate=validate)
            except Exception as exc:
                result.errors.append(f"Save failed: {exc}")
        return result
