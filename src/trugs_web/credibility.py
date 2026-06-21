"""
Credibility Scoring Module

Calculates credibility scores and initial edge weights based on source
quality signals (peer review, venue quality, recency, citations, authorship).

Scores are capped at 0.95 — a perfect score is never assigned automatically.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

from .crawler import Source
from .extractor import Relation


@dataclass
class CredibilityFactors:
    """Factors contributing to a source credibility score."""

    peer_reviewed: float = 0.0  # +0.3 max
    author_credentials: float = 0.0  # +0.2 max
    citation_score: float = 0.0  # +0.2 max
    venue_quality: float = 0.0  # +0.2 max
    recency: float = 0.0  # +0.1 max

    _CAP: float = 0.95

    @property
    def total(self) -> float:
        """Credibility score capped at 0.95."""
        raw = (
            self.peer_reviewed
            + self.author_credentials
            + self.citation_score
            + self.venue_quality
            + self.recency
        )
        return min(self._CAP, raw)

    def to_dict(self) -> dict:
        return {
            "peer_reviewed": self.peer_reviewed,
            "author_credentials": self.author_credentials,
            "citation_score": self.citation_score,
            "venue_quality": self.venue_quality,
            "recency": self.recency,
            "total": self.total,
        }


# Domain quality rankings
HIGH_QUALITY_DOMAINS = {
    "nature.com": 0.2,
    "science.org": 0.2,
    "cell.com": 0.2,
    "ieee.org": 0.18,
    "acm.org": 0.18,
    "arxiv.org": 0.15,
    "springer.com": 0.15,
    "wiley.com": 0.15,
    "elsevier.com": 0.15,
    "plos.org": 0.15,
    "pubmed.ncbi.nlm.nih.gov": 0.18,
    "docs.python.org": 0.15,
    "pytorch.org": 0.15,
    "tensorflow.org": 0.15,
    "reactjs.org": 0.15,
    "openai.com": 0.12,
    "anthropic.com": 0.12,
    "google.ai": 0.12,
    "ai.meta.com": 0.12,
    "microsoft.com": 0.10,
    "aws.amazon.com": 0.10,
    "techcrunch.com": 0.08,
    "arstechnica.com": 0.08,
    "wired.com": 0.08,
    "theverge.com": 0.06,
}

MODERATE_QUALITY_DOMAINS = {
    "github.com": 0.10,
    "stackoverflow.com": 0.08,
    "dev.to": 0.05,
    "hackernews.com": 0.05,
    "medium.com": 0.03,
    "substack.com": 0.05,
    "wordpress.com": 0.02,
    "blogger.com": 0.02,
}

LOW_QUALITY_SIGNALS = [
    "pinterest",
    "facebook.com",
    "twitter.com",
    "x.com",
    "reddit.com",
    "quora.com",
]


class CredibilityScorer:
    """
    Scores source and edge credibility.

    All scores are capped at 0.95 — initial credibility signals only
    (starting weights, not topology).
    """

    def __init__(self):
        self.high_quality = HIGH_QUALITY_DOMAINS
        self.moderate_quality = MODERATE_QUALITY_DOMAINS
        self.low_quality_signals = LOW_QUALITY_SIGNALS

    def score_source(self, source: Source) -> CredibilityFactors:
        """
        Calculate credibility factors for a source.

        Args:
            source: Source to score

        Returns:
            CredibilityFactors with breakdown (total capped at 0.95)
        """
        factors = CredibilityFactors()
        domain = urlparse(source.url).netloc.lower()

        factors.peer_reviewed = self._score_peer_review(source, domain)
        factors.author_credentials = self._score_author(source)
        factors.citation_score = self._score_citations(source)
        factors.venue_quality = self._score_venue(domain)
        factors.recency = self._score_recency(source)

        return factors

    def score_edge(
        self,
        relation: Relation,
        from_source: Optional[Source] = None,
        to_source: Optional[Source] = None,
    ) -> float:
        """
        Calculate weight for an edge (capped at 0.95).

        Uses source credibility if available, otherwise uses
        the relation's confidence as baseline.
        """
        if from_source:
            factors = self.score_source(from_source)
            base_score = factors.total
        else:
            base_score = min(0.95, relation.confidence)

        relation_multipliers = {
            "CITES": 1.0,
            "DEFINES": 0.95,
            "USES": 0.9,
            "EXTENDS": 0.9,
            "SUPPORTS": 0.85,
            "CONTRADICTS": 0.8,
            "RELATED_TO": 0.7,
            "ALTERNATIVE_TO": 0.75,
        }
        multiplier = relation_multipliers.get(relation.relation_type, 0.7)
        return min(0.95, base_score * multiplier)

    def _score_peer_review(self, source: Source, domain: str) -> float:
        if source.source_type == "PAPER":
            if "arxiv" in domain:
                return 0.15
            return 0.3
        if source.source_type == "DOCUMENTATION":
            return 0.2
        if source.source_type == "ARTICLE":
            if any(d in domain for d in ["nature", "science", "ieee"]):
                return 0.25
            return 0.1
        if source.source_type == "PROJECT":
            return 0.1
        return 0.0

    def _score_author(self, source: Source) -> float:
        author = source.metadata.get("author", {})
        if isinstance(author, dict):
            h_index = author.get("h_index", 0)
            if h_index > 50:
                return 0.2
            if h_index > 20:
                return 0.15
            if h_index > 10:
                return 0.1
            if h_index > 0:
                return 0.05
        stars = source.metadata.get("stars", 0)
        if stars > 10000:
            return 0.15
        if stars > 1000:
            return 0.1
        if stars > 100:
            return 0.05
        return 0.0

    def _score_citations(self, source: Source) -> float:
        citations = source.metadata.get("citations", 0)
        if citations > 10000:
            return 0.2
        if citations > 1000:
            return 0.15
        if citations > 100:
            return 0.1
        if citations > 10:
            return 0.05
        return 0.0

    def _score_venue(self, domain: str) -> float:
        for pattern, score in self.high_quality.items():
            if pattern in domain:
                return score
        for pattern, score in self.moderate_quality.items():
            if pattern in domain:
                return score
        if any(signal in domain for signal in self.low_quality_signals):
            return 0.0
        return 0.02

    def _score_recency(self, source: Source) -> float:
        published = source.metadata.get("published")
        if not published:
            return 0.03
        try:
            if isinstance(published, str):
                for fmt in ["%Y-%m-%d", "%Y-%m", "%Y"]:
                    try:
                        pub_date = datetime.strptime(published, fmt)
                        break
                    except ValueError:
                        continue
                else:
                    return 0.03
            else:
                pub_date = published

            age_days = (datetime.now() - pub_date).days
            age_years = age_days / 365

            if age_years < 1:
                return 0.1
            if age_years < 2:
                return 0.08
            if age_years < 3:
                return 0.05
            if age_years < 5:
                return 0.03
            return 0.0

        except Exception:
            return 0.03


def calculate_credibility(source: Source) -> float:
    """
    Convenience function: calculate source credibility score.

    Args:
        source: Source to score

    Returns:
        Credibility score (0.0 – 0.95)
    """
    scorer = CredibilityScorer()
    factors = scorer.score_source(source)
    return factors.total


def score_edge_weight(
    relation: Relation,
    source: Optional[Source] = None,
) -> float:
    """
    Convenience function: calculate edge weight.

    Args:
        relation: Relation to score
        source: Optional source for credibility context

    Returns:
        Edge weight (0.0 – 0.95)
    """
    scorer = CredibilityScorer()
    return scorer.score_edge(relation, from_source=source)
