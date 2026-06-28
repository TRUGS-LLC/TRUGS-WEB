# trugs-web

**Web-to-TRUG builder.** One binary, `trugs-web` — crawl web sources, extract entities and relations with LLM assistance (model-agnostic), resolve and score credibility, and build a passive TRUGS knowledge graph for querying. It builds graphs; it never closes the self-developing loop (reserved patent mechanism, US app 19/575,491).

## What & Why

`trugs-web` is a **one-way, passive** research tool. You point it at seed URLs; it discovers sources, extracts structured knowledge (entities, relations, citations) via LLM-backed natural language processing, resolves entity identity across sources, scores credibility from topology and metadata, and emits a TRUGS 1.0 format graph. That graph is a **passive data structure**—queryable, traversable, reportable—but inert. The tool does not modify it in place; no agent closes the feedback loop. This boundary is licensed: the reserved patent (US 19/575,491) protects self-modifying graph substrates. A downstream user who wires this tool's passive output into a self-modifying agent operates outside this grant.

As a **T2 reference application** (sibling of `trugs-folder`), `trugs-web` depends downward on the T1 commons: `trugs-tools>=2.0.0` (language, validator) and `trugs-store>=2.0.0` (graph persistence). v1 ships the ingestion pipeline (crawler, extractor, resolver, credibility scorer, graph builder), query subsystem (loader, traverse, synthesize), and weight computation (topology-based importance ranking). Hub federation and refresh are deferred to Phase 2 (see `deferred_phase2/`).

## Key Features

- **Source discovery**: crawl seed URLs, discover linked pages, respect `robots.txt`, apply rate limits and exponential backoff
- **Entity & relation extraction**: LLM-backed NLP (model-agnostic; use Anthropic Claude, OpenAI GPT, or mock for testing)
- **Cross-reference resolution**: deduplicate entities across sources by name, description, and context
- **Credibility scoring**: topology-aware confidence weights on nodes and edges
- **TRUGS 1.0 graph output**: validated against `trugs_tools.validator.validate_trug`; query-ready JSON
- **Query & traverse**: load a graph, traverse by relation type, filter by weight threshold, synthesize findings into markdown reports
- **Safety rails**: secrets from environment (never inline), LLM cost guard, inter-request delays, structured logging

## Quick Example

> **Network + LLM required** — `build_graph` crawls the seed URLs over the live web. For a no-network, no-LLM run on a shipped graph, see [below](#offline-quickstart).

```python
import asyncio
from trugs_web import build_graph, load_graph, query_graph, generate_report

# 1. Build a passive graph from seed URLs (mock LLM provider for testing)
async def main():
    builder = await build_graph(
        topic="acupuncture evidence",
        seed_urls=["https://example.com/research"],
        llm_provider="mock",  # or "anthropic", "openai"
        output_path="acupuncture.trug.json"
    )
    print(f"Built: {len(builder.graph['nodes'])} nodes, {len(builder.graph['edges'])} edges")

    # 2. Load and query the graph
    graph = load_graph("acupuncture.trug.json")
    results = query_graph(graph, "sources for acupuncture efficacy", min_weight=0.5)
    print(results)

    # 3. Synthesize a markdown report
    report = await generate_report(graph, "acupuncture efficacy evidence")
    print(report.to_markdown())

asyncio.run(main())
```

## Installation

**Requirements:** Python ≥ 3.11

Install from source (directly from GitHub):

```bash
# Minimal (graph building + querying, no crawling or LLM)
pip install "git+https://github.com/TRUGS-LLC/TRUGS-WEB.git"

# With web crawling (httpx, beautifulsoup4, lxml)
pip install "trugs-web[web] @ git+https://github.com/TRUGS-LLC/TRUGS-WEB.git"

# With LLM support (anthropic, openai)
pip install "trugs-web[llm] @ git+https://github.com/TRUGS-LLC/TRUGS-WEB.git"

# Verify
trugs-web --version
```

## Offline Quickstart

Try it with **no network and no LLM** on the shipped example graph ([`example.trug.json`](example.trug.json)):

```bash
trugs-web query example.trug.json --q "GraphRAG"
trugs-web synthesize example.trug.json --q "GraphRAG"
```

The `crawl`/`build` verbs fetch live web sources; the `query`/`synthesize` verbs above run entirely offline on an existing graph.

## Usage

The `trugs-web` binary exposes four verbs:

### `crawl` — Discover sources from seed URLs (no LLM)

```bash
trugs-web crawl https://example.com/research --topic "acupuncture" --max-sources 30
```

Outputs a list of discovered sources (title, URL, source type). No LLM calls.

### `build` — Crawl, extract, resolve, score → TRUGS graph

```bash
trugs-web build https://example.com/research \
  --topic "acupuncture efficacy" \
  --provider anthropic \
  --out acupuncture.trug.json
```

Full pipeline: discovers sources, extracts entities/relations via LLM, resolves duplicates, scores credibility, writes a TRUGS 1.0 JSON graph. Requires `$ANTHROPIC_API_KEY` or `$OPENAI_API_KEY` in the environment (provider-dependent).

### `query` — Traverse and find within a built graph

```bash
trugs-web query acupuncture.trug.json --q "sources for efficacy" --min-weight 0.6
```

Traverses the graph, returns matching nodes and paths as JSON.

### `synthesize` — Render a markdown report from a graph

```bash
trugs-web synthesize acupuncture.trug.json \
  --q "acupuncture evidence summary" \
  --out report.md
```

Queries the graph and synthesizes findings into a human-readable markdown document.

Every verb documents examples and options: `trugs-web <verb> --help`.

## Library Use

```python
from trugs_web import build_graph, load_graph, query_graph, generate_report

# build_graph (async) crawls the seed URLs over the live web and writes a passive graph:
#   builder = await build_graph(topic="...", seed_urls=[...], llm_provider="mock",
#                               output_path="out.trug.json")

# load_graph / query_graph operate OFFLINE on an existing graph:
graph = load_graph("example.trug.json")          # the shipped fixture
results = query_graph(graph, "GraphRAG", min_weight=0.5)
print(results)

# generate_report (async) renders a markdown report; it is also the `trugs-web synthesize` CLI verb.
```

Graph validation uses `trugs_tools.validator` internally — `TRUGSWebGraphBuilder.save(..., validate=True)` writes and validates in one step.

## Documentation

- **[ARCHITECTURE.md](ARCHITECTURE.md)** — v1 subsystem design, data flow, validation contract
- **[AGENT.md](AGENT.md)** — agent/multi-turn patterns (if used with LLM orchestration)
- **[CHANGELOG.md](CHANGELOG.md)** — v1.0 → v2.0 migration, breaking changes

## Status

**Beta.** v1 implements the Phase 1 ingestion and query pipeline. Hub federation, refresh, and self-developing loop reservation are deferred to Phase 2. Test coverage: 270 passing (respx-mocked HTTP, MockLLMClient). Pytest markers: `robots`, `rate_limit`, `cost`, `secret`, `logging`, `graph_validation_e2e`.

## License

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).

This license covers a **one-way, passive** tool. The reserved patent mechanism (US app 19/575,491) protects self-modifying graph substrates. See [NOTICE](NOTICE) for boundary and commercial licensing.

## Contributing

PRs welcome. Issues: https://github.com/TRUGS-LLC/TRUGS-WEB/issues
