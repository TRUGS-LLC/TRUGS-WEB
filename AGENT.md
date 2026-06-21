# trugs-web v1 AGENT.md

**trugs-web** is a one-way, passive web-to-TRUG builder: crawl web sources → extract entities/relations (LLM-backed, model-agnostic) → resolve → score credibility → emit a passive TRUGS graph for querying. It never closes the self-developing loop (reserved by US patent app 19/575,491).

## Module Map

```
src/trugs_web/
├── __init__.py           # Package exports
├── cli.py                # Command-line interface (crawl, build, query, synthesize)
├── _safety.py            # Tier-B safety rails (secrets, cost guard, rate limit, logging)
├── crawler.py            # Async HTTP crawling, robots.txt compliance, link extraction
├── extractor.py          # LLM-powered entity/relation extraction (Protocol-based)
├── resolver.py           # Entity deduplication & cross-reference mapping
├── credibility.py        # Source credibility scoring
├── graph_builder.py      # Orchestrate pipeline; emit TRUGS 1.0 validated by trugs_tools
├── query/
│   ├── loader.py         # Load TRUGS 1.0 graphs from disk
│   ├── traverse.py       # Graph traversal; query by concept, source, relation
│   └── synthesize.py     # Markdown report generation (async, LLM-backed)
└── weight/
    └── topology.py       # Node importance computation (centrality, freshness)

deferred_phase2/          # Phase 2 (hub federation, refresh) — NOT shipped in v1
├── hub/
│   ├── hub_agent.py      # TRUG discovery (HTTP, graph matching, LLM eval)
│   └── orchestrate.py
└── refresh/
    ├── diff.py           # Change tracking
    └── persistent_query.py
```

## LLM Seams

The extractor is **model-agnostic**: all LLM clients conform to a `Protocol`, enabling testing with `MockLLMClient` and swapping Anthropic/OpenAI without code changes.

### Protocol Definition

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class LLMClient(Protocol):
    async def complete(self, prompt: str, max_tokens: int = 1000) -> str:
        """Generate completion for prompt."""
        ...
```

### Available Implementations

1. **MockLLMClient** (`extractor.py:101-126`)
   - No API key required; returns synthetic JSON based on prompt patterns.
   - Test fixture in `conftest.py`; enables full integration testing without network calls.

2. **AnthropicClient** (`extractor.py:129-154`)
   - Uses `anthropic.AsyncAnthropic(api_key=...)` (Claude Haiku, cheap extraction).
   - API key: `$ANTHROPIC_API_KEY` environment variable (resolved via `_safety.resolve_api_key()`).
   - Model default: `claude-3-haiku-20240307`; override with `--model` flag.

3. **OpenAIClient** (`extractor.py:157-182`)
   - Uses `openai.AsyncOpenAI(api_key=...)` (GPT-3.5, cheap extraction).
   - API key: `$OPENAI_API_KEY` environment variable.
   - Model default: `gpt-3.5-turbo`; override with `--model` flag.

### Extraction Points

| Module | Method | Protocol Check |
|--------|--------|---|
| `extractor.EntityExtractor` | `extract(source: Source)` | Uses `llm.complete()` to parse entities from content. |
| `extractor.RelationExtractor` | `extract(sources: list[Source])` | Uses `llm.complete()` to infer relations between entities. |
| `extractor.CitationExtractor` | `extract(sources: list[Source])` | Uses `llm.complete()` to extract bibliographic citations. |
| `query.synthesize.ReportSynthesizer` | `synthesize(graph, query)` | Uses `llm.complete()` to render markdown reports (Phase 2 deferred). |

## Safety Rails (Tier-B)

All defined in `src/trugs_web/_safety.py`. Used by crawlers and extractors.

### 1. Secrets from Environment

```python
from trugs_web._safety import resolve_api_key

# No inline API keys; fail open (returns None if env var absent)
key = resolve_api_key("anthropic")  # reads $ANTHROPIC_API_KEY
key = resolve_api_key("openai")     # reads $OPENAI_API_KEY
```

**Test marker:** `@pytest.mark.secret` (verify keys are never logged or echoed).

### 2. Cost Guard

```python
from trugs_web._safety import CostGuard, CostBudgetExceeded

guard = CostGuard(max_calls=100, max_tokens=50000)
try:
    guard.check(prompt="...")  # raises if would exceed budget
    # proceed with LLM call
except CostBudgetExceeded as e:
    print(f"Budget exhausted: {e}")
```

**Test marker:** `@pytest.mark.cost` (verify budget ceiling blocks runaway calls).

### 3. Rate Limit + Exponential Backoff

```python
from trugs_web._safety import backoff_delay, RETRYABLE_STATUS

RETRYABLE_STATUS  # frozenset({429, 500, 502, 503, 504})

delay = backoff_delay(attempt=2)  # 0.5 * 2^2 = 2.0 seconds
# cap at 30.0 seconds
```

**Test marker:** `@pytest.mark.rate_limit` (verify inter-request delays and backoff on transient failures).

### 4. robots.txt Politeness

Implemented in `crawler.py` (async HTTP client): honors `robots.txt`, fails open if unreachable.

**Test marker:** `@pytest.mark.robots` (verify crawler respects disallow rules).

### 5. Structured Logging

```python
from trugs_web._safety import get_logger

