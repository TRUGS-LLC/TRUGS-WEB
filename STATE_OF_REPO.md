# State of the Repo — TRUGS-WEB-TOOLS

> **Purpose.** A factual, verified snapshot of this repository's present state, written as
> the starting point for the redesign + integration tracked by EPIC
> [Xepayac/TRUGS-DEVELOPMENT#2295](https://github.com/Xepayac/TRUGS-DEVELOPMENT/issues/2295)
> ("integrate TRUGS-WEB-TOOLS web research-substrate into TRUGS-START — redesign for
> external users"). It describes *what is here now* — not what should be built. Every
> count and claim below was reproduced, not quoted.

- **Snapshot date:** 2026-06-06
- **Commit:** `9fc5c18` (`main`)
- **Author of inventory:** Claude Code (verification run), for HITM (William E. Leigh / Xepayac)

---

## 1. TL;DR — the one-screen verdict

The web research-substrate is **functionally complete and well-tested code** — 5 subsystems,
20 Python modules, ~5,023 LOC, **0 stubs / 0 TODOs / 0 `NotImplementedError`**. The test
corpus is **431 tests / 746 assertions** — *both numbers confirmed exactly* by re-running.

It is **not yet a runnable, standalone product**. The blockers are all *packaging and
plumbing*, not logic:

| # | Blocker | Impact |
|---|---|---|
| B1 | **No packaging** — no `pyproject.toml` / `setup.py` / `requirements.txt` | Repo cannot be installed or its deps resolved |
| B2 | **Tests import `trugs_tools.web.*`**, but this repo ships the package at `web/` | Suite cannot find this repo's code without a remap |
| B3 | **Shared `tests/conftest.py` was dropped in migration** | 54 of 431 tests **error** (missing `sample_graph` fixtures) until restored |
| B4 | **Hard dependency on `trugs_tools.validator`** | `graph_builder.validate()` needs the parent package that #2191 just decoupled from |
| B5 | **No CLI / entrypoint / `__main__`** | "Works" only as an imported library; no user-facing surface |
| B6 | **36 `.pyc` files tracked in git; no `.gitignore`** | Repo hygiene |
| B7 | **`README.md` / `web/__init__.py` still say `pip install trugs-tools[web,llm]`** | Install story is stale post-#2191 |
| B8 | **`folder.trug.json` is a one-node stub** | Machine-readable structure doesn't describe actual contents |

**Bottom line:** the *engine* is healthy; what's missing is the *vehicle around it*
(packaging, test harness, CLI, repo independence). That is exactly the scope #2295 exists
to define.

---

## 2. Repository metadata

| Field | Value |
|---|---|
| Remote | `https://github.com/Xepayac/TRUGS-WEB-TOOLS` (**PRIVATE**) |
| Default branch | `main` @ `9fc5c18` |
| Commit history | 3 commits total — `feat: initial migration` → `chore: add TRUG infrastructure` → merge PR #1 |
| Migration origin | `TRUGS-DEVELOPMENT/TRUGS_TOOLS/trugs_tools/web/`, copied 2026-04-13 |
| License | **Proprietary** — Copyright © 2026 Xepayac LLC. Not licensed for use/modification/distribution. |
| Open PRs | **#2** `feat: receive EXAMPLES/web handoff from trugs_tools (AAA #2191 S3)` — adds `EXAMPLES/web/{minimal,medium,complex,complete}.json` + README (605 insertions). Does **not** add packaging or restore the conftest. |
| Tracked files | 39 source/meta files **+ 36 stale `.pyc`** (see B6) |
| `.gitignore` | **absent** |

### Tracked layout (excluding `.pyc`)
```
CLAUDE.md  LICENSE  README.md  folder.trug.json
web/
  __init__.py  crawler.py  credibility.py  extractor.py  graph_builder.py  resolver.py
  hub/    __init__.py  cross_trug_edges.py  hub_agent.py  orchestrate.py  qualifying_interest.py
  query/  __init__.py  loader.py  synthesize.py  traverse.py
  refresh/__init__.py  diff.py  persistent_query.py
  weight/ __init__.py  topology.py
tests/  (16 test_web_*.py — no conftest.py)
```

---

## 3. Test suite — verification (the headline)

**Claim under test:** "431 tests / 746 asserts, 0 stubs/TODOs (mocked via respx)."

**Result: all three confirmed.**

| Metric | Claimed | Measured | Method |
|---|---|---|---|
| Tests collected | 431 | **431** | `pytest --collect-only` |
| Assertions | 746 | **746** | `grep -rcE '^\s*assert ' tests/*.py` (+3 `pytest.raises`) |
| Stubs / TODOs | 0 | **0** | `grep TODO\|FIXME\|XXX\|NotImplementedError web/` → none |

### As-shipped vs. repaired

- **As shipped (this repo, untouched):** `377 passed, 54 errors`. The 54 errors are **not
  failures** — they are *collection-time fixture errors*: the 3 `query/` test files
  (`test_web_query_{loader,traverse,synthesize}.py`) reference fixtures `sample_graph` /
  `sample_graph_dict` that live in a `tests/conftest.py` **which was never migrated** (it
  still exists at `TRUGS-TOOLS-dev/tests/conftest.py`, 88 lines).
- **With the dropped conftest restored:** `431 passed` in ~0.6s. The code is healthy; only
  the harness is missing.

> `377 (pass) + 54 (fixture-errored) = 431 (collected)` — which is precisely why the "431"
> figure was reproducible even though a clean checkout cannot currently get to green.

### Reproduction recipe (exact)

This repo has no packaging, so a faithful run requires a small harness. Recorded here so
the next session can reproduce byte-for-byte:

```bash
# 1. Isolated env + deps (none are declared in-repo)
python3 -m venv /tmp/wtenv
/tmp/wtenv/bin/pip install pytest pytest-asyncio respx httpx anthropic openai beautifulsoup4 lxml
/tmp/wtenv/bin/pip install -e /home/arek/REPO/TRUGS-TOOLS-dev   # provides trugs_tools.validator

# 2. Remap trugs_tools.web -> THIS repo's web/ (tests import trugs_tools.web.*),
#    via an ephemeral conftest.py at repo root that loads web/__init__.py under that name.
# 3. Restore the dropped fixtures:
cp /home/arek/REPO/TRUGS-TOOLS-dev/tests/conftest.py tests/conftest.py

# 4. Run
/tmp/wtenv/bin/python -m pytest tests/ -o asyncio_mode=auto -q   # -> 431 passed
```

> Mocking: HTTP is mocked with `respx`; the LLM seam is mocked with the in-repo
> `MockLLMClient`. No network or API keys are touched by the suite.

### Test distribution (collected, per file)

| Tests | File | Tests | File |
|---:|---|---:|---|
| 45 | test_web_hub_cross_trug_edges | 25 | test_web_credibility |
| 44 | test_web_query_loader | 24 | test_web_query_traverse |
| 41 | test_web_hub_agent | 20 | test_web_refresh_persistent_query |
| 39 | test_web_extractor | 20 | test_web_crawler |
| 33 | test_web_hub_qualifying_interest | 18 | test_web_resolver |
| 32 | test_web_refresh_diff | 18 | test_web_query_synthesize |
| 31 | test_web_weight_topology | 10 | test_web_hub_orchestrate |
| 29 | test_web_graph_builder | 2 | test_web_query_integration |

Test code: **4,150 LOC** across 16 files (a ~0.83 test:source LOC ratio).

---

## 4. Subsystem & module inventory (5 subsystems · 20 modules · ~5,023 LOC)

Pipeline shape (from README): **Source Discovery → Entity Extraction → Resolution →
Credibility → Graph Building → Hub Discovery ↔ Query/Traverse → Refresh.**

### 4.1 Ingestion pipeline (root of `web/`)

| Module | LOC | Public surface | Notes |
|---|---:|---|---|
| `crawler.py` | 244 | `Source`, `SourceDiscoverer.discover()` (async), `discover_sources()` | Async HTTP source discovery; robots/link extraction. `httpx`+`bs4` imported **lazily** with graceful-degradation errors. No LLM. |
| `extractor.py` | 462 | `Entity`, `Relation`, `LLMClient` (Protocol), `MockLLMClient`, `AnthropicClient`, `OpenAIClient`, `EntityExtractor`, `RelationExtractor`, `CitationExtractor`, `create_extractor()` | LLM-backed entity/relation/citation extraction. **Model-agnostic seam**: a `LLMClient` Protocol with Mock/Anthropic/OpenAI impls (the `...` at line 93 is the Protocol body, not a stub). |
| `resolver.py` | 262 | `ResolvedEntity`, `EntityResolver.resolve()`, `CrossReferenceMapper`, `resolve_entities()` | Entity dedup + cross-reference mapping (`difflib.SequenceMatcher`). Pure stdlib. |
| `credibility.py` | 293 | `CredibilityFactors`, `CredibilityScorer.{score_source,score_edge}()`, `calculate_credibility()`, `score_edge_weight()` | Source trust → edge weight. Domain trust table (e.g. `openai.com`, `anthropic.com`). Pure stdlib. |
| `graph_builder.py` | 417 | `TRUGSWebGraphBuilder` (+`validate()`, `to_dict/json`, `save`), `build_graph()` (async), `load_graph()`, `url_to_id()`, `make_id()` | Assembles entities/relations into a **TRUGS 1.0 graph**. `validate()` calls `trugs_tools.validator.validate_trug` (**external coupling — B4**). |

### 4.2 Query (`web/query/`)

| Module | LOC | Public surface | Notes |
|---|---:|---|---|
| `loader.py` | 431 | `Node`, `Edge`, `GraphMeta`, `Graph` (rich graph API: `get_node`, `find_nodes`, `traverse`, `find_path`, `get_top_nodes`, `get_edge_stats`, …), `GraphLoader`, `load_graph()` | In-memory graph model + loader from dict/file/string. Pure stdlib. |
| `traverse.py` | 299 | `TraversalResult`, `GraphTraverser` (`concept_sources`, `related_concepts`, `citation_chain`, `high_credibility_sources`, `weighted_consensus`, `alternatives`, …), `query_graph()` | Query-intent traversal over a loaded graph. |
| `synthesize.py` | 435 | `Finding`, `Report`, `ReportSynthesizer.synthesize()` (async), `generate_report()` (async) | Report generation (markdown), optional LLM synthesis (mockable). |

### 4.3 Weight (`web/weight/`)

| Module | LOC | Public surface | Notes |
|---|---:|---|---|
| `topology.py` | 181 | `NodeTopology`, `compute_topology()`, `rank_by_importance()`, `find_convergence()`, `compute_freshness()` | Query-time node importance across loaded TRUGs. Pure stdlib. |

### 4.4 Hub / federation (`web/hub/`)

| Module | LOC | Public surface | Notes |
|---|---:|---|---|
| `hub_agent.py` | 437 | `HubCandidate`, `HubAgent` (`discover_from_urls` async, `discover_from_graphs`, `evaluate_tier2`, `evaluate_tier3` async, `rank`, `discover` async) | 3-tier discovery of TRUGs published by others (HTTP → graph matching → LLM eval). `httpx` lazy, graceful degradation. |
| `qualifying_interest.py` | 200 | `QualifyingInterest`, `parse_qualifying_interest()`, `match_interest()`, `rank_matches()` | How a TRUG declares what it is about (the federation matching key). |
| `cross_trug_edges.py` | 335 | `CrossTrugUri`, `CrossTrugEdge`, `parse_cross_trug_uri()`, `is_cross_trug_ref()`, `build_cross_trug_uri()`, `validate_cross_trug_edge()`, `CrossTrugResolver` | Cross-graph edge URIs + resolution (edges in one TRUG referencing nodes in another). |
| `orchestrate.py` | 288 | `PipelineResult`, `Orchestrator.{run,run_and_save}()` (async) | Full URLs → validated TRUGS 1.0 graph pipeline (the top-level driver). |

### 4.5 Refresh (`web/refresh/`)

| Module | LOC | Public surface | Notes |
|---|---:|---|---|
| `diff.py` | 217 | `TrugDiff`, `diff_trugs()`, `apply_diff()` | Changeset diff/apply between two TRUG graph dicts. Pure stdlib. |
| `persistent_query.py` | 193 | `PersistentQuery`, `QueryDiffResult`, `QueryStore` (`save/load/list/delete`), `QueryRunner.run()` (async) | Store / reload / re-run web queries. |

> `web/__init__.py` (153 LOC) re-exports a flat public API of **~60 names** via `__all__`,
> spanning all five subsystems. Construct counts across `web/`: **20 `@dataclass`**,
> **25 `async def`**.

---

## 5. Dependencies

**Declared in-repo:** none (no requirements/pyproject — **B1**).

**Actually required (discovered by import analysis):**

| Dependency | Used by | Import style |
|---|---|---|
| `httpx` | crawler, hub_agent | **lazy** (inside funcs), graceful-degradation message |
| `beautifulsoup4` (`bs4`) | crawler | **lazy** |
| `lxml` | crawler (parser) | via bs4 |
| `anthropic` | extractor (`AnthropicClient`) | **lazy** |
| `openai` | extractor (`OpenAIClient`) | **lazy** |
| `trugs_tools.validator` | graph_builder.`validate()` | **lazy**, but a hard external coupling (**B4**) |
| *(test only)* `pytest`, `pytest-asyncio`, `respx` | suite | top-level in tests |

Module code otherwise uses **only the stdlib** (`dataclasses`, `typing`, `re`, `json`,
`urllib.parse`, `pathlib`, `datetime`, `asyncio`, `difflib`). The lazy-import pattern means
`import web` succeeds with zero third-party packages installed — deps are only needed when
the corresponding feature actually runs. This is a genuine strength to preserve in any
redesign (it matches the memory note: *keep a model-agnostic seam rather than hardwiring
Claude*).

---

## 6. What is solid (carry forward)

- **Logic is complete and green** — 431/431 once the harness exists; 0 stubs/TODOs.
- **Clean layering** — 5 subsystems with narrow public APIs and a flat re-export facade.
- **Model-agnostic LLM seam** — `LLMClient` Protocol + Mock/Anthropic/OpenAI.
- **Mockable I/O** — `respx` for HTTP, `MockLLMClient` for LLM; suite needs no network/keys.
- **Lazy optional deps** — import-time cost is stdlib-only; features degrade gracefully.
- **Strong test density** — ~0.83 test:source LOC, 746 assertions.

## 7. What is missing / stale (the building backlog seed)

Mapped to the blockers in §1:

1. **Packaging (B1)** — add `pyproject.toml`, declare deps + `[web]`/`[llm]` extras, define
   the import package name. *This is the keystone decision* (see §8).
2. **Import identity (B2)** — code lives at `web/` but tests/clients say `trugs_tools.web`.
   The redesign must pick one canonical package name and align tests to it.
3. **Test harness (B3)** — restore/replace `tests/conftest.py` (the `sample_graph` fixtures)
   so a clean checkout reaches green.
4. **Validator coupling (B4)** — decide whether to vendor, depend on, or replace
   `trugs_tools.validator`; #2191 just decoupled this repo from `trugs_tools`, so a
   lingering hard reference is a contradiction to resolve.
5. **No product surface (B5)** — no CLI/entrypoint; the issue's "no external consumers"
   gap. The external-user shape is the open question in #2295.
6. **Repo hygiene (B6)** — remove 36 tracked `.pyc`, add `.gitignore`.
7. **Docs drift (B7)** — `README.md` + `web/__init__.py` advertise
   `pip install trugs-tools[web,llm]`, which no longer reflects a standalone repo.
8. **Structure stub (B8)** — `folder.trug.json` describes a single root node; it should
   enumerate the real subsystem/module structure (it is `tg validate`-VALID as-is).

## 8. Implications for the #2295 build

The first fork in the road is **language & repo strategy** (the issue's "decide first"):

- **If it stays Python:** the work is largely *packaging + harness + CLI* around healthy
  code — graduate `Xepayac/TRUGS-WEB-TOOLS → TRUGS-LLC/WEB-TOOLS` (+ `-dev` mirror),
  resolve B1–B4, and design the external-user surface (B5). The 431-test corpus becomes the
  regression net from day one.
- **If it is rewritten (e.g. Go):** this repo becomes the **executable specification** —
  the module inventory in §4 and the 746 assertions define behavior to port, and the green
  Python suite is the oracle.

Either way, **nothing here needs to be re-discovered** — the substrate works; #2295 is about
giving it a body (packaging, identity, a user-facing surface) and a home (repo graduation).

---

## Appendix — verification commands

```bash
# Counts
git ls-tree -r --name-only main | grep -v '\.pyc$'        # tracked files
find web -name '*.py' | xargs wc -l                       # 5,023 LOC
grep -rcE '^\s*assert ' tests/*.py | awk -F: '{s+=$NF}END{print s}'   # 746
grep -rnE 'TODO|FIXME|XXX|NotImplementedError' web/ | wc -l           # 0
tg validate folder.trug.json                              # VALID
# Suite: see §3 reproduction recipe -> 431 passed
```
