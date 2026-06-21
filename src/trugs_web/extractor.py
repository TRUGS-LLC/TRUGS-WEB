"""
Entity and Relation Extraction Module

Uses LLMs to extract entities and relations from source content.
Supports Anthropic (Claude Haiku), OpenAI (GPT-3.5), and a MockLLMClient
for testing without API keys.

Requires: pip install trugs-tools[llm]  (for real LLM clients)
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, runtime_checkable

from .crawler import Source
from ._safety import get_logger, resolve_api_key

logger = get_logger()


# ============================================================================
# Data Types
# ============================================================================


@dataclass
class Entity:
    """An extracted entity (concept, author, claim, tool, etc.)."""

    id: str
    name: str
    entity_type: str  # CONCEPT, AUTHOR, CLAIM, TOOL, PROJECT, PAPER, URL
    description: str = ""
    aliases: list = field(default_factory=list)
    source_url: str = ""
    metadata: dict = field(default_factory=dict)

    def to_node(self) -> dict:
        """Convert to TRUGS 1.0 node format."""
        metric_level = _entity_metric_level(self.entity_type)
        return {
            "id": self.id,
            "type": self.entity_type,
            "properties": {
                "name": self.name,
                "description": self.description,
                "aliases": self.aliases,
                "source_url": self.source_url,
            },
            "metric_level": metric_level,
            "parent_id": None,
            "contains": [],
            "dimension": "web_structure",
        }


@dataclass
class Relation:
    """An extracted relation between entities."""

    from_id: str
    to_id: str
    relation_type: str  # CITES, DEFINES, USES, EXTENDS, CONTRADICTS, SUPPORTS, etc.
    evidence: str = ""
    confidence: float = 0.5
    source_url: str = ""

    def to_edge(self) -> dict:
        """Convert to TRUGS 1.0 edge format."""
        return {
            "from_id": self.from_id,
            "to_id": self.to_id,
            "relation": self.relation_type,
            "weight": self.confidence,
        }


def _entity_metric_level(entity_type: str) -> str:
    """Map entity type to TRUGS 1.0 metric level."""
    centi_types = {"CLAIM", "STATEMENT", "RESULT"}
    if entity_type in centi_types:
        return f"CENTI_{entity_type}"
    return f"BASE_{entity_type}"


# ============================================================================
# LLM Protocol (supports multiple providers)
# ============================================================================


@runtime_checkable
class LLMClient(Protocol):
    """Protocol for LLM clients (Anthropic, OpenAI, Mock)."""

    async def complete(self, prompt: str, max_tokens: int = 1000) -> str:
        """Generate completion for prompt."""
        ...


class MockLLMClient:
    """Mock LLM client for testing without API keys."""

    async def complete(self, prompt: str, max_tokens: int = 1000) -> str:
        """Return mock response based on prompt patterns."""
        prompt_lower = prompt.lower()

        if "extract key entities" in prompt_lower or "extract entities" in prompt_lower:
            return json.dumps(
                {
                    "entities": [
                        {
                            "name": "Example Entity",
                            "type": "CONCEPT",
                            "description": "A test entity",
                        }
                    ]
                }
            )
        if (
            "extract relationships" in prompt_lower
            or "extract relations" in prompt_lower
        ):
            return json.dumps(
                {
                    "relations": [
                        {
                            "from": "entity_a",
                            "to": "entity_b",
                            "relation": "RELATED_TO",
                            "confidence": 0.7,
                        }
                    ]
                }
            )
        if "extract citations" in prompt_lower:
            return json.dumps(
                {
                    "citations": [
                        {
                            "title": "Test Paper",
                            "type": "PAPER",
                            "url": "https://example.com",
                        }
                    ]
                }
            )
        return "{}"


class AnthropicClient:
    """Anthropic Claude client (Haiku for cheap extraction)."""

    def __init__(self, api_key: str, model: str = "claude-3-haiku-20240307"):
        self.api_key = api_key
        self.model = model
        self._client: Any = None

    async def complete(self, prompt: str, max_tokens: int = 1000) -> str:
        """Generate completion using Claude Haiku."""
        if self._client is None:
            try:
                import anthropic
            except ImportError as exc:
                raise ImportError(
                    "anthropic is required for AnthropicClient. "
                    "Install with: pip install trugs-tools[llm]"
                ) from exc
            self._client = anthropic.AsyncAnthropic(api_key=self.api_key)

        message = await self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text


class OpenAIClient:
    """OpenAI client (GPT-3.5 for cheap extraction)."""

    def __init__(self, api_key: str, model: str = "gpt-3.5-turbo"):
        self.api_key = api_key
        self.model = model
        self._client: Any = None

    async def complete(self, prompt: str, max_tokens: int = 1000) -> str:
        """Generate completion using GPT-3.5."""
        if self._client is None:
            try:
                import openai
            except ImportError as exc:
                raise ImportError(
                    "openai is required for OpenAIClient. "
                    "Install with: pip install trugs-tools[llm]"
                ) from exc
            self._client = openai.AsyncOpenAI(api_key=self.api_key)

        response = await self._client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content


# ============================================================================
# Entity Extraction
# ============================================================================

ENTITY_EXTRACTION_PROMPT = """Extract key entities from this text. Return JSON only.

