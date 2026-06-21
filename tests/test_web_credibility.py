"""Tests for trugs_web.credibility — Credibility scoring module."""

import pytest

from trugs_web.crawler import Source
from trugs_web.extractor import Relation
from trugs_web.credibility import (
    CredibilityFactors,
    CredibilityScorer,
    calculate_credibility,
    score_edge_weight,
)


class TestCredibilityFactors:
    def test_total_is_capped_at_095(self):
        factors = CredibilityFactors(
            peer_reviewed=0.3,
            author_credentials=0.2,
            citation_score=0.2,
            venue_quality=0.2,
            recency=0.1,
        )
        # Raw sum = 1.0, capped at 0.95
        assert factors.total == pytest.approx(0.95)

    def test_total_below_cap(self):
        factors = CredibilityFactors(peer_reviewed=0.2, venue_quality=0.1)
        assert factors.total == pytest.approx(0.3)

    def test_to_dict(self):
        factors = CredibilityFactors(peer_reviewed=0.3)
        d = factors.to_dict()
        assert "peer_reviewed" in d
        assert "total" in d
        assert d["total"] == pytest.approx(0.3)

    def test_cap_never_exceeds_095(self):
        # Even with all factors maxed out
        factors = CredibilityFactors(
            peer_reviewed=1.0,
            author_credentials=1.0,
            citation_score=1.0,
            venue_quality=1.0,
            recency=1.0,
        )
        assert factors.total <= 0.95


