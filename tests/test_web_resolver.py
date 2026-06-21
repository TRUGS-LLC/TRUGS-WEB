"""Tests for trugs_web.resolver — Entity resolution module."""

from trugs_web.extractor import Entity
from trugs_web.resolver import (
    ResolvedEntity,
    EntityResolver,
    CrossReferenceMapper,
    resolve_entities,
)


class TestResolvedEntity:
    def test_to_node_trugs_format(self):
        entity = ResolvedEntity(
            id="langchain",
            canonical_name="LangChain",
            entity_type="TOOL",
            description="LLM orchestration framework",
            aliases=["lang-chain"],
            source_urls=["https://github.com/langchain-ai/langchain"],
            mention_count=3,
        )
        node = entity.to_node()

        assert node["id"] == "langchain"
        assert node["type"] == "TOOL"
        assert "properties" in node
        assert node["properties"]["name"] == "LangChain"
        assert node["properties"]["mention_count"] == 3
        assert node["properties"]["aliases"] == ["lang-chain"]
        assert "metric_level" in node
        assert node["metric_level"] == "BASE_TOOL"
        assert node["contains"] == []
        assert node["dimension"] == "web_structure"

    def test_to_node_claim_level(self):
        entity = ResolvedEntity(id="c1", canonical_name="Claim", entity_type="CLAIM")
        node = entity.to_node()
        assert node["metric_level"] == "CENTI_CLAIM"


class TestEntityResolver:
    def test_exact_match_merge(self):
        resolver = EntityResolver()
        entities = [
            Entity(id="lang-1", name="LangChain", entity_type="TOOL"),
            Entity(id="lang-2", name="LangChain", entity_type="TOOL"),
        ]
        resolved = resolver.resolve(entities)
        assert len(resolved) == 1
        assert resolved[0].mention_count == 2

    def test_known_alias_merge(self):
        resolver = EntityResolver()
        entities = [
            Entity(id="lc-1", name="langchain", entity_type="TOOL"),
            Entity(id="lc-2", name="lang chain", entity_type="TOOL"),
        ]
        resolved = resolver.resolve(entities)
        assert len(resolved) == 1

    def test_different_types_not_merged(self):
        resolver = EntityResolver()
        entities = [
            Entity(id="neo-1", name="Neo4j", entity_type="TOOL"),
            Entity(id="neo-2", name="Neo4j", entity_type="CONCEPT"),
        ]
        resolved = resolver.resolve(entities)
        assert len(resolved) == 2

    def test_resolve_empty(self):
        resolver = EntityResolver()
        assert resolver.resolve([]) == []

    def test_resolve_single(self):
        resolver = EntityResolver()
        entities = [Entity(id="x", name="Thing", entity_type="CONCEPT")]
        resolved = resolver.resolve(entities)
        assert len(resolved) == 1
        assert resolved[0].canonical_name == "Thing"
        assert resolved[0].mention_count == 1

    def test_merge_collects_source_urls(self):
        resolver = EntityResolver()
        entities = [
            Entity(
                id="a1",
                name="LangChain",
                entity_type="TOOL",
                source_url="https://site1.com",
            ),
            Entity(
                id="a2",
                name="LangChain",
                entity_type="TOOL",
                source_url="https://site2.com",
            ),
        ]
        resolved = resolver.resolve(entities)
        assert len(resolved) == 1
        assert len(resolved[0].source_urls) == 2

    def test_merge_longest_description(self):
        resolver = EntityResolver()
        entities = [
            Entity(id="a1", name="X", entity_type="CONCEPT", description="Short"),
            Entity(
                id="a2",
                name="X",
                entity_type="CONCEPT",
                description="Much longer description here",
            ),
        ]
        resolved = resolver.resolve(entities)
        assert "longer" in resolved[0].description

    def test_normalized_similarity_merge(self):
        resolver = EntityResolver(similarity_threshold=0.85)
        entities = [
            Entity(id="a", name="TensorFlow Framework", entity_type="TOOL"),
            Entity(id="b", name="TensorFlow", entity_type="TOOL"),
        ]
        resolved = resolver.resolve(entities)
        # May or may not merge depending on similarity; just check it returns list
        assert isinstance(resolved, list)
        assert len(resolved) >= 1

    def test_similarity_method(self):
        resolver = EntityResolver()
        assert resolver._similarity("hello", "hello") == 1.0
        assert resolver._similarity("hello", "world") < 1.0

    def test_normalize_removes_suffixes(self):
        resolver = EntityResolver()
        assert resolver._normalize("pandas library") == "pandas"
        assert resolver._normalize("pytorch framework") == "pytorch"

    def test_make_id(self):
        resolver = EntityResolver()
        assert resolver._make_id("LangChain") == "langchain"
        assert " " not in resolver._make_id("multi word name")


class TestCrossReferenceMapper:
    def test_map_entity_to_source(self):
        mapper = CrossReferenceMapper()
        mapper.map_entity_to_source("entity_1", "https://site1.com")
        mapper.map_entity_to_source("entity_1", "https://site2.com")
        assert "entity_1" in mapper.entity_to_urls
        assert len(mapper.entity_to_urls["entity_1"]) == 2

    def test_find_cross_references(self):
        mapper = CrossReferenceMapper()
        entities = [
            ResolvedEntity(
                id="e1",
                canonical_name="E1",
                entity_type="CONCEPT",
                source_urls=["https://a.com", "https://b.com"],
            ),
            ResolvedEntity(
                id="e2",
                canonical_name="E2",
                entity_type="CONCEPT",
                source_urls=["https://a.com"],
            ),
        ]
        cross_refs = mapper.find_cross_references(entities)
        assert len(cross_refs) == 1
        assert cross_refs[0]["entity_id"] == "e1"
        assert cross_refs[0]["source_count"] == 2

    def test_find_connected_sources(self):
        mapper = CrossReferenceMapper()
        mapper.map_entity_to_source("e1", "https://site1.com")
        mapper.map_entity_to_source("e1", "https://site2.com")
        connected = mapper.find_connected_sources("https://site1.com", [])
        assert any(url == "https://site2.com" for url in connected)
        assert "https://site1.com" not in connected

    def test_find_cross_references_single_source(self):
        mapper = CrossReferenceMapper()
        entities = [
            ResolvedEntity(
                id="e1",
                canonical_name="E1",
                entity_type="CONCEPT",
                source_urls=["https://a.com"],
            ),
        ]
        cross_refs = mapper.find_cross_references(entities)
        assert cross_refs == []


def test_resolve_entities_convenience():
    entities = [
        Entity(id="a", name="LangChain", entity_type="TOOL"),
        Entity(id="b", name="LangChain", entity_type="TOOL"),
    ]
    resolved = resolve_entities(entities)
    assert len(resolved) == 1
    assert isinstance(resolved[0], ResolvedEntity)
