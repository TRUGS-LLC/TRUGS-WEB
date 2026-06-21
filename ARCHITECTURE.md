# Architecture

## Overview

**trugs-web v1** is a ONE-WAY, passive web-to-TRUG builder. It crawls web sources, extracts entities and relations via LLM (model-agnostic: Anthropic, OpenAI, or mock), resolves duplicates, scores credibility, and emits a passive TRUGS 1.0 knowledge graph for querying. It **never closes the self-developing loop** — the reserved patent mechanism (U.S. app 19/575,491).

- **Type:** T2 reference application (sibling of `trugs-folder`)
- **Dependencies:** T1 commons (`trugs-tools>=2.0.0`, `trugs-store>=2.0.0`)
- **License:** Apache-2.0 + PATENT NOTICE
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
   TRUGS 1.0 graph {name, version, nodes[], edges[], dimensions}
   ↓
QUERY (loader, traverse, synthesize)
   ↓
   TraversalResult | Report (markdown)
```

**Flow guarantee:** Each stage outputs immutable, serializable data. No mutation, no state sharing between stages. Graph always passes `validate_trug()` before save.

---

## Subsystem Breakdown

### 1. **Crawler** (`src/trugs_web/crawler.py`)

**Purpose:** Async HTTP source discovery from seed URLs; no LLM required.

| Class / Function | Role |
|---|---|
| `Source` | Dataclass: `{url, title, description, source_type, content, outbound_links, metadata}`. Properties: `.domain`, `.is_academic`, `.is_github`. |
| `SourceDiscoverer` | Async crawler. Tier-B safety (see below): respects `robots.txt` (fail-open), inter-request delay, exponential backoff on 429/5xx. Constructor opt-in: `request_delay=0.0`, `respect_robots=True`, `max_retries=2`. |
| `discover_sources()` | Convenience entry point: `async discover_sources(seed_urls, topic="", max_sources=50, max_depth=2) → Source[]`. |

**Key APIs:**
- `SourceDiscoverer.fetch_url()` — HTTP GET with backoff + robots.txt check.
- `SourceDiscoverer.extract_links()` — Parse HTML, yield relative/absolute links.
- `SourceDiscoverer.discover()` — BFS from seeds, yield `Source` objects.

**Safety rails (Tier-B):**
- `robots.txt` politeness: HEAD to `/robots.txt`, parse `User-agent: TRUGSWebCrawler`, respect `Disallow`. Fail-open: if fetch fails, crawl anyway (log warning).
- Inter-request delay: configurable `request_delay` (e.g., 1.0 sec) per domain.
- Exponential backoff: on 429/500/502/503/504, wait `base * 2^attempt` (capped 30s).
- Logging: structured via `_safety.get_logger()`.

---

### 2. **Extractor** (`src/trugs_web/extractor.py`)

**Purpose:** LLM-powered entity and relation extraction from source text.

| Class / Function | Role |
|---|---|
| `Entity` | Dataclass: `{id, name, entity_type, description, aliases[], source_url, metadata}`. Types: `CONCEPT`, `AUTHOR`, `CLAIM`, `TOOL`, `PROJECT`, `PAPER`, `URL`. Method: `.to_node()` → TRUGS 1.0 node. |
| `Relation` | Dataclass: `{from_id, to_id, relation_type, evidence, confidence, source_url}`. Method: `.to_edge()` → TRUGS 1.0 edge. |
| `LLMClient` (Protocol) | Interface: `async complete(prompt: str, max_tokens: int) → str`. Implemented by: `MockLLMClient`, `AnthropicClient`, `OpenAIClient`. |
| `EntityExtractor` | Async: `await extractor.extract(source: Source) → Entity[]`. Sends LLM prompt, parses JSON response. |
| `RelationExtractor` | Async: `await extractor.extract(source: Source) → Relation[]`. |
| `CitationExtractor` | Async: finds papers/references in text. |
| `create_extractor(provider, api_key=None, model=None)` | Factory: reads `$ANTHROPIC_API_KEY` / `$OPENAI_API_KEY` (via `_safety.resolve_api_key()`). Returns `(EntityExtractor, RelationExtractor)`. |

**LLM Clients:**
- **MockLLMClient:** Returns synthetic JSON for testing. No API key needed.
- **AnthropicClient:** Wraps `anthropic.AsyncAnthropic(api_key)`. Default model: `claude-3-haiku-20240307`.
- **OpenAIClient:** Wraps `openai.AsyncOpenAI(api_key)`. Default model: `gpt-3.5-turbo`.

**Safety rails:**
- API key from environment **only** (never inline): `resolve_api_key()` checks `$ANTHROPIC_API_KEY` / `$OPENAI_API_KEY`.
- LLM cost guard (see below).
- Structured error logging on extraction failure.

---

### 3. **Resolver** (`src/trugs_web/resolver.py`)

**Purpose:** Deduplication and alias resolution across entities extracted from multiple sources.

| Class / Function | Role |
|---|---|
| `ResolvedEntity` | Dataclass: `{id, canonical_name, entity_type, description, aliases[], source_urls[], mention_count, metadata}`. Merged view of an entity. Method: `.to_node()` → TRUGS 1.0 node. |
| `EntityResolver` | `resolve(entities: Entity[]) → ResolvedEntity[]`. Uses string similarity (≥0.85 by default) + known alias dict (e.g., `"langchain"` ↔ `"lang chain"`). Groups duplicates, picks canonical. |
| `CrossReferenceMapper` | Builds bidirectional mapping: `entity_id ↔ canonical_id`. Enables relation rewriting post-merge. |

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
| `CredibilityScorer` | `score(source: Source) → CredibilityFactors`. Checks domain (arxiv, nature, ieee, openai.com, etc. → +0.15–0.20). Authors (e.g., `creator` meta tag → +0.2). Publication date (recent → +0.1). Aggregates signals, respects 0.95 cap. |
| `calculate_credibility(source) → float` | Shorthand: score and return `.total`. |
| `score_edge_weight(relation, source_credibility) → float` | Combines relation confidence + source credibility; returns 0.0–1.0. |

**Domain ranking (sample):**
- High: nature.com, science.org, arxiv.org, ieee.org, acm.org (0.15–0.20)
- Medium: openai.com, anthropic.com, pytorch.org, reactjs.org (0.10–0.12)
- Low: techcrunch.com, arstechnica.com, wired.com (0.08)

---

### 5. **Graph Builder** (`src/trugs_web/graph_builder.py`)

**Purpose:** Orchestrate pipeline and emit TRUGS 1.0 graphs.

| Class / Function | Role |
|---|---|
| `TRUGSWebGraphBuilder` | Stateful builder. Constructor: `__init__(name: str, topic: str, description: str)`. Creates root `RESEARCH_GRAPH` node. Methods: `.add_source_node(source, credibility)`, `.add_entity(entity)`, `.add_relation(from_id, to_id, relation, weight)`, `.validate()`, `.save(filepath, validate=True)`. Returns graph conforming to TRUGS 1.0 schema. |
| `_WebPipeline` (internal) | Orchestrates crawl → extract → resolve → score → graph. Runs async: `await pipeline.run(topic, seed_urls) → TRUGSWebGraphBuilder`. |
| `build_graph(topic, seed_urls, provider, ...)` | High-level async entry: `await build_graph(...) → dict` (the graph). Calls `_WebPipeline`, validates, returns. |
| `load_graph(filepath: str) → dict` | Deserialize `.trug.json`. |
| `url_to_id(url) → str` | Hash URL to safe ID. |
| `make_id(text) → str` | Slugify text to safe ID (lowercase, alphanumeric + underscore). |

**Graph structure (TRUGS 1.0 envelope):**
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

**Validation:** `TRUGSWebGraphBuilder.validate()` invokes `trugs_tools.validator.validate_trug(graph)` and returns a `ValidationResult`. All saved graphs **must** pass validation (else `.save()` raises `ValueError`).

---

### 6. **Query Subsystem** (`src/trugs_web/query/`)

#### Loader (`loader.py`)
| Class | Role |
|---|---|
| `Node` | Dataclass: `{id, type, properties, metric_level}`. Properties include: `name`, `description`, `credibility`, `url`. Method: `.matches(**criteria)` for filtering. |
| `Edge` | Dataclass: `{from_id, to_id, relation, weight}`. |
| `Graph` | Wrapper: `{meta, nodes_dict, edges_list}`. Methods: `.search_nodes(query)`, `.neighbors(node_id)`. |
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
| `Finding` | Result element: `{node, edges, confidence}`. |
| `Report` | Markdown: `{title, summary, findings[], sources}`. |
| `ReportSynthesizer` | `synthesize(traversal_result) → Report`. Converts graph traversal to human-readable markdown with citations. |
| `generate_report(graph, q, ...)` | Shorthand: query, synthesize, return markdown `str`. |

---

### 7. **Weight Subsystem** (`src/trugs_web/weight/`)

#### Topology (`topology.py`)
| Class / Function | Role |
|---|---|
| `NodeTopology` | Dataclass: `{node_id, inbound_count, weighted_inbound, sources}`. Computed per node across loaded TRUGs at query time (never stored). |
| `compute_topology(graphs[]) → dict` | `{node_id: NodeTopology}`. Counts inbound edges + sums weights across all graphs. |
| `rank_by_importance(topology_dict, top_n=10)` | Sort nodes by inbound edge count (importance). Returns top N. |
| `find_convergence(graphs[]) → Node[]` | Find nodes with edges from ≥3 graphs (strong consensus). |
| `compute_freshness(graph, days=365) → dict` | Age of nodes by publication date. Returns `{node_id: age_days}`. |

**Design principle:** All computations are **read-time** and never mutate input graphs. No new state stored.

---

## Safety Rails (Tier-B)

Tier-B safety is **opt-in via constructor parameters** so default construction is unchanged. All implemented in `src/trugs_web/_safety.py` and `crawler.py`.

### Secrets (`_safety.py`)
- **resolve_api_key(provider, explicit=None):** Reads `$ANTHROPIC_API_KEY` / `$OPENAI_API_KEY`. Never logs or echoes keys. Explicit argument wins precedence.
- **No inline keys:** All extractors created via `create_extractor()`, which calls `resolve_api_key()`.

### Cost Guard (`_safety.py`)
- **CostGuard(max_calls=None, max_tokens=None):** Budget ceiling. Call `.check(prompt, max_tokens)` **before** each LLM request. Raises `CostBudgetExceeded` if budget exceeded.
- **Heuristic:** ~4 chars/token.
- **Default:** Both `None` (no-op; existing pipelines unaffected).

### Rate Limit & Backoff (`_safety.py` + `crawler.py`)
- **Constant:** `RETRYABLE_STATUS = {429, 500, 502, 503, 504}`.
- **backoff_delay(attempt, base=0.5, cap=30.0):** Exponential: `min(cap, base * 2^attempt)`.
- **SourceDiscoverer:** Constructor params `request_delay=0.0`, `max_retries=2`. Applied per domain.

### Robots.txt Politeness (`crawler.py`)
- **SourceDiscoverer(respect_robots=True):** Checks `/robots.txt` before crawling. Respects `Disallow:` rules for `User-agent: TRUGSWebCrawler`.
- **Fail-open:** If robots.txt fetch fails, crawl anyway (log warning).
- **No enforcement:** Malicious use is possible; tool assumes good faith.

### Structured Logging (`_safety.py`)
- **get_logger(name="trugs_web"):** Returns configured `logging.Logger`. Library does not set handlers (app's job); emits records for debugging.
- **Used by:** Crawler (robots.txt warnings, backoff), extractor (LLM errors), resolver, etc.

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

Every graph emitted by `TRUGSWebGraphBuilder.save()` conforms to **TRUGS 1.0 schema** and passes `trugs_tools.validator.validate_trug()`:

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
      "weight": float             # 0.0–1.0 (credibility × confidence)
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
- **Fixtures:** `sample_graph_dict`, `sample_graph` (conftest.py). Minimal TRUGS 1.0 graph for query tests.
- **Monkeypatch:** Env var isolation, spy on trugs_tools.validator.

**Example test:**
```python
@pytest.mark.graph_validation_e2e
def test_builder_validate_invokes_validator_and_passes(monkeypatch):
    import trugs_tools.validator as v
    calls = []
    real = v.validate_trug
    monkeypatch.setattr(v, "validate_trug", spy=lambda g, *a, **kw: (calls.append(g), real(g, *a, **kw)))
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

