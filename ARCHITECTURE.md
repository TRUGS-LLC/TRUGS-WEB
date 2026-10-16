# Architecture

## Overview

**trugs-web v1** is a ONE-WAY, passive web-to-TRUG builder. It crawls web sources, extracts entities and relations via LLM (model-agnostic: Anthropic, OpenAI, or mock), resolves duplicates, scores credibility, and emits a passive TRUGS knowledge graph for querying. It **never closes the self-developing loop**.

- **Type:** T2 reference application (sibling of `trugs-folder`)
- **Dependencies:** T1 commons (`trugs-tools>=2.0.0`, `trugs-store>=2.0.0`)
- **License:** Apache-2.0 with attribution-only NOTICE; see README [Scope](README.md#scope).
- **v1 scope:** Ingestion (crawler → extractor → resolver → credibility → graph_builder), query, weight. Hub federation and refresh deferred to Phase 2.

---

## Pipeline Architecture

```
CRAWL (async HTTP, robots.txt-aware)
   ↓
   Source ← [~20–50 discovered URLs, HTML parsed]
   ↓
EXTRACT (LLM-backed: Claude Haiku / GPT-3.5 / Mock)
   ↓
   Entity[], Relation[] ← [entities, relations, citations per source]
   ↓
RESOLVE (string similarity + known aliases)
   ↓
   ResolvedEntity[] ← [merged, deduplicated entities]
   ↓
CREDIBILITY (domain quality, peer-review, author, recency)
   ↓
   CredibilityFactors, edge weights ← [0.0–0.95 capped scores]
   ↓
GRAPH_BUILDER (validate via trugs_tools.validator.validate_trug)
   ↓
   TRUGS graph {name, version, nodes[], edges[], dimensions}
   ↓
QUERY (loader, traverse, synthesize)
   ↓
   TraversalResult | Report (markdown)
```

**Stage data:** `Source`, `Entity`, and `ResolvedEntity` are mutable dataclasses. Stages can share collection references, including aliases and metadata; later mutations can affect builder data. Saving validates by default; `save(validate=False)` bypasses validation, as does `build_graph(..., output_path=..., validate=False)`.

---

## Subsystem Breakdown

### 1. **Crawler** (`src/trugs_web/crawler.py`)

**Purpose:** Async HTTP source discovery from seed URLs; no LLM required.

| Class / Function | Role |
|---|---|
| `Source` | Dataclass: `{url, title, description, source_type, content, outbound_links, metadata}`. Properties: `.domain`, `.is_academic`, `.is_github`. |
| `SourceDiscoverer` | Async crawler. Tier-B safety (see below): respects `robots.txt` (fail-open), delays during batch preparation, exponential backoff on 429/5xx. Constructor defaults: `request_delay=0.0`, `respect_robots=True`, `max_retries=2`. Batch requests run in parallel without spacing. |
| `discover_sources()` | Convenience entry point: `async discover_sources(seed_urls, topic='', max_sources=50) → Source[]`. Configure `max_depth` on `SourceDiscoverer` instead. |

**Key APIs:**
- `SourceDiscoverer._fetch_source(client, url, depth)` — Internal HTTP GET with retry backoff; returns a `Source` or `None`.
- `SourceDiscoverer._extract_links(soup, base_url)` — Internal HTML link parser; returns normalized HTTP(S) URLs.
- `await SourceDiscoverer.discover(seed_urls, topic="")` — BFS from seeds; checks robots.txt before fetching and returns a list of `Source` objects.

**Safety rails (Tier-B):**
- `robots.txt` politeness: GET `/robots.txt`, respect `Disallow` for the configured user agent. Fail-open: network exceptions log at DEBUG; non-200 responses silently allow crawling.
- Batch preparation delay: configurable `request_delay` sleeps for each allowed URL before the batch fetches begin. Parallel requests in the batch are not spaced, and there is no per-domain limiter.
- Exponential backoff: on 429/500/502/503/504, wait `base * 2^attempt` (capped 30s).
- Logging: structured via `_safety.get_logger()`.

---

### 2. **Extractor** (`src/trugs_web/extractor.py`)

**Purpose:** LLM-powered entity and relation extraction from source text.

| Class / Function | Role |
|---|---|
| `Entity` | Dataclass: `{id, name, entity_type, description, aliases[], source_url, metadata}`. Types: `CONCEPT`, `AUTHOR`, `CLAIM`, `TOOL`, `PROJECT`, `PAPER`, `URL`. Method: `.to_node()` → TRUGS node. |
| `Relation` | Dataclass: `{from_id, to_id, relation_type, evidence, confidence, source_url}`. Method: `.to_edge()` → TRUGS edge. |
| `LLMClient` (Protocol) | Interface: `async complete(prompt: str, max_tokens: int) → str`. Implemented by: `MockLLMClient`, `AnthropicClient`, `OpenAIClient`. |
| `EntityExtractor` | Async: `await extractor.extract(source: Source) → Entity[]`. Sends LLM prompt, parses JSON response. |
| `RelationExtractor` | Async: `await extractor.extract(source: Source, entities: list) → Relation[]`. Requires the known entities for that source. |
| `CitationExtractor` | Async: `await extractor.extract(source: Source) → list`. Returns citation dictionaries found in one source. |
| `create_extractor(provider, api_key=None, model=None)` | Factory: reads `$ANTHROPIC_API_KEY` / `$OPENAI_API_KEY` (via `_safety.resolve_api_key()`). Returns `(EntityExtractor, RelationExtractor)`. |

**LLM Clients:**
- **MockLLMClient:** Returns synthetic JSON for testing. No API key needed.
- **AnthropicClient:** Wraps `anthropic.AsyncAnthropic(api_key)`. Default model: `claude-3-haiku-20240307`.
- **OpenAIClient:** Wraps `openai.AsyncOpenAI(api_key)`. Default model: `gpt-3.5-turbo`.

**Safety rails:**
- API keys need not be hard-coded: `resolve_api_key()` uses an explicit argument when supplied, otherwise checks `$ANTHROPIC_API_KEY` / `$OPENAI_API_KEY`.
- `CostGuard` is a standalone utility (see below); extraction and crawl/build do not invoke it or enforce its budget.
- Structured error logging on extraction failure.

---

### 3. **Resolver** (`src/trugs_web/resolver.py`)

**Purpose:** Deduplication and alias resolution across entities extracted from multiple sources.

| Class / Function | Role |
|---|---|
| `ResolvedEntity` | Dataclass: `{id, canonical_name, entity_type, description, aliases[], source_urls[], mention_count, metadata}`. Merged view of an entity. Method: `.to_node()` → TRUGS node. |
| `EntityResolver` | `resolve(entities: Entity[]) → ResolvedEntity[]`. Uses string similarity (≥0.85 by default) + known alias dict (e.g., `"langchain"` ↔ `"lang chain"`). Groups duplicates, picks canonical. |
| `CrossReferenceMapper` | Maps source URLs to entity IDs and entity IDs to source URLs; finds cross-reference records and sources connected through shared entities. Provides no canonical-ID mapping or relation rewrite API. |

**Known aliases (built-in):**
```python
{
  "langchain": {"lang chain", "lang-chain"},
  "langgraph": {"lang graph", "lang-graph"},
  "neo4j": {"neo 4j"},
  "gpt-4": {"gpt4", "gpt 4"},
  ...
}
```

---

### 4. **Credibility** (`src/trugs_web/credibility.py`)

**Purpose:** Source quality scoring and edge weight assignment.

| Class / Function | Role |
|---|---|
| `CredibilityFactors` | Dataclass: `{peer_reviewed, author_credentials, citation_score, venue_quality, recency}`. Each factor ≤ their max; `.total` property sums and **caps at 0.95** (perfect score never auto-assigned). |
| `CredibilityScorer` | `score_source(source: Source) → CredibilityFactors`. Uses source type, domain, `metadata["author"]["h_index"]` or `metadata["stars"]`, citations and publication date. These are initial credibility signals; topology ranking is a separate query-time API. |
| `calculate_credibility(source) → float` | Shorthand: score and return `.total`. |
| `score_edge_weight(relation, source=None) → float` | Uses source credibility when a `Source` is supplied, otherwise relation confidence; applies a relation-type multiplier and caps at the scorer's ceiling. |

**Domain ranking (sample):**
- High: nature.com, science.org, arxiv.org, ieee.org, acm.org (0.15–0.20)
- openai.com: 0.12
- anthropic.com: 0.12
- pytorch.org: 0.15
- reactjs.org: 0.15
- Low: techcrunch.com, arstechnica.com, wired.com (0.08)

---

### 5. **Graph Builder** (`src/trugs_web/graph_builder.py`)

**Purpose:** Orchestrate pipeline and emit TRUGS graphs.

| Class / Function | Role |
|---|---|
| `TRUGSWebGraphBuilder` | Stateful builder. Constructor: `__init__(name: str, topic: str, description: str = "")`. Creates root `RESEARCH_GRAPH` node. Methods: `.add_source_node(source, credibility)`, `.add_entity_node(entity: ResolvedEntity)`, `.add_relation_edge(relation: Relation, weight)`, `.validate()`, `.save(filepath, validate=True)`. Mutable graph data is available as `.graph`. |
| `_WebPipeline` (internal) | Orchestrates crawl → extract → resolve → score → graph. Runs async: `await pipeline.run(topic, seed_urls) → TRUGSWebGraphBuilder`. |
| `build_graph(topic, seed_urls, llm_provider="mock", api_key=None, model=None, output_path=None, validate=True)` | High-level async entry returning `TRUGSWebGraphBuilder`. Validates only when saving to `output_path` with `validate=True`; no validation is run without an output path or with the bypass selected. |
| `load_graph(filepath: str) → dict` | Deserialize `.trug.json`. |
| `url_to_id(url) → str` | Normalizes and truncates the URL's host/path to a lowercase, hyphenated ID; does not hash. |
| `make_id(text) → str` | Truncates a lowercase text slug: removes punctuation and replaces whitespace with hyphens. |

**Graph structure (TRUGS envelope):**
```json
{
  "name": "research_graph_acupuncture",
  "version": "1.0.0",
  "type": "RESEARCH",
  "dimensions": {
    "web_structure": {
      "description": "acupuncture",
      "base_level": "BASE"
    }
  },
  "capabilities": {...},
  "nodes": [
    {
      "id": "langchain",
      "type": "PROJECT",
      "properties": {"name": "LangChain", "url": "...", "credibility": 0.9},
      "metric_level": "BASE_PROJECT",
      "parent_id": null,
      "contains": [],
      "dimension": "web_structure"
    },
    ...
  ],
  "edges": [
    {"from_id": "langchain", "to_id": "neo4j", "relation": "INTEGRATES", "weight": 0.7},
    ...
  ]
}
```

**Validation:** `TRUGSWebGraphBuilder.validate()` invokes `trugs_tools.validator.validate_trug(graph)` and returns a `ValidationResult`. `.save(validate=True)` validates before writing and raises `ValueError` on failure; `.save(validate=False)` writes without validation.

---

### 6. **Query Subsystem** (`src/trugs_web/query/`)

#### Loader (`loader.py`)
| Class | Role |
|---|---|
| `Node` | Dataclass: `{id, type, properties, metric_level}`. Properties include: `name`, `description`, `credibility`, `url`. Method: `.matches(**criteria)` for filtering. |
| `Edge` | Dataclass: `{from_id, to_id, relation, weight}`. |
| `Graph` | Wrapper: `{meta, nodes_dict, edges_list}`. Methods: `.search_nodes(query)`, `.get_neighbors(node_id, direction="both", min_weight=0.0)`. |
| `GraphLoader` | `load(filepath_or_dict) → Graph`. Deserializes `.trug.json`, builds node/edge indexes. |

#### Traverse (`traverse.py`)
| Class | Role |
|---|---|
| `TraversalResult` | Result: `{query, nodes[], edges[], paths[], total_weight, avg_weight, high_credibility_count}`. Methods: `.top_nodes(n)`, `.top_edges(n)`. |
| `GraphTraverser` | Patterns: `.concept_sources()`, `.related_concepts()`, `.citation_chain()`, `.find_by_relation()`, `.high_credibility_sources()`, `.weighted_consensus()`, `.alternatives()`. Each returns `TraversalResult`. |
| `query_graph(graph, q, ...)` | Shorthand: parse query, run traversal, return result. |

#### Synthesize (`synthesize.py`)
| Class | Role |
|---|---|
| `Finding` | Result element: `{statement, source_name, source_url, weight, evidence}`. |
| `Report` | Fields: `{title, query, graph_id, generated, summary, findings[], contradictions[], recommendations[], source_count, high_credibility_count, avg_weight}`. `.to_markdown()` renders the report. |
| `ReportSynthesizer` | `await synthesize(graph, result: TraversalResult, title=None) → Report`. Converts graph traversal to a report with citations. |
| `generate_report(graph, query, ...)` | Async shorthand: query, synthesize, return `Report`; call `.to_markdown()` for markdown text. |

---

### 7. **Weight Subsystem** (`src/trugs_web/weight/`)

#### Topology (`topology.py`)
| Class / Function | Role |
|---|---|
| `NodeTopology` | Dataclass: `{node_id, inbound_count, weighted_inbound, sources}`. Computed per node across loaded TRUGs at query time (never stored). |
| `compute_topology(graphs[]) → dict` | `{node_id: NodeTopology}`. Counts inbound edges + sums weights across all graphs. |
| `rank_by_importance(topology_dict, min_inbound=1) → NodeTopology[]` | Returns all eligible nodes sorted by descending `weighted_inbound`. |
| `find_convergence(topology_dict, min_sources=2) → NodeTopology[]` | Filters by distinct contributing graph names/IDs; sorts by source count, then weighted inbound, descending. |
| `compute_freshness(edge, now=None, half_life_days=30.0) → float` | Exponential decay of an edge timestamp; returns a freshness score, with missing/unparseable timestamps receiving the minimum. |

**Design principle:** All computations are **read-time** and never mutate input graphs. No new state stored.

---

## Safety Rails (Tier-B)

Tier-B safety uses utilities in `src/trugs_web/_safety.py` and crawler configuration in `crawler.py`. Robots checks are enabled by default; batch preparation delay and retry backoff are constructor-configurable. Key resolution accepts explicit arguments or environment fallback. `CostGuard` is standalone and is not wired into crawl/build or extraction.

### Secrets (`_safety.py`)
- **resolve_api_key(provider, explicit=None):** Reads `$ANTHROPIC_API_KEY` / `$OPENAI_API_KEY`. Never logs or echoes keys. Explicit argument wins precedence.
- **No hard-coded keys required:** `create_extractor()` calls `resolve_api_key()`; an explicit API-key argument takes precedence over the environment.

### Cost Guard (`_safety.py`)
- **CostGuard(max_calls=None, max_tokens=None):** Budget ceiling. Call `.check(prompt, max_tokens)` **before** each LLM request. Raises `CostBudgetExceeded` if budget exceeded.
- **Heuristic:** ~4 chars/token.
- **Default:** Both `None` (no-op; existing pipelines unaffected).

### Rate Limit & Backoff (`_safety.py` + `crawler.py`)
- **Constant:** `RETRYABLE_STATUS = {429, 500, 502, 503, 504}`.
- **backoff_delay(attempt, base=0.5, cap=30.0):** Exponential: `min(cap, base * 2^attempt)`.
- **SourceDiscoverer:** Constructor params `request_delay=0.0`, `max_retries=2`. Delay calls occur while preparing allowed URLs, before parallel fetches start. Requests in a batch are not spaced; no per-domain limiter is implemented. Retry backoff applies to each fetch separately.

### Robots.txt Politeness (`crawler.py`)
- **SourceDiscoverer(respect_robots=True):** Checks `/robots.txt` before crawling. Respects `Disallow:` rules for `User-agent: TRUGSWebCrawler`.
- **Fail-open:** Network exceptions log at DEBUG and allow crawling; non-200 responses silently allow crawling.
- **No enforcement:** Malicious use is possible; tool assumes good faith.

### Structured Logging (`_safety.py`)
- **get_logger(name="trugs_web"):** Returns configured `logging.Logger`. Library does not set handlers (app's job); emits records for debugging.
- **Used by:** Crawler (robots.txt network exceptions at DEBUG, disallowed URLs, retry backoff), extractor (LLM errors), and CLI (command failures). Resolver does not use a logger.

---

## Deferred to Phase 2

**NOT in v1; excluded from wheel by setuptools config:**

```python
[tool.setuptools.packages.find]
where = ["src"]
include = ["trugs_web*"]  # deferred_phase2/ NOT included
```

### Hub Federation (`deferred_phase2/hub/`)
- 3-tier discovery: HTTP (known registries) → graph matching (similar TRUGs) → LLM evaluation (relevance).
- Enables cross-instance graph discovery and federation.
- Depends on `refresh/` subsystem (not available in Phase 1).

### Refresh (`deferred_phase2/refresh/`)
- Persistent queries + change tracking.
- Allows a TRUG to subscribe to "re-crawl this topic" and surface new findings.
- Closes the monitoring loop: *"Build once, poll for updates."*

**Why deferred:**
- v1 is one-way: build a passive graph, query it, done. Refresh requires state, scheduling.
- Hub federation requires cross-instance coordination (DNS, registry, federation protocol).
- Both out of scope for v1 launch.

---

## Emitted TRUG Envelope

With the default `validate=True`, `TRUGSWebGraphBuilder.save()` checks the graph with `trugs_tools.validator.validate_trug()` before writing. `validate=False` bypasses that check and can emit invalid graphs. The normal envelope is:

```python
{
  "name": str,                    # e.g., "research_graph_acupuncture"
  "version": "1.0.0",
  "type": "RESEARCH",
  "dimensions": {
    "web_structure": {
      "description": str,         # topic
      "base_level": "BASE"
    }
  },
  "capabilities": {
    "extensions": [],
    "vocabularies": ["research_v1"],
    "profiles": []
  },
  "nodes": [
    {
      "id": str,
      "type": str,                # PROJECT, CONCEPT, PAPER, AUTHOR, CLAIM, etc.
      "properties": {
        "name": str,
        "description": str,
        "aliases": [str],
        "source_url(s)": str | [str],
        "credibility": float       # 0.0–0.95
      },
      "metric_level": str,        # BASE_PROJECT, CENTI_CLAIM, etc.
      "parent_id": str | null,
      "contains": [str],          # child node IDs
      "dimension": "web_structure"
    }
  ],
  "edges": [
    {
      "from_id": str,
      "to_id": str,
      "relation": str,            # CITES, DEFINES, USES, EXTENDS, CONTRADICTS, SUPPORTS, INTEGRATES, etc.
      "weight": float             # source credibility when supplied, otherwise confidence; relation-type multiplier, capped at scorer ceiling
    }
  ]
}
```

---

## CLI

**Binary:** `trugs-web` (installed via entry point `trugs_web.cli:main`).

**Verbs:**
```bash
trugs-web crawl <url> [<url>...] --topic <str> --max-sources <int>
  → Print discovered sources (no LLM).

trugs-web build <url> [<url>...] --topic <str> [--provider {mock,anthropic,openai}] [--model <str>] [--out <path>]
  → Crawl + extract + resolve + score → passive TRUG graph.
  → API keys from $ANTHROPIC_API_KEY / $OPENAI_API_KEY.

trugs-web query <graph.trug.json> --q '<query>' [--min-weight <float>]
  → Traverse graph, print findings.

trugs-web synthesize <graph.trug.json> --q '<query>' [--out <path>]
  → Traverse graph, render markdown report.
```

---

## Test Architecture

**Test suite:** ~270 tests, pytest-based. Markers:

| Marker | Purpose | Coverage |
|---|---|---|
| `@pytest.mark.robots` | robots.txt politeness (SP4) | Mocked HTTP via respx |
| `@pytest.mark.rate_limit` | Backoff + delay behavior (SP4) | Async timing checks |
| `@pytest.mark.cost` | LLM budget guard (SP4) | CostGuard boundary tests |
| `@pytest.mark.secret` | API key from environment (SP4) | Monkeypatch $ENV tests |
| `@pytest.mark.logging` | Structured logging (SP4) | Handler inspection |
| `@pytest.mark.graph_validation_e2e` | End-to-end TRUG validation (SP2) | Build → validate_trug() → VALID |
| `@pytest.mark.asyncio` | Async extraction / crawl | pytest-asyncio |

**Test infrastructure:**
- **respx:** HTTP mocking (replaces httpx calls). No real HTTP.
- **MockLLMClient:** No API keys needed. Returns synthetic JSON.
- **Fixtures:** `sample_graph_dict`, `sample_graph` (conftest.py). Minimal TRUGS graph for query tests.
- **Monkeypatch:** Env var isolation, spy on trugs_tools.validator.

**Example test:**
```python
import pytest
from trugs_web.crawler import Source
from trugs_web.graph_builder import TRUGSWebGraphBuilder

@pytest.mark.graph_validation_e2e
def test_builder_validate_invokes_validator_and_passes(monkeypatch):
    import trugs_tools.validator as v
    calls = []
    real = v.validate_trug
    def spy(graph, *args, **kwargs):
        calls.append(graph)
        return real(graph, *args, **kwargs)
    monkeypatch.setattr(v, "validate_trug", spy)
    builder = TRUGSWebGraphBuilder(name="e2e", topic="testing")
    builder.add_source_node(Source(url="https://example.com/a", source_type="WEB_SOURCE"), credibility=0.7)
    result = builder.validate()
    assert calls, "validator not invoked"
    assert result.valid, f"validation failed: {result.to_dict()}"
```

---

## Dependencies & Installation

**Core dependencies (T1 commons):**
```toml
trugs-tools>=2.0.0      # Validator, TRL compiler
trugs-store>=2.0.0      # Graph store interface
```

**Optional dependencies:**
```bash
pip install "trugs-web[web]"      # httpx, beautifulsoup4, lxml (crawling)
pip install "trugs-web[llm]"      # anthropic, openai (LLM extraction)
pip install "trugs-web[web,llm]"  # Both
pip install "trugs-web[test]"     # pytest, respx, pytest-asyncio (testing)
```

---

## License & Scope

**License:** Apache-2.0 (`LICENSE` file).

**NOTICE:** Attribution only. See README [Scope](README.md#scope) for what this software includes.

---

## Design Invariants

1. **One-way passive:** Crawl web sources → extract → resolve → score → emit graph. No write-back, no mutation loop.
2. **T2-on-T1:** Depends downward on `trugs-tools` (T1 language) + `trugs-store` (T1 store). Never upward on T3 (application).
3. **Model-agnostic LLM:** Extractor works with Anthropic, OpenAI, or mock. Pluggable via `LLMClient` protocol.
4. **Default save validation (INVARIANT-2):** `.save(validate=True)` validates before writing. `.save(validate=False)` bypasses validation; `build_graph` forwards this option only when saving to an output path.
5. **Mutable stage output:** Crawler → Source[], Extractor → Entity[], Resolver → ResolvedEntity[], etc. Dataclasses and their collections are mutable; aliases and other references can be shared with builder data.
6. **Read-time weight:** Node importance and freshness computed at query time, never stored in the graph.
7. **Safety configuration:** Robots checks default to enabled; batch preparation delay and retry backoff are configurable. Explicit API-key arguments override environment fallback. `CostGuard` requires caller invocation and is not wired into crawl/build or extraction.
