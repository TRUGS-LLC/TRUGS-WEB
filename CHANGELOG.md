# trugs-web

**TRUGS web research tool.** One binary, `trugs-web` — crawl web sources and build a passive TRUGS knowledge graph. Extract entities and relations (LLM-backed, model-agnostic), resolve deduplication, score credibility, and emit a read-only graph for querying.

The tool is **one-way and passive**: it builds graphs for querying; it never closes the self-developing loop (the reserved patent mechanism, US app 19/575,491).

## Install

```bash
pip install trugs-web[web,llm]
```

**web** extras: `httpx`, `beautifulsoup4`, `lxml` (async crawling, HTML parsing)  
**llm** extras: `anthropic`, `openai` (Claude Haiku / GPT-3.5 extraction)

Extracts work with any LLM via the `LLMClient` protocol; a `MockLLMClient` is included for testing without keys.

## Quickstart

```bash
# Discover sources from seed URLs (no LLM)
trugs-web crawl https://example.com --topic "machine learning" --max-sources 20

# Build a graph: crawl + extract + resolve + score
trugs-web build https://example.com --topic "machine learning" --provider anthropic --out graph.trug.json

# Query the built graph
trugs-web query graph.trug.json --q "sources for machine learning" --min-weight 0.5

# Render a markdown report
trugs-web synthesize graph.trug.json --q "evidence for machine learning" --out report.md
```

Every verb documents examples and exit codes: `trugs-web <verb> --help`.

## Architecture

### Ingestion pipeline

```
Source Discovery
       ↓
   crawl (httpx + robots.txt)
       ↓
    extract (LLM: entity, relation, citation)
       ↓
    resolve (deduplication, alias mapping)
       ↓
  credibility (scoring by source type + domain)
       ↓
 graph_builder (emit TRUGS 1.0 JSON)
```

### Components

| Module | Purpose |
|--------|---------|
| `crawler.py` | Async HTTP crawling, robots.txt politeness (fail-open), link extraction |
| `extractor.py` | LLM-powered entity/relation/citation extraction (protocol-based: Anthropic, OpenAI, Mock) |
| `resolver.py` | Entity deduplication via string similarity + known aliases |
| `credibility.py` | Source credibility scoring (domain type, freshness) |
| `graph_builder.py` | Orchestrates the full pipeline; emits TRUGS 1.0 graphs validated via `trugs_tools.validator.validate_trug` |
| `query/` | Graph loading, traversal, report synthesis |
| `weight/topology.py` | Query-time node importance from inbound edge topology |
| `_safety.py` | Tier-B safety rails: cost guard, rate limiting, exponential backoff, structured logging |

### Safety rails (Tier-B)

For a public tool that runs LLM-backed crawls against live sites and paid APIs:

- **secrets**: API keys from environment (`$ANTHROPIC_API_KEY` / `$OPENAI_API_KEY`), never required inline, never logged
- **cost guard**: Pre-flight budget ceiling on LLM calls and token spend (no-op by default)
- **rate limit**: Inter-request delay + exponential backoff on retryable HTTP status
- **robots.txt**: Crawl politeness, cached per host, fail-open on parse errors
- **logging**: Structured logger so failures are debuggable, not swallowed

## Dependencies

`trugs-web` is **T2** (a reference application): it depends downward on the T1 commons:

- `trugs-tools>=2.0.0` — language core (TRL, validator, TRUG parsing)
- `trugs-store>=2.0.0` — graph store (persistence)

It never depends on any T3 system package (the cleave invariant; see AAA #2358).

## Output format

Graphs are TRUGS 1.0 JSON, validated by `trugs_tools.validator.validate_trug`:

```json
{
  "name": "machine learning",
  "version": "1.0.0",
  "type": "RESEARCH",
  "dimensions": { "web_structure": {...} },
  "capabilities": { "vocabularies": ["research_v1"], ... },
  "nodes": [
    {
      "id": "concept_mlops",
      "type": "CONCEPT",
      "properties": { "name": "MLOps", ... },
      "metric_level": "BASE_CONCEPT",
      "dimension": "web_structure"
    },
    ...
  ],
  "edges": [
    {
      "from_id": "concept_mlops",
      "to_id": "tool_kubeflow",
      "relation": "USES",
      "weight": 0.8
    },
    ...
  ]
}
```

Node types: `CONCEPT`, `AUTHOR`, `CLAIM`, `TOOL`, `PROJECT`, `PAPER`, `URL`, `RESEARCH_GRAPH`  
Relation types: `CITES`, `DEFINES`, `USES`, `EXTENDS`, `CONTRADICTS`, `SUPPORTS`, etc.

## Testing

270 passing tests (pytest markers: `robots`, `rate_limit`, `cost`, `secret`, `logging`, `graph_validation_e2e`).

- **respx-mocked HTTP**: crawler and extractor tests use fake HTTP responses
- **MockLLMClient**: extraction tests work without API keys
- **graph_validation_e2e**: end-to-end: crawl → extract → build → validate_trug

```bash
pytest tests/ -v
pytest tests/ -m graph_validation_e2e  # validate against trugs_tools.validator
```

## Deferred to Phase 2

Hub federation and graph refresh are scaffolded in `deferred_phase2/` but not shipped in v1:

- `hub/`: TRUG discovery agent (3-tier: HTTP index, graph matching, LLM evaluation)
- `refresh/`: Persistent queries and change tracking

These will ship in `2.1.0`.

## License

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).

