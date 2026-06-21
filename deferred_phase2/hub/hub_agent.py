"""
Hub Agent — discovers TRUGs published by others and evaluates relevance.

Three-tier discovery (from TRUGS_WEB/AAA.md §8):

* **Tier 1** (free) — HTTP fetch: discover TRUG files at known URLs,
  GitHub repos, and registries.
* **Tier 2** (free) — Graph compute: match discovered TRUGs against a
  qualifying interest, score relevance via keyword / domain overlap.
* **Tier 3** (paid, optional) — LLM: for ambiguous matches, ask an LLM
  to evaluate semantic relevance.

90 % of the work should be Tier 1 + 2.  Tier 3 is only invoked when
the Tier-2 score falls in the ambiguous band (configurable).

Reuses ``SourceDiscoverer`` from ``trugs_tools.web.crawler`` for HTTP
fetching, and ``LLMClient`` / ``MockLLMClient`` from
``trugs_tools.web.extractor`` for optional Tier-3 evaluation.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse

from .qualifying_interest import (
    QualifyingInterest,
    match_interest,
    parse_qualifying_interest,
)


# ============================================================================
# Data model
# ============================================================================

@dataclass
class HubCandidate:
    """
    A TRUG discovered by the hub agent.

    Attributes:
        url:              Where the TRUG was found (URL or file path).
        graph_data:       Parsed TRUG dict (may be None before fetch).
        qualifying_interest: Parsed QualifyingInterest (may be None).
        tier2_score:      Relevance score from Tier 2 matching [0.0, 1.0].
        tier3_score:      Optional LLM relevance score [0.0, 1.0].
        final_score:      Combined score used for ranking.
        metadata:         Extra metadata (source type, fetch status, etc.).
    """

    url: str = ""
    graph_data: Optional[dict] = None
    qualifying_interest: Optional[QualifyingInterest] = None
    tier2_score: float = 0.0
    tier3_score: Optional[float] = None
    final_score: float = 0.0
    metadata: dict = field(default_factory=dict)


# ============================================================================
# Hub Agent
# ============================================================================

# Sentinel for "no LLM client provided".
_NO_LLM = object()

# Known TRUG file patterns
_TRUG_FILE_PATTERNS = [
    "folder.trug.json",
    ".trug.json",
    "trug.json",
]

_GITHUB_RAW_PREFIX = "https://raw.githubusercontent.com"


def _is_trug_url(url: str) -> bool:
    """Heuristic: does the URL look like it points to a TRUG file?"""
    lower = url.lower()
    return any(lower.endswith(p) for p in _TRUG_FILE_PATTERNS) or "trug.json" in lower


def _github_raw_url(repo_url: str, path: str = "folder.trug.json", branch: str = "main") -> str:
    """Convert a GitHub repo URL to a raw content URL for a TRUG file."""
    parsed = urlparse(repo_url)
    # github.com/user/repo → raw.githubusercontent.com/user/repo/main/path
    parts = parsed.path.strip("/").split("/")
    if len(parts) >= 2:
        user, repo = parts[0], parts[1]
        return f"{_GITHUB_RAW_PREFIX}/{user}/{repo}/{branch}/{path}"
    return ""


def _extract_trug_urls(content: str, base_url: str) -> list:
    """Extract URLs that might point to TRUG files from page content."""
    urls: list = []
    # Look for href or src attributes pointing to trug.json files
    for match in re.finditer(r'(?:href|src)\s*=\s*["\']([^"\']+trug\.json[^"\']*)["\']', content, re.IGNORECASE):
        url = match.group(1)
        if not url.startswith("http"):
            parsed_base = urlparse(base_url)
            url = f"{parsed_base.scheme}://{parsed_base.netloc}/{url.lstrip('/')}"
        urls.append(url)
    # Look for bare URLs in text
    for match in re.finditer(r'(https?://[^\s<>"]+trug\.json[^\s<>"]*)', content, re.IGNORECASE):
        url = match.group(1)
        if url not in urls:
            urls.append(url)
    return urls


def _parse_trug_json(text: str) -> Optional[dict]:
    """Attempt to parse text as TRUG JSON. Returns None on failure."""
    try:
        data = json.loads(text)
        if isinstance(data, dict) and "nodes" in data:
            return data
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    return None


def _find_root_node(graph_data: dict) -> Optional[dict]:
    """Find the root node (no parent_id or parent_id is None)."""
    for node in graph_data.get("nodes", []):
        if node.get("parent_id") is None:
            return node
    # Fallback: first node
    nodes = graph_data.get("nodes", [])
    return nodes[0] if nodes else None


class HubAgent:
    """
    Discovers and evaluates external TRUGs via a three-tier process.

    Usage::

        agent = HubAgent(
            interest=QualifyingInterest(keywords=["machine learning"]),
        )
        candidates = await agent.discover(seed_urls)
        ranked = agent.rank(candidates)

    Args:
        interest:          What we are looking for.
        llm_client:        Optional LLMClient for Tier 3 evaluation.
        ambiguous_low:     Lower bound of ambiguous score band (Tier 3 kicks in).
        ambiguous_high:    Upper bound of ambiguous score band.
        min_relevance:     Minimum final score to keep a candidate.
        max_candidates:    Maximum candidates to return.
    """

    def __init__(
        self,
        interest: QualifyingInterest,
        llm_client: object = _NO_LLM,
        ambiguous_low: float = 0.25,
        ambiguous_high: float = 0.55,
        min_relevance: float = 0.1,
        max_candidates: int = 50,
    ):
        self.interest = interest
        self.llm_client = llm_client
        self.ambiguous_low = ambiguous_low
        self.ambiguous_high = ambiguous_high
        self.min_relevance = min_relevance
        self.max_candidates = max_candidates

    # ------------------------------------------------------------------
    # Tier 1 — HTTP discovery
    # ------------------------------------------------------------------

    async def _fetch_text(self, url: str) -> Optional[str]:
        """
        Tier 1: fetch the content of a URL as text.

        Uses httpx if available, otherwise returns None (graceful degradation).
        """
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, follow_redirects=True)
                if resp.status_code == 200:
                    return resp.text
        except Exception:
            pass
        return None

    async def discover_from_urls(self, seed_urls: list) -> list:
        """
        Tier 1: discover TRUG candidates from a list of seed URLs.

        For each URL:
          - If it looks like a TRUG JSON, try to parse it directly.
          - If it looks like a GitHub repo, try known TRUG file locations.
          - Otherwise, fetch the page and extract TRUG links.

        Returns:
            List of HubCandidate with ``graph_data`` populated.
        """
        candidates: list = []
        seen_urls: set = set()

        for url in seed_urls:
            if url in seen_urls:
                continue
            seen_urls.add(url)

            if _is_trug_url(url):
                # Direct TRUG file
                candidate = await self._try_fetch_trug(url)
                if candidate:
                    candidates.append(candidate)
            elif urlparse(url).hostname == "github.com":
                # Try common TRUG file locations in GitHub repos
                for pattern in _TRUG_FILE_PATTERNS:
                    raw_url = _github_raw_url(url, path=pattern)
                    if raw_url and raw_url not in seen_urls:
                        seen_urls.add(raw_url)
                        candidate = await self._try_fetch_trug(raw_url)
                        if candidate:
                            candidates.append(candidate)
                            break
            else:
                # Fetch page, extract TRUG links
                text = await self._fetch_text(url)
                if text:
                    trug_data = _parse_trug_json(text)
                    if trug_data:
                        candidates.append(HubCandidate(
                            url=url,
                            graph_data=trug_data,
                            metadata={"source": "direct_json"},
                        ))
                    else:
                        # Look for TRUG links in the page
                        found_urls = _extract_trug_urls(text, url)
                        for trug_url in found_urls:
                            if trug_url not in seen_urls:
                                seen_urls.add(trug_url)
                                candidate = await self._try_fetch_trug(trug_url)
                                if candidate:
                                    candidates.append(candidate)

            if len(candidates) >= self.max_candidates:
                break

        return candidates[:self.max_candidates]

    async def _try_fetch_trug(self, url: str) -> Optional[HubCandidate]:
        """Fetch a URL and try to parse it as a TRUG file."""
        text = await self._fetch_text(url)
        if text:
            data = _parse_trug_json(text)
            if data:
                return HubCandidate(
                    url=url,
                    graph_data=data,
                    metadata={"source": "trug_file"},
                )
        return None

    def discover_from_graphs(self, graphs: list) -> list:
        """
        Tier 1 (local variant): create candidates from pre-loaded graph dicts.

        Useful when graphs have already been fetched or are local files.

        Args:
            graphs: List of ``(url_or_label, graph_dict)`` tuples.

        Returns:
            List of HubCandidate with ``graph_data`` populated.
        """
        candidates: list = []
        for label, graph_data in graphs:
            if isinstance(graph_data, dict) and "nodes" in graph_data:
                candidates.append(HubCandidate(
                    url=label,
                    graph_data=graph_data,
                    metadata={"source": "local"},
                ))
        return candidates[:self.max_candidates]

    # ------------------------------------------------------------------
    # Tier 2 — Graph-compute matching
    # ------------------------------------------------------------------

    def evaluate_tier2(self, candidates: list) -> list:
        """
        Tier 2: score each candidate against the hub's qualifying interest.

        For each candidate with ``graph_data``, find the root node, parse
        its qualifying interest, and compute a match score.  Sets
        ``tier2_score`` and ``qualifying_interest`` on each candidate.

        Returns:
            The same list with scores populated (mutated in place).
        """
        for candidate in candidates:
            if candidate.graph_data is None:
                continue
            root = _find_root_node(candidate.graph_data)
            if root is None:
                continue
            qi = parse_qualifying_interest(root)
            candidate.qualifying_interest = qi
            if qi and qi.is_valid:
                candidate.tier2_score = match_interest(self.interest, qi)
            else:
                # No qualifying interest → use fallback heuristics
                candidate.tier2_score = self._fallback_score_from_root(root)
            candidate.final_score = candidate.tier2_score
        return candidates

    def _fallback_score_from_root(self, root: dict) -> float:
        """Score a root node against hub keywords without qualifying_interest."""
        props = root.get("properties", {})
        text_parts: list = [
            str(props.get("name", "")),
            str(props.get("topic", "")),
            str(props.get("description", "")),
        ]
        combined = " ".join(text_parts).lower()
        if not combined.strip():
            return 0.0

        matched = 0
        for kw in self.interest.keywords:
            if kw.lower() in combined:
                matched += 1
        if not self.interest.keywords:
            return 0.0
        return round(matched / len(self.interest.keywords) * 0.5, 4)

    # ------------------------------------------------------------------
    # Tier 3 — LLM evaluation (optional, paid)
    # ------------------------------------------------------------------

    async def evaluate_tier3(self, candidates: list) -> list:
        """
        Tier 3: use LLM to evaluate ambiguous candidates.

        Only invoked for candidates whose ``tier2_score`` falls in the
        ambiguous band [ambiguous_low, ambiguous_high].

        Requires an LLM client that implements ``async complete(prompt) -> str``.

        Returns:
            The same list with ``tier3_score`` and updated ``final_score``
            where applicable.
        """
        if self.llm_client is _NO_LLM:
            return candidates

        for candidate in candidates:
            if candidate.tier2_score < self.ambiguous_low:
                continue
            if candidate.tier2_score > self.ambiguous_high:
                continue

            score = await self._llm_evaluate(candidate)
            if score is not None:
                candidate.tier3_score = score
                # Blend: 50 % Tier 2 + 50 % Tier 3
                candidate.final_score = round(
                    0.5 * candidate.tier2_score + 0.5 * score, 4
                )

        return candidates

    async def _llm_evaluate(self, candidate: HubCandidate) -> Optional[float]:
        """Ask the LLM to score the relevance of a candidate TRUG."""
        root = _find_root_node(candidate.graph_data) if candidate.graph_data else None
        if root is None:
            return None

        props = root.get("properties", {})
        prompt = (
            "Rate the relevance (0.0-1.0) of the following TRUG to the topic.\n"
            f"Topic keywords: {', '.join(self.interest.keywords)}\n"
            f"TRUG name: {props.get('name', 'unknown')}\n"
            f"TRUG description: {props.get('description', 'none')}\n"
            "Reply with ONLY a number between 0.0 and 1.0."
        )
        try:
            result = await self.llm_client.complete(prompt, max_tokens=50)
            # Extract first float from response
            for token in result.split():
                try:
                    score = float(token.strip(".,;"))
                    if 0.0 <= score <= 1.0:
                        return round(score, 4)
                except ValueError:
                    continue
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------
    # Ranking
    # ------------------------------------------------------------------

    def rank(self, candidates: list) -> list:
        """
        Rank candidates by final_score, filtering by min_relevance.

        Returns:
            Sorted list of HubCandidate (highest score first).
        """
        filtered: list = [
            c for c in candidates if c.final_score >= self.min_relevance
        ]
        filtered.sort(key=lambda c: c.final_score, reverse=True)
        return filtered

    # ------------------------------------------------------------------
    # Full pipeline
    # ------------------------------------------------------------------

    async def discover(self, seed_urls: list) -> list:
        """
        Full hub discovery pipeline: Tier 1 → Tier 2 → Tier 3 → rank.

        Args:
            seed_urls: URLs to start discovery from.

        Returns:
            Ranked list of HubCandidate.
        """
        candidates = await self.discover_from_urls(seed_urls)
        self.evaluate_tier2(candidates)
        await self.evaluate_tier3(candidates)
        return self.rank(candidates)
