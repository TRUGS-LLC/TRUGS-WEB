"""
Entity Resolution Module

Resolves and deduplicates entities across multiple sources.
Handles alias detection, cross-reference mapping, and entity merging.
"""

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from .extractor import Entity, _entity_metric_level


@dataclass
class ResolvedEntity:
    """An entity after resolution (potentially merged from multiple sources)."""

    id: str
    canonical_name: str
    entity_type: str
    description: str = ""
    aliases: list = field(default_factory=list)
    source_urls: list = field(default_factory=list)
    mention_count: int = 1
    metadata: dict = field(default_factory=dict)

    def to_node(self) -> dict:
        """Convert to TRUGS 1.0 node format."""
        metric_level = _entity_metric_level(self.entity_type)
        return {
            "id": self.id,
            "type": self.entity_type,
            "properties": {
                "name": self.canonical_name,
                "description": self.description,
                "aliases": self.aliases,
                "source_urls": self.source_urls,
                "mention_count": self.mention_count,
            },
            "metric_level": metric_level,
            "parent_id": None,
            "contains": [],
            "dimension": "web_structure",
        }


class EntityResolver:
    """
    Resolves entities across multiple sources.

    Uses string similarity and known aliases to identify when different
    names refer to the same entity.
    """

    def __init__(
        self,
        similarity_threshold: float = 0.85,
        case_sensitive: bool = False,
    ):
        self.similarity_threshold = similarity_threshold
        self.case_sensitive = case_sensitive

        self.known_aliases: dict = {
            "langchain": {"lang chain", "lang-chain"},
            "langgraph": {"lang graph", "lang-graph"},
            "neo4j": {"neo 4j"},
            "gpt-4": {"gpt4", "gpt 4"},
            "gpt-3.5": {"gpt3.5", "gpt 3.5", "chatgpt"},
            "graphrag": {"graph rag", "graph-rag"},
            "pytorch": {"py torch", "torch"},
            "tensorflow": {"tensor flow", "tf"},
        }

    def resolve(self, entities: list) -> list:
        """
        Resolve a list of entities, merging duplicates.

        Args:
            entities: Raw extracted Entity objects

        Returns:
            List of ResolvedEntity objects
        """
        if not entities:
            return []

        by_type: dict = {}
        for entity in entities:
            by_type.setdefault(entity.entity_type, []).append(entity)

        resolved: list = []
        for entity_type, type_entities in by_type.items():
            type_resolved = self._resolve_type(type_entities)
            resolved.extend(type_resolved)

        return resolved

    def _resolve_type(self, entities: list) -> list:
        """Resolve entities of the same type."""
        clusters: list = []

        for entity in entities:
            matched = False
            for cluster in clusters:
                if self._should_merge(entity, cluster[0]):
                    cluster.append(entity)
                    matched = True
                    break
            if not matched:
                clusters.append([entity])

        return [self._merge_cluster(c) for c in clusters]

    def _should_merge(self, entity: Entity, representative: Entity) -> bool:
        """Check if entity should merge with cluster representative."""
        name1 = entity.name if self.case_sensitive else entity.name.lower()
        name2 = (
            representative.name if self.case_sensitive else representative.name.lower()
        )

        if name1 == name2:
            return True

        for canonical, aliases in self.known_aliases.items():
            all_names = {canonical} | aliases
            if name1 in all_names and name2 in all_names:
                return True

        if name1 in [a.lower() for a in representative.aliases]:
            return True
        if name2 in [a.lower() for a in entity.aliases]:
            return True

        if self._similarity(name1, name2) >= self.similarity_threshold:
            return True

        norm1 = self._normalize(name1)
        norm2 = self._normalize(name2)
        if (
            norm1
            and norm2
            and self._similarity(norm1, norm2) >= self.similarity_threshold
        ):
            return True

        return False

    def _similarity(self, s1: str, s2: str) -> float:
        """Calculate string similarity ratio."""
        return SequenceMatcher(None, s1, s2).ratio()

    def _normalize(self, name: str) -> str:
        """Normalize entity name for comparison."""
        suffixes = ["framework", "library", "tool", "database", "db", "ai", "ml"]
        name = name.lower().strip()
        for suffix in suffixes:
            if name.endswith(suffix):
                name = name[: -len(suffix)].strip()
        name = re.sub(r"[^a-z0-9\s]", "", name)
        name = re.sub(r"\s+", " ", name).strip()
        return name

    def _merge_cluster(self, cluster: list) -> ResolvedEntity:
        """Merge a cluster of entities into one resolved entity."""
        if len(cluster) == 1:
            e = cluster[0]
            return ResolvedEntity(
                id=e.id,
                canonical_name=e.name,
                entity_type=e.entity_type,
                description=e.description,
                aliases=e.aliases,
                source_urls=[e.source_url] if e.source_url else [],
                mention_count=1,
                metadata=e.metadata,
            )

        names = [e.name for e in cluster]
        canonical = max(set(names), key=lambda n: (names.count(n), len(n)))

        all_aliases: set = set()
        for e in cluster:
            all_aliases.update(e.aliases)
            if e.name.lower() != canonical.lower():
                all_aliases.add(e.name)

        source_urls = list(set(e.source_url for e in cluster if e.source_url))
        descriptions = [e.description for e in cluster if e.description]
        description = max(descriptions, key=len) if descriptions else ""
        entity_id = self._make_id(canonical)

        return ResolvedEntity(
            id=entity_id,
            canonical_name=canonical,
            entity_type=cluster[0].entity_type,
            description=description,
            aliases=list(all_aliases),
            source_urls=source_urls,
            mention_count=len(cluster),
            metadata={"merged_from": len(cluster)},
        )

    def _make_id(self, name: str) -> str:
        """Generate valid ID from name."""
        id_str = name.lower()
        id_str = re.sub(r"[^a-z0-9\s-]", "", id_str)
        id_str = re.sub(r"\s+", "-", id_str)
        return id_str[:50]


class CrossReferenceMapper:
    """
    Maps cross-references between entities and sources.

    Identifies when entities appear across multiple sources.
    """

    def __init__(self):
        self.url_to_entity: dict = {}
        self.entity_to_urls: dict = {}

    def map_entity_to_source(self, entity_id: str, source_url: str) -> None:
        """Record that an entity appears in a source."""
        self.url_to_entity.setdefault(source_url, []).append(entity_id)
        self.entity_to_urls.setdefault(entity_id, []).append(source_url)

    def find_cross_references(self, entities: list) -> list:
        """
        Find entities that appear in multiple sources.

        Returns list of cross-reference records.
        """
        cross_refs = []
        for entity in entities:
            if len(entity.source_urls) > 1:
                cross_refs.append(
                    {
                        "entity_id": entity.id,
                        "entity_name": entity.canonical_name,
                        "source_count": len(entity.source_urls),
                        "sources": entity.source_urls,
                    }
                )
        return cross_refs

    def find_connected_sources(self, source_url: str, entities: list) -> list:
        """Find other sources connected through shared entities."""
        entity_ids = self.url_to_entity.get(source_url, [])
        connected: set = set()
        for entity_id in entity_ids:
            urls = self.entity_to_urls.get(entity_id, [])
            connected.update(urls)
        connected.discard(source_url)
        return list(connected)


def resolve_entities(entities: list) -> list:
    """
    Convenience function to resolve entities.

    Args:
        entities: Raw extracted Entity objects

    Returns:
        Resolved (deduplicated) ResolvedEntity list
    """
    resolver = EntityResolver()
    return resolver.resolve(entities)
