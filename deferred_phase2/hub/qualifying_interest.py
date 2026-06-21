"""
Qualifying Interest — how a TRUG declares what it is about.

A hub is any TRUG whose root node carries a ``qualifying_interest`` in
its properties dict.  The qualifying interest is a lightweight topic
descriptor: a set of keywords, an optional domain scope, and optional
free-text description.

Specification (from TRUGS_WEB/AAA.md §1, §8):

* ``qualifying_interest`` lives in ``properties`` on the root node.
* It contains:
    - ``keywords``  — list of topic strings (required, >= 1)
    - ``domain``    — broad domain string (optional, e.g. "machine-learning")
    - ``scope``     — free-text scope description (optional)
* Any TRUG *could* be a hub; there is no separate "hub" type.
* Matching is pure Tier 2 (graph compute, no LLM).
* Weight means curator endorsement (0.0–1.0), nothing else.
"""

import re
from dataclasses import dataclass, field
from typing import Optional


# ============================================================================
# Data model
# ============================================================================

@dataclass
class QualifyingInterest:
    """
    Describes what a TRUG is about.

    Attributes:
        keywords: Topic keywords that define the interest (>= 1 required).
        domain: Broad domain scope (e.g. "machine-learning", "biology").
        scope: Free-text description of the scope.
    """

    keywords: list = field(default_factory=list)
    domain: str = ""
    scope: str = ""

    @property
    def is_valid(self) -> bool:
        """A qualifying interest is valid when it has at least one keyword."""
        return len(self.keywords) > 0


# ============================================================================
# Parsing
# ============================================================================

def parse_qualifying_interest(root_node: dict) -> Optional[QualifyingInterest]:
    """
    Extract a QualifyingInterest from a TRUG root node.

    The root node must have ``properties.qualifying_interest`` with at
    least a ``keywords`` list.  Returns *None* when the node has no
    qualifying interest or the data is invalid.

    Args:
        root_node: A TRUG 1.0 node dict (must have ``properties``).

    Returns:
        QualifyingInterest or None.
    """
    props = root_node.get("properties", {})
    qi_data = props.get("qualifying_interest")
    if qi_data is None:
        return None

    if isinstance(qi_data, dict):
        keywords = qi_data.get("keywords", [])
        domain = qi_data.get("domain", "")
        scope = qi_data.get("scope", "")
    elif isinstance(qi_data, list):
        # Shorthand: bare list treated as keywords
        keywords = qi_data
        domain = ""
        scope = ""
    elif isinstance(qi_data, str):
        # Shorthand: bare string treated as single keyword
        keywords = [qi_data]
        domain = ""
        scope = ""
    else:
        return None

    # Normalise keywords
    keywords = [str(k).strip().lower() for k in keywords if str(k).strip()]
    if not keywords:
        return None

    qi = QualifyingInterest(
        keywords=keywords,
        domain=str(domain).strip().lower(),
        scope=str(scope).strip(),
    )
    return qi


# ============================================================================
# Matching
# ============================================================================

def _normalise(text: str) -> str:
    """Lower-case, collapse whitespace / punctuation, strip."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _token_overlap(a_tokens: set, b_tokens: set) -> float:
    """Jaccard-style overlap capped at 1.0."""
    if not a_tokens or not b_tokens:
        return 0.0
    intersection = a_tokens & b_tokens
    union = a_tokens | b_tokens
    return len(intersection) / len(union)


def match_interest(
    interest: QualifyingInterest,
    candidate: QualifyingInterest,
) -> float:
    """
    Compute a [0.0, 1.0] relevance score between two qualifying interests.

    Scoring:
      * 60 % keyword overlap  (Jaccard on normalised token sets)
      * 30 % domain match     (exact match = 1.0, partial token overlap)
      * 10 % scope overlap    (token overlap on free-text scope)

    Pure Tier 2 — no LLM, no network access.

    Args:
        interest:  The hub's qualifying interest (what we are looking for).
        candidate: The candidate TRUG's qualifying interest.

    Returns:
        Float in [0.0, 1.0].
    """
    # Keyword overlap (60 %)
    a_kw = set()
    for kw in interest.keywords:
        a_kw.update(_normalise(kw).split())
    b_kw = set()
    for kw in candidate.keywords:
        b_kw.update(_normalise(kw).split())
    kw_score = _token_overlap(a_kw, b_kw)

    # Domain match (30 %)
    if interest.domain and candidate.domain:
        a_dom = set(_normalise(interest.domain).split())
        b_dom = set(_normalise(candidate.domain).split())
        domain_score = _token_overlap(a_dom, b_dom)
    elif not interest.domain and not candidate.domain:
        domain_score = 0.0  # absence is not agreement
    else:
        domain_score = 0.0

    # Scope overlap (10 %)
    if interest.scope and candidate.scope:
        a_scope = set(_normalise(interest.scope).split())
        b_scope = set(_normalise(candidate.scope).split())
        scope_score = _token_overlap(a_scope, b_scope)
    elif not interest.scope and not candidate.scope:
        scope_score = 0.0  # absence is not agreement
    else:
        scope_score = 0.0

    return round(0.6 * kw_score + 0.3 * domain_score + 0.1 * scope_score, 4)


def rank_matches(
    interest: QualifyingInterest,
    candidates: list,
    min_score: float = 0.1,
) -> list:
    """
    Rank candidate QualifyingInterest objects against *interest*.

    Args:
        interest:   The hub's qualifying interest.
        candidates: List of ``(label, QualifyingInterest)`` tuples.
        min_score:  Minimum relevance score to include (default 0.1).

    Returns:
        Sorted list of ``(label, score)`` tuples, highest score first.
    """
    results: list = []
    for label, candidate_qi in candidates:
        score = match_interest(interest, candidate_qi)
        if score >= min_score:
            results.append((label, score))
    results.sort(key=lambda x: x[1], reverse=True)
    return results