logger = get_logger()  # returns logging.Logger("trugs_web")
logger.error("extraction failed: %s", exc)  # use stdlib logging
```

The library **does not configure handlers** (that's the application's job); it emits records so failures are visible, not swallowed.

**Test marker:** `@pytest.mark.logging` (verify error context is logged).

## Running Tests

```bash
# Full test suite (14 tests, 270+ assertions, all passing)
pytest tests/

# By marker (safe to run in CI without API keys, network, or costs)
pytest tests/ -m "not (secret or cost or robots or rate_limit)"

# Specific subsystem
pytest tests/test_web_crawler.py
pytest tests/test_web_extractor.py
pytest tests/test_web_graph_builder.py

# With coverage
pytest tests/ --cov=src/trugs_web --cov-report=term-missing
```

### Marker Conventions

| Marker | Test Harness | Cost / Network / Keys |
|--------|---|---|
| `@pytest.mark.robots` (SP4) | respx-mocked HTTP | None; robots.txt politeness check |
| `@pytest.mark.rate_limit` (SP4) | respx-mocked HTTP + asyncio | None; inter-request delay + backoff |
| `@pytest.mark.cost` (SP4) | `CostGuard` unit tests | None; verify budget ceiling logic |
| `@pytest.mark.secret` (SP4) | `resolve_api_key()` unit tests | None; verify keys from env only |
| `@pytest.mark.logging` (SP4) | `get_logger()` unit tests | None; verify error context |
| `@pytest.mark.graph_validation_e2e` (SP2) | `respx`-mocked HTTP + `trugs_tools.validator.validate_trug()` | None; end-to-end build + validation |

### Test Fixtures

- `conftest.py`: `sample_graph_dict`, `sample_graph` (TRUGS 1.0 test data with credibility).
- `test_web_cli.py`: CLI argument parsing and verb dispatch.
- `test_web_safety_rails.py`: Cost guard, rate limit, secrets, logging.
- `test_web_crawler.py`: robots.txt, link extraction, rate limiting.
- `test_web_extractor.py`: Entity/relation/citation extraction with `MockLLMClient`.
- `test_web_resolver.py`: Entity deduplication and cross-reference mapping.
- `test_web_credibility.py`: Credibility scoring and edge weighting.
- `test_web_graph_builder.py`: Pipeline orchestration, TRUGS 1.0 schema validation.
- `test_web_query_*.py`: Graph loading, traversal, report synthesis.

## One-Way, Passive Invariant

The code **must preserve** the one-way, passive contract: it builds graphs, it never closes the self-developing loop.

**Forbidden patterns** (grep to audit):

```bash
# No self-modification during traversal
grep -rE "modify|update|delete.*during.*traversal|self-modify|agent.*traverses.*and.*modifies" src/trugs_web/

# No persist-after-traversal feedback
grep -rE "write.*graph.*after.*query|feedback.*loop|refine.*based.*on.*traversal" src/trugs_web/

# No integration with trugs-agent or self-developing systems
grep -rE "trugs.agent|self.develop|dynamic.graph.*execution" src/trugs_web/
```

Phase 2 deferred features (hub federation, refresh, persistent queries) remain in `deferred_phase2/` and are **not shipped** in the v1 wheel.

## CLI

All verbs with `--help` and examples:

```bash
trugs-web crawl <seed_urls> [--topic <topic>] [--max-sources <n>]
trugs-web build <seed_urls> --topic <topic> [--out <path>] [--provider {mock|anthropic|openai}] [--model <model>]
trugs-web query <graph.trug.json> --q <query> [--min-weight <float>]
trugs-web synthesize <graph.trug.json> --q <query> [--out <path>] [--min-weight <float>]
```

Example:
```bash
export ANTHROPIC_API_KEY="sk-ant-..."
trugs-web build https://example.com --topic "acupuncture evidence" \
  --provider anthropic --out graph.trug.json
trugs-web query graph.trug.json --q "sources for acupuncture"
```

## Navigation Hints

### Find LLM Clients

```bash
grep -n "class.*Client" src/trugs_web/extractor.py
```

### Find Safety Rails Usage

```bash
grep -rn "CostGuard\|resolve_api_key\|get_logger\|backoff_delay" src/trugs_web/
```

### Find TRUGS 1.0 Validation

```bash
grep -rn "validate_trug\|trugs_tools.validator" src/trugs_web/
```

### Find Deferred Phase 2

```bash
ls -la deferred_phase2/  # not in v1 wheel
```

### Audit Protocol Conformance

```bash
# Check that extractors accept LLMClient protocol
grep -A 5 "def __init__.*llm" src/trugs_web/extractor.py
```

## Dependencies

**Required (T1 commons, downward only):**
- `trugs-tools>=2.0.0` (language core, TRUGS 1.0 schema, validator)
- `trugs-store>=2.0.0` (graph persistence)

**Optional:**
- `pip install "trugs-web[web]"` → httpx, beautifulsoup4, lxml (crawling)
- `pip install "trugs-web[llm]"` → anthropic, openai (LLM extraction)
- `pip install "trugs-web[test]"` → pytest, respx, pytest-asyncio (testing)

## Version

- **trugs-web v2.0.0** (Beta, parity with trugs-folder / trugs-tools)
- **License:** Apache-2.0 with patent NOTICE (US app 19/575,491)