## License & Patent Notice

**License:** Apache-2.0 (`LICENSE` file).

**PATENT NOTICE** (NOTICE file):
> This license covers a ONE-WAY, PASSIVE tool. It does NOT cover self-developing graph systems (agent-in-the-loop mutation, no compile boundary).
> 
> U.S. patent application 19/575,491 (EGS-979) reserves self-modifying agent systems. Downstream users who wire this tool's passive output into a self-modifying agent operate outside this grant.
> 
> AGPL 3.0 and commercial licensing available at https://github.com/Xepayac/XEPAYAC_LLC.

---

## Design Invariants

1. **One-way passive:** Crawl web sources → extract → resolve → score → emit graph. No write-back, no mutation loop.
2. **T2-on-T1:** Depends downward on `trugs-tools` (T1 language) + `trugs-store` (T1 store). Never upward on T3 (application).
3. **Model-agnostic LLM:** Extractor works with Anthropic, OpenAI, or mock. Pluggable via `LLMClient` protocol.
4. **Validation invariant (INVARIANT-2):** Every graph emitted to disk passes `trugs_tools.validator.validate_trug()`. Enforced in `.save(validate=True)`.
5. **Immutable stage output:** Crawler → Source[], Extractor → Entity[], Resolver → ResolvedEntity[], etc. No aliasing, no in-place mutation.
6. **Read-time weight:** Node importance and freshness computed at query time, never stored in the graph.
7. **Safety opt-in:** Tier-B rails (robots.txt, cost guard, rate limit, secrets) all constructor-configurable. Default = unchanged behavior.
