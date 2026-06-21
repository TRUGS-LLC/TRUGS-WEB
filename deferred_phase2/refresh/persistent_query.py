"""
Persistent Queries — store, reload, and re-execute TRUGS web queries.

A persistent query captures a complete set of parameters (topic, seed URLs,
qualifying interest, schedule) so that it can be re-run on demand and the
results compared between runs.

Reuses :class:`~trugs_tools.web.hub.orchestrate.Orchestrator` and
:class:`~trugs_tools.web.hub.qualifying_interest.QualifyingInterest`.

Design constraints (TRUGS_WEB/AAA.md §8):
  - JSON file-based storage — no database needed.
  - No new dependencies.
"""

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional

from ..hub.orchestrate import Orchestrator, PipelineResult
from .diff import TrugDiff, diff_trugs


# ============================================================================
# Data structures
# ============================================================================

@dataclass
class PersistentQuery:
    """
    A stored query that can be re-executed.

    Attributes:
        query_id:            Unique identifier (typically slugified topic).
        topic:               Research topic string.
        seed_urls:           Starting URLs for crawling.
        qualifying_interest: Optional QualifyingInterest for hub matching.
        schedule:            Cron-like schedule hint (informational only).
        last_run:            ISO-8601 timestamp of the most recent execution.
        llm_provider:        LLM provider to use ("mock", "anthropic", "openai").
        max_sources:         Maximum sources to crawl.
        last_graph:          The graph dict from the most recent run.
    """

    query_id: str
    topic: str
    seed_urls: list = field(default_factory=list)
    qualifying_interest: Optional[dict] = None
    schedule: str = ""
    last_run: str = ""
    llm_provider: str = "mock"
    max_sources: int = 50
    last_graph: Optional[dict] = None


@dataclass
class QueryDiffResult:
    """
    Outcome of re-running a persistent query.

    Attributes:
        query_id:    Which query was re-executed.
        previous:    The graph dict from the previous run (or None).
        current:     The graph dict from this run.
        diff:        A TrugDiff between previous and current.
        errors:      Any pipeline errors encountered.
    """

    query_id: str
    previous: Optional[dict] = None
    current: Optional[dict] = None
    diff: Optional[TrugDiff] = None
    errors: list = field(default_factory=list)


# ============================================================================
# QueryStore — JSON file-based persistence
# ============================================================================

class QueryStore:
    """
    Save and load persistent queries to/from a JSON file.

    The store file is a JSON object mapping ``query_id`` → serialised
    ``PersistentQuery``.

    Args:
        store_path: Filesystem path for the JSON store file.
    """

    def __init__(self, store_path: str):
        self.store_path = store_path

    def _load_all(self) -> dict:
        if not os.path.exists(self.store_path):
            return {}
        with open(self.store_path, "r", encoding="utf-8") as fh:
            return json.load(fh)

    def _save_all(self, data: dict) -> None:
        parent = os.path.dirname(self.store_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(self.store_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)

    def save(self, query: PersistentQuery) -> None:
        """Save or update a persistent query."""
        data = self._load_all()
        data[query.query_id] = asdict(query)
        self._save_all(data)

    def load(self, query_id: str) -> Optional[PersistentQuery]:
        """Load a persistent query by ID. Returns None if not found."""
        data = self._load_all()
        entry = data.get(query_id)
        if entry is None:
            return None
        return PersistentQuery(**entry)

    def list_queries(self) -> list:
        """Return a list of all stored query IDs."""
        data = self._load_all()
        return sorted(data.keys())

    def delete(self, query_id: str) -> bool:
        """Delete a persistent query. Returns True if found and deleted."""
        data = self._load_all()
        if query_id not in data:
            return False
        del data[query_id]
        self._save_all(data)
        return True


# ============================================================================
# QueryRunner — re-execute a stored query and diff the results
# ============================================================================

class QueryRunner:
    """
    Re-execute a :class:`PersistentQuery` using the Orchestrator and
    diff the new graph against the previous one.

    Args:
        store: A :class:`QueryStore` instance for loading/saving queries.
    """

    def __init__(self, store: QueryStore):
        self.store = store

    async def run(self, query: PersistentQuery) -> QueryDiffResult:
        """
        Execute the query's pipeline and produce a diff against the
        previous run.

        The query's ``last_run`` and ``last_graph`` are updated and
        persisted back to the store.

        Args:
            query: The persistent query to re-execute.

        Returns:
            A :class:`QueryDiffResult`.
        """
        result = QueryDiffResult(query_id=query.query_id)
        result.previous = query.last_graph

        # Build and run orchestrator
        orch = Orchestrator(
            topic=query.topic,
            llm_provider=query.llm_provider,
            max_sources=query.max_sources,
        )
        pipeline_result: PipelineResult = await orch.run(query.seed_urls)
        result.errors = list(pipeline_result.errors)
        result.current = pipeline_result.graph_dict

        # Compute diff
        if result.previous is not None and result.current is not None:
            result.diff = diff_trugs(result.previous, result.current)
        elif result.current is not None:
            # First run — everything is "added"
            result.diff = diff_trugs({}, result.current)

        # Update and persist the query
        query.last_run = datetime.now(timezone.utc).isoformat()
        query.last_graph = result.current
        self.store.save(query)

        return result