TEXT:
{content}

Extract these entity types:
- CONCEPT: Key ideas, terms, technologies
- AUTHOR: People or organizations mentioned
- CLAIM: Specific factual assertions
- TOOL: Software, libraries, frameworks
- PAPER: Academic papers referenced
- URL: Important links mentioned

Return JSON format:
{{
  "entities": [
    {{"name": "Entity Name", "type": "CONCEPT", "description": "Brief description"}}
  ]
}}

JSON response:"""


class EntityExtractor:
    """Extracts entities from source content using an LLM client."""

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    async def extract(self, source: Source) -> list:
        """
        Extract entities from a source.

        Args:
            source: Source with content to extract from

        Returns:
            List of Entity objects
        """
        content = source.content[:4000]
        if not content.strip():
            return []

        prompt = ENTITY_EXTRACTION_PROMPT.format(content=content)

        try:
            response = await self.llm.complete(prompt)
            data = self._parse_json(response)

            entities = []
            for item in data.get("entities", []):
                entity_id = self._make_id(item.get("name", "unknown"))
                entities.append(
                    Entity(
                        id=entity_id,
                        name=item.get("name", ""),
                        entity_type=item.get("type", "CONCEPT"),
                        description=item.get("description", ""),
                        source_url=source.url,
                        metadata={"extracted_from": source.url},
                    )
                )
            return entities

        except Exception as exc:
            logger.warning(
                "entity extraction failed for %s: %s", getattr(source, "url", "?"), exc
            )
            return []

    def _parse_json(self, text: str) -> dict:
        """Extract JSON from LLM response."""
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\n?", "", text)
            text = re.sub(r"\n?```$", "", text)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{[\s\S]*\}", text)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
        return {}

    def _make_id(self, name: str) -> str:
        """Convert name to valid ID."""
        id_str = name.lower()
        id_str = re.sub(r"[^a-z0-9\s-]", "", id_str)
        id_str = re.sub(r"\s+", "-", id_str)
        return id_str[:50]


# ============================================================================
# Relation Extraction
# ============================================================================

RELATION_EXTRACTION_PROMPT = """Extract relationships between entities in this text. Return JSON only.

TEXT:
{content}

KNOWN ENTITIES:
{entities}

Extract these relation types:
- CITES: Source A references/cites source B
- DEFINES: Source defines or explains a concept
- USES: Tool/project uses another tool/library
- EXTENDS: Builds upon or extends another work
- CONTRADICTS: Claims that contradict each other
- SUPPORTS: Claims that support each other
- AUTHORED_BY: Work created by author
- ALTERNATIVE_TO: Competing or alternative approaches