The patent NOTICE covers the one-way, passive nature of this tool. Self-modifying graph systems that close the development loop are reserved under US patent application 19/575,491 (EGS-979). See https://github.com/Xepayac/XEPAYAC_LLC for AGPL 3.0 and commercial licensing.

## Lineage

Migrated from `trugs-tools` 1.0.0 (PyPI, 2026-04-18), where the web pipeline lived as `trugs_tools.web.*`. The v1 → 2.0 refactor cleanly separated it onto its own T2 wheel with its own CLI, `trugs-web`.

---

# CHANGELOG

All notable changes to `trugs-web` are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Nothing yet.

## [2.0.0] — 2026-06-17

First release as a standalone, installable T2 package (versions are in lockstep with `trugs-tools` 2.0).

### Lineage

`trugs-web` descends from the web pipeline half of **trugs-tools 1.0.0** (PyPI, 2026-04-18), where these
components lived under `trugs_tools.web.*`. The TRUGS 2.0 commons cleave (AAA #2373) split the web tier onto
its own wheel with its own binary, `trugs-web`. The 1.0 → 2.0 module migration table is in the
[trugs-tools CHANGELOG](https://github.com/TRUGS-LLC/TRUGS-TOOLS/blob/main/CHANGELOG.md).

### Added

- The `trugs-web` binary: four ingestion+query verbs (`crawl` / `build` / `query` / `synthesize`), each with
  examples and documented exit codes in `--help`.
- Installable Python package: `pip install trugs-web[web,llm]` (web = httpx, beautifulsoup4, lxml; llm = anthropic, openai).
- Ingestion pipeline (AAA #2295 SP1–SP3): source discovery, entity/relation/citation extraction (LLM-backed,
  model-agnostic via `LLMClient` protocol), entity resolution (deduplication), credibility scoring, TRUGS 1.0 graph
  emission + validation via `trugs_tools.validator.validate_trug`.
- Query subsystem: graph loading, traversal, report synthesis (markdown rendering).
- Weight topology: query-time node importance computation from inbound edge topology across loaded TRUGs.
- Tier-B safety rails (AAA #2295 SP4): robots.txt politeness (fail-open), inter-request delay + exponential backoff,
  LLM cost guard (budget ceiling on calls/tokens), structured logging, API-key-from-environment secrets (never inline,
  never logged).
- Package-owned test suite (`tests/`): 270 passing tests with pytest markers (`robots`, `rate_limit`, `cost`,
  `secret`, `logging`, `graph_validation_e2e`); respx-mocked HTTP, MockLLMClient for zero-API-key testing.
- TRUGS 1.0 graph validation e2e test (AAA #2295 SP2): end-to-end crawl → extract → resolve → credibility → build →
  validate_trug.

### Changed

- Module namespace: `trugs_tools.web.*` → `trugs_web.*` (new package).
- Dependencies: now depends downward on `trugs-tools>=2.0.0` + `trugs-store>=2.0.0` (T1 commons), never on T3
  system packages.
- CLI architecture: consolidated into a single `trugs-web` binary with verb subparsers, not separate tools.
- Graph emission: all output follows TRUGS 1.0 JSON schema with per-node validation.

### License

Changed from Proprietary to Apache-2.0 + patent NOTICE. The patent NOTICE covers the one-way, passive nature of
the tool (it never closes the self-developing loop, US app 19/575,491). Downstream users who wire this tool's
passive output into self-modifying agents operate outside the Apache grant. See
[NOTICE](NOTICE) and https://github.com/Xepayac/XEPAYAC_LLC for AGPL 3.0 and commercial licensing of the
reserved mechanism.

### Deferred to Phase 2

Hub federation and graph refresh are scaffolded in `deferred_phase2/` but not shipped in v1. These will ship in
`2.1.0`:

- **hub federation**: TRUG discovery agent (3-tier: HTTP index search, graph structure matching, LLM evaluation).
- **refresh**: Persistent queries and change tracking across graph snapshots.

### Note

The `trugs-tools` / `trugs-store` 2.0.0 final commons are now on PyPI, and the clean-venv
install gate (SC-1) is verified green against them (270 tests pass from the built wheel;
`trugs_tools.validator.validate_trug` resolves from the published 2.0.0). `trugs-web` itself is
**not yet published** — the PyPI publish + public repo graduation (AAA #2295 SP6) is a separate,
explicit step pending HITM go.