class TestCredibilityScorer:
    def test_academic_paper_high_score(self):
        scorer = CredibilityScorer()
        source = Source(
            url="https://nature.com/articles/paper123",
            source_type="PAPER",
            metadata={"citations": 500},
        )
        factors = scorer.score_source(source)
        assert factors.peer_reviewed > 0
        assert factors.venue_quality > 0
        assert factors.total > 0

    def test_arxiv_preprint_lower_than_nature(self):
        scorer = CredibilityScorer()
        nature_source = Source(url="https://nature.com/article", source_type="PAPER")
        arxiv_source = Source(url="https://arxiv.org/abs/123", source_type="PAPER")
        nature_factors = scorer.score_source(nature_source)
        arxiv_factors = scorer.score_source(arxiv_source)
        assert nature_factors.peer_reviewed > arxiv_factors.peer_reviewed

    def test_github_moderate_score(self):
        scorer = CredibilityScorer()
        source = Source(
            url="https://github.com/org/repo",
            source_type="PROJECT",
            metadata={"stars": 5000},
        )
        factors = scorer.score_source(source)
        assert factors.venue_quality > 0
        assert factors.total > 0

    def test_github_stars_boost_author(self):
        scorer = CredibilityScorer()
        low_star = Source(
            url="https://github.com/u/r", source_type="PROJECT", metadata={"stars": 5}
        )
        high_star = Source(
            url="https://github.com/u/r",
            source_type="PROJECT",
            metadata={"stars": 50000},
        )
        low_f = scorer.score_source(low_star)
        high_f = scorer.score_source(high_star)
        assert high_f.author_credentials >= low_f.author_credentials

    def test_low_quality_source(self):
        scorer = CredibilityScorer()
        source = Source(
            url="https://random-blog.wordpress.com/post",
            source_type="WEB_SOURCE",
        )
        factors = scorer.score_source(source)
        assert factors.total < 0.3

    def test_social_media_zero_venue(self):
        scorer = CredibilityScorer()
        source = Source(url="https://twitter.com/user/post", source_type="WEB_SOURCE")
        factors = scorer.score_source(source)
        assert factors.venue_quality == 0.0

    def test_citation_count_boosts_score(self):
        scorer = CredibilityScorer()
        high_cite = Source(
            url="https://example.com", source_type="PAPER", metadata={"citations": 5000}
        )
        low_cite = Source(
            url="https://example.com", source_type="PAPER", metadata={"citations": 1}
        )
        high_f = scorer.score_source(high_cite)
        low_f = scorer.score_source(low_cite)
        assert high_f.citation_score > low_f.citation_score

    def test_recency_recent_source(self):
        scorer = CredibilityScorer()
        from datetime import datetime

        this_year = datetime.now().strftime("%Y-%m-%d")
        source = Source(
            url="https://example.com",
            source_type="WEB_SOURCE",
            metadata={"published": this_year},
        )
        factors = scorer.score_source(source)
        assert factors.recency >= 0.1

    def test_recency_old_source(self):
        scorer = CredibilityScorer()
        source = Source(
            url="https://example.com",
            source_type="WEB_SOURCE",
            metadata={"published": "2010-01-01"},
        )
        factors = scorer.score_source(source)
        assert factors.recency == 0.0

    def test_recency_no_date(self):
        scorer = CredibilityScorer()
        source = Source(url="https://example.com", source_type="WEB_SOURCE")
        factors = scorer.score_source(source)
        assert factors.recency == pytest.approx(0.03)

    def test_recency_invalid_date(self):
        scorer = CredibilityScorer()
        source = Source(
            url="https://example.com",
            source_type="WEB_SOURCE",
            metadata={"published": "not-a-date"},
        )
        factors = scorer.score_source(source)
        assert factors.recency == pytest.approx(0.03)

    def test_high_h_index_boost(self):
        scorer = CredibilityScorer()
        source = Source(
            url="https://example.com",
            source_type="PAPER",
            metadata={"author": {"h_index": 60}},
        )
        factors = scorer.score_source(source)
        assert factors.author_credentials == pytest.approx(0.2)

    def test_documentation_peer_reviewed(self):
        scorer = CredibilityScorer()
        source = Source(url="https://docs.python.org/3/", source_type="DOCUMENTATION")
        factors = scorer.score_source(source)
        assert factors.peer_reviewed == pytest.approx(0.2)

    def test_score_edge_with_source(self):
        scorer = CredibilityScorer()
        relation = Relation(
            from_id="a", to_id="b", relation_type="CITES", confidence=0.8
        )
        source = Source(url="https://nature.com/article", source_type="PAPER")
        weight = scorer.score_edge(relation, from_source=source)
        assert 0 < weight <= 0.95

    def test_score_edge_without_source(self):
        scorer = CredibilityScorer()
        relation = Relation(
            from_id="a", to_id="b", relation_type="CITES", confidence=0.8
        )
        weight = scorer.score_edge(relation)
        assert weight > 0
        assert weight <= 0.95

    def test_score_edge_cap_at_095(self):
        scorer = CredibilityScorer()
        relation = Relation(
            from_id="a", to_id="b", relation_type="CITES", confidence=1.0
        )
        weight = scorer.score_edge(relation)
        assert weight <= 0.95

    def test_relation_type_multipliers(self):
        scorer = CredibilityScorer()
        cites = Relation(from_id="a", to_id="b", relation_type="CITES", confidence=0.9)
        weak = Relation(
            from_id="a", to_id="b", relation_type="RELATED_TO", confidence=0.9
        )
        assert scorer.score_edge(cites) >= scorer.score_edge(weak)

    def test_unknown_domain_small_venue_score(self):
        scorer = CredibilityScorer()
        source = Source(
            url="https://totally-unknown-domain-xyz.com/page", source_type="WEB_SOURCE"
        )
        factors = scorer.score_source(source)
        assert factors.venue_quality == pytest.approx(0.02)


def test_calculate_credibility():
    source = Source(
        url="https://arxiv.org/abs/2301.00001",
        source_type="PAPER",
        metadata={"citations": 200},
    )
    score = calculate_credibility(source)
    assert 0 < score <= 0.95


def test_score_edge_weight():
    relation = Relation(from_id="x", to_id="y", relation_type="USES", confidence=0.7)
    weight = score_edge_weight(relation)
    assert 0 < weight <= 0.95


def test_score_edge_weight_with_source():
    relation = Relation(from_id="x", to_id="y", relation_type="USES", confidence=0.7)
    source = Source(url="https://github.com/org/repo", source_type="PROJECT")
    weight = score_edge_weight(relation, source=source)
    assert 0 < weight <= 0.95