Return JSON format:
{{
  "relations": [
    {{"from": "entity_id_1", "to": "entity_id_2", "relation": "RELATION_TYPE", "confidence": 0.8, "evidence": "quote from text"}}
  ]
}}

JSON response:"""


class RelationExtractor:
    """Extracts relations between entities using an LLM client."""

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    async def extract(self, source: Source, entities: list) -> list:
        """
        Extract relations from a source given known entities.

        Args:
            source: Source with content
            entities: List of Entity objects to find relations between

        Returns:
            List of Relation objects
        """
        content = source.content[:4000]
        if not content.strip() or not entities:
            return []

        entity_list = "\n".join(
            [f"- {e.id}: {e.name} ({e.entity_type})" for e in entities[:20]]
        )

        prompt = RELATION_EXTRACTION_PROMPT.format(
            content=content,
            entities=entity_list,
        )

        try:
            response = await self.llm.complete(prompt)
            data = self._parse_json(response)

            relations = []
            for item in data.get("relations", []):
                relations.append(
                    Relation(
                        from_id=item.get("from", ""),
                        to_id=item.get("to", ""),
                        relation_type=item.get("relation", "RELATED_TO"),
                        evidence=item.get("evidence", ""),
                        confidence=float(item.get("confidence", 0.5)),
                        source_url=source.url,
                    )
                )
            return relations

        except Exception as exc:
            logger.warning("relation extraction failed: %s", exc)
            return []

    def _parse_json(self, text: str) -> dict:
        """Extract JSON from LLM response."""
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\n?", "", text)
            text = re.sub(r"\n?```$", "", text)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{[\s\S]*\}", text)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
        return {}


# ============================================================================
# Citation Extraction
# ============================================================================

CITATION_EXTRACTION_PROMPT = """Extract citations and references from this text. Return JSON only.

TEXT:
{content}

Extract:
1. Direct citations (papers, books, URLs referenced)
2. Implicit references (tools, projects, concepts mentioned as sources)

Return JSON format:
{{
  "citations": [
    {{"title": "Paper Title", "authors": ["Author Name"], "url": "https://...", "type": "PAPER"}},
    {{"title": "Tool Name", "url": "https://github.com/...", "type": "PROJECT"}}
  ]
}}

JSON response:"""


class CitationExtractor:
    """Specialized extractor for citations and references."""

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    async def extract(self, source: Source) -> list:
        """Extract citations from source."""
        content = source.content[:4000]
        if not content.strip():
            return []

        prompt = CITATION_EXTRACTION_PROMPT.format(content=content)

        try:
            response = await self.llm.complete(prompt)
            data = self._parse_json(response)
            return data.get("citations", [])
        except Exception:
            return []

    def _parse_json(self, text: str) -> dict:
        """Extract JSON from response."""
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\n?", "", text)
            text = re.sub(r"\n?```$", "", text)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {}


# ============================================================================
# Factory Function
# ============================================================================


def create_extractor(
    provider: str = "mock",
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> tuple:
    """
    Create entity and relation extractors.

    Args:
        provider: "mock", "anthropic", or "openai"
        api_key: API key for provider
        model: Optional model override

    Returns:
        Tuple of (EntityExtractor, RelationExtractor)
    """
    if provider in ("anthropic", "openai"):
        # Tier-B: resolve the key from the environment (ANTHROPIC_API_KEY / OPENAI_API_KEY)
        # when not passed inline — never require a hard-coded secret.
        api_key = resolve_api_key(provider, api_key)
        if not api_key:
            env = "ANTHROPIC_API_KEY" if provider == "anthropic" else "OPENAI_API_KEY"
            raise ValueError(
                f"API key required for {provider}: pass api_key=... or set ${env} in the "
                "environment (keys are read from the environment; never hard-code them)."
            )
        client: LLMClient = (
            AnthropicClient(api_key, model or "claude-3-haiku-20240307")
            if provider == "anthropic"
            else OpenAIClient(api_key, model or "gpt-3.5-turbo")
        )
    else:
        client = MockLLMClient()

    return EntityExtractor(client), RelationExtractor(client)
