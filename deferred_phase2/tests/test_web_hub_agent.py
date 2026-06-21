"""Tests for trugs_tools.web.hub.hub_agent."""

import json

import pytest

from trugs_tools.web.hub.hub_agent import (
    HubCandidate,
    HubAgent,
    _is_trug_url,
    _github_raw_url,
    _extract_trug_urls,
    _parse_trug_json,
    _find_root_node,
)
from trugs_tools.web.hub.qualifying_interest import QualifyingInterest


# ============================================================================
# Helper function tests
# ============================================================================

class TestIsTrugUrl:
    def test_folder_trug_json(self):
        assert _is_trug_url("https://example.com/folder.trug.json") is True

    def test_bare_trug_json(self):
        assert _is_trug_url("https://example.com/trug.json") is True

    def test_dot_trug_json(self):
        assert _is_trug_url("https://example.com/.trug.json") is True

    def test_non_trug_url(self):
        assert _is_trug_url("https://example.com/index.html") is False

    def test_trug_in_path(self):
        assert _is_trug_url("https://example.com/path/to/trug.json") is True


class TestGithubRawUrl:
    def test_basic_repo(self):
        url = _github_raw_url("https://github.com/user/repo")
        assert url == "https://raw.githubusercontent.com/user/repo/main/folder.trug.json"

    def test_custom_path(self):
        url = _github_raw_url("https://github.com/user/repo", path="data/graph.trug.json")
        assert "data/graph.trug.json" in url

    def test_custom_branch(self):
        url = _github_raw_url("https://github.com/user/repo", branch="develop")
        assert "/develop/" in url

    def test_invalid_repo(self):
        url = _github_raw_url("https://github.com/user")
        assert url == ""


class TestExtractTrugUrls:
    def test_href_links(self):
        html = '<a href="https://example.com/folder.trug.json">TRUG</a>'
        urls = _extract_trug_urls(html, "https://example.com")
        assert len(urls) == 1
        assert urls[0] == "https://example.com/folder.trug.json"

    def test_relative_links(self):
        html = '<a href="/data/trug.json">TRUG</a>'
        urls = _extract_trug_urls(html, "https://example.com")
        assert len(urls) == 1
        assert "example.com" in urls[0]

    def test_bare_url_in_text(self):
        text = "Check out https://example.com/data.trug.json for more info."
        urls = _extract_trug_urls(text, "https://example.com")
        assert len(urls) >= 1

    def test_no_trug_links(self):
        html = '<a href="https://example.com/index.html">Home</a>'
        urls = _extract_trug_urls(html, "https://example.com")
        assert len(urls) == 0


class TestParseTrugJson:
    def test_valid_trug(self):
        data = {"name": "test", "nodes": [], "edges": []}
        result = _parse_trug_json(json.dumps(data))
        assert result is not None
        assert result["name"] == "test"

    def test_invalid_json(self):
        assert _parse_trug_json("not json") is None

    def test_no_nodes(self):
        data = {"name": "test"}
        assert _parse_trug_json(json.dumps(data)) is None

    def test_non_dict(self):
        assert _parse_trug_json(json.dumps([1, 2, 3])) is None


class TestFindRootNode:
    def test_root_by_parent_id_none(self):
        graph = {
            "nodes": [
                {"id": "child", "parent_id": "root"},
                {"id": "root", "parent_id": None},
            ]
        }
        root = _find_root_node(graph)
        assert root["id"] == "root"

    def test_no_parent_id_field(self):
        graph = {"nodes": [{"id": "only"}]}
        root = _find_root_node(graph)
        assert root["id"] == "only"

    def test_empty_nodes(self):
        assert _find_root_node({"nodes": []}) is None

    def test_fallback_first_node(self):
        graph = {
            "nodes": [
                {"id": "a", "parent_id": "b"},
                {"id": "b", "parent_id": "a"},
            ]
        }
        root = _find_root_node(graph)
        assert root["id"] == "a"


# ============================================================================
# HubCandidate dataclass
# ============================================================================

class TestHubCandidate:
    def test_default_values(self):
        c = HubCandidate()
        assert c.url == ""
        assert c.graph_data is None
        assert c.tier2_score == 0.0
        assert c.tier3_score is None
        assert c.final_score == 0.0

    def test_with_data(self):
        c = HubCandidate(
            url="https://example.com/trug.json",
            graph_data={"nodes": []},
            tier2_score=0.8,
        )
        assert c.url == "https://example.com/trug.json"
        assert c.graph_data is not None


# ============================================================================
# HubAgent — Tier 2 (graph compute)
# ============================================================================

def _make_trug_graph(name, keywords, domain="", topic=""):
    """Helper to create a minimal TRUG graph dict with qualifying_interest."""
    return {
        "name": name,
        "nodes": [
            {
                "id": f"root_{name}",
                "type": "RESEARCH_GRAPH",
                "parent_id": None,
                "properties": {
                    "name": name,
                    "topic": topic or name,
                    "qualifying_interest": {
                        "keywords": keywords,
                        "domain": domain,
                    },
                },
            }
        ],
        "edges": [],
    }


def _make_trug_graph_no_qi(name, topic=""):
    """Helper to create a TRUG graph WITHOUT qualifying_interest."""
    return {
        "name": name,
        "nodes": [
            {
                "id": f"root_{name}",
                "type": "RESEARCH_GRAPH",
                "parent_id": None,
                "properties": {
                    "name": name,
                    "topic": topic or name,
                    "description": f"A graph about {topic or name}",
                },
            }
        ],
        "edges": [],
    }


class TestHubAgentTier2:
    def test_evaluate_with_matching_qi(self):
        interest = QualifyingInterest(keywords=["machine learning"], domain="ai")
        agent = HubAgent(interest=interest)
        candidates = [
            HubCandidate(
                url="a",
                graph_data=_make_trug_graph("ml", ["machine learning"], domain="ai"),
            ),
        ]
        agent.evaluate_tier2(candidates)
        assert candidates[0].tier2_score > 0.5
        assert candidates[0].qualifying_interest is not None

    def test_evaluate_with_non_matching_qi(self):
        interest = QualifyingInterest(keywords=["machine learning"])
        agent = HubAgent(interest=interest)
        candidates = [
            HubCandidate(
                url="b",
                graph_data=_make_trug_graph("cooking", ["recipes", "food"]),
            ),
        ]
        agent.evaluate_tier2(candidates)
        assert candidates[0].tier2_score < 0.3

    def test_evaluate_without_qi_uses_fallback(self):
        interest = QualifyingInterest(keywords=["machine learning"])
        agent = HubAgent(interest=interest)
        candidates = [
            HubCandidate(
                url="c",
                graph_data=_make_trug_graph_no_qi("ml_graph", topic="machine learning"),
            ),
        ]
        agent.evaluate_tier2(candidates)
        # Fallback should find "machine learning" in topic
        assert candidates[0].tier2_score > 0.0

    def test_evaluate_no_graph_data(self):
        interest = QualifyingInterest(keywords=["test"])
        agent = HubAgent(interest=interest)
        candidates = [HubCandidate(url="d", graph_data=None)]
        agent.evaluate_tier2(candidates)
        assert candidates[0].tier2_score == 0.0

    def test_evaluate_empty_graph(self):
        interest = QualifyingInterest(keywords=["test"])
        agent = HubAgent(interest=interest)
        candidates = [HubCandidate(url="e", graph_data={"nodes": []})]
        agent.evaluate_tier2(candidates)
        assert candidates[0].tier2_score == 0.0

    def test_fallback_no_keyword_match(self):
        interest = QualifyingInterest(keywords=["quantum computing"])
        agent = HubAgent(interest=interest)
        candidates = [
            HubCandidate(
                url="f",
                graph_data=_make_trug_graph_no_qi("cooking", topic="recipes"),
            ),
        ]
        agent.evaluate_tier2(candidates)
        assert candidates[0].tier2_score == 0.0


class TestHubAgentDiscoverFromGraphs:
    def test_from_graph_dicts(self):
        interest = QualifyingInterest(keywords=["ml"])
        agent = HubAgent(interest=interest)
        graphs = [
            ("graph_a", {"nodes": [{"id": "r"}], "edges": []}),
            ("graph_b", {"nodes": [{"id": "r2"}], "edges": []}),
        ]
        candidates = agent.discover_from_graphs(graphs)
        assert len(candidates) == 2
        assert candidates[0].url == "graph_a"

    def test_filters_invalid_graphs(self):
        interest = QualifyingInterest(keywords=["test"])
        agent = HubAgent(interest=interest)
        graphs = [
            ("good", {"nodes": [], "edges": []}),
            ("bad", {"not_a_graph": True}),
            ("also_bad", "string"),
        ]
        candidates = agent.discover_from_graphs(graphs)
        assert len(candidates) == 1

    def test_max_candidates_limit(self):
        interest = QualifyingInterest(keywords=["test"])
        agent = HubAgent(interest=interest, max_candidates=2)
        graphs = [
            (f"g{i}", {"nodes": [], "edges": []}) for i in range(10)
        ]
        candidates = agent.discover_from_graphs(graphs)
        assert len(candidates) == 2


class TestHubAgentRank:
    def test_rank_filters_by_min_relevance(self):
        interest = QualifyingInterest(keywords=["test"])
        agent = HubAgent(interest=interest, min_relevance=0.5)
        candidates = [
            HubCandidate(url="a", final_score=0.8),
            HubCandidate(url="b", final_score=0.3),
            HubCandidate(url="c", final_score=0.6),
        ]
        ranked = agent.rank(candidates)
        assert len(ranked) == 2
        assert ranked[0].url == "a"
        assert ranked[1].url == "c"

    def test_rank_empty(self):
        interest = QualifyingInterest(keywords=["test"])
        agent = HubAgent(interest=interest)
        assert agent.rank([]) == []


# ============================================================================
# HubAgent — Tier 3 (LLM, async)
# ============================================================================

class MockLLMForHub:
    """Mock LLM client that returns a score."""

    async def complete(self, prompt, max_tokens=50):
        return "0.75"


class MockLLMBadResponse:
    """Mock LLM client that returns non-numeric text."""

    async def complete(self, prompt, max_tokens=50):
        return "I think this is very relevant!"


class MockLLMError:
    """Mock LLM client that raises an exception."""

    async def complete(self, prompt, max_tokens=50):
        raise RuntimeError("LLM failed")


class TestHubAgentTier3:
    @pytest.mark.asyncio
    async def test_tier3_evaluates_ambiguous(self):
        interest = QualifyingInterest(keywords=["ml"])
        agent = HubAgent(
            interest=interest,
            llm_client=MockLLMForHub(),
            ambiguous_low=0.2,
            ambiguous_high=0.6,
        )
        candidates = [
            HubCandidate(
                url="a",
                graph_data=_make_trug_graph("x", ["ml"]),
                tier2_score=0.4,  # in ambiguous range
                final_score=0.4,
            ),
        ]
        await agent.evaluate_tier3(candidates)
        assert candidates[0].tier3_score == 0.75
        # Blended: 0.5*0.4 + 0.5*0.75 = 0.575
        assert abs(candidates[0].final_score - 0.575) < 0.01

    @pytest.mark.asyncio
    async def test_tier3_skips_high_score(self):
        interest = QualifyingInterest(keywords=["ml"])
        agent = HubAgent(
            interest=interest,
            llm_client=MockLLMForHub(),
            ambiguous_high=0.6,
        )
        candidates = [
            HubCandidate(url="a", tier2_score=0.9, final_score=0.9),
        ]
        await agent.evaluate_tier3(candidates)
        assert candidates[0].tier3_score is None  # Not evaluated

    @pytest.mark.asyncio
    async def test_tier3_skips_low_score(self):
        interest = QualifyingInterest(keywords=["ml"])
        agent = HubAgent(
            interest=interest,
            llm_client=MockLLMForHub(),
            ambiguous_low=0.2,
        )
        candidates = [
            HubCandidate(url="a", tier2_score=0.1, final_score=0.1),
        ]
        await agent.evaluate_tier3(candidates)
        assert candidates[0].tier3_score is None

    @pytest.mark.asyncio
    async def test_tier3_no_llm_client(self):
        interest = QualifyingInterest(keywords=["ml"])
        agent = HubAgent(interest=interest)  # no llm_client
        candidates = [
            HubCandidate(url="a", tier2_score=0.4, final_score=0.4),
        ]
        await agent.evaluate_tier3(candidates)
        assert candidates[0].tier3_score is None

    @pytest.mark.asyncio
    async def test_tier3_bad_response(self):
        interest = QualifyingInterest(keywords=["ml"])
        agent = HubAgent(
            interest=interest,
            llm_client=MockLLMBadResponse(),
            ambiguous_low=0.2,
            ambiguous_high=0.6,
        )
        candidates = [
            HubCandidate(
                url="a",
                graph_data=_make_trug_graph("x", ["ml"]),
                tier2_score=0.4,
                final_score=0.4,
            ),
        ]
        await agent.evaluate_tier3(candidates)
        assert candidates[0].tier3_score is None  # Couldn't parse

    @pytest.mark.asyncio
    async def test_tier3_llm_error(self):
        interest = QualifyingInterest(keywords=["ml"])
        agent = HubAgent(
            interest=interest,
            llm_client=MockLLMError(),
            ambiguous_low=0.2,
            ambiguous_high=0.6,
        )
        candidates = [
            HubCandidate(
                url="a",
                graph_data=_make_trug_graph("x", ["ml"]),
                tier2_score=0.4,
                final_score=0.4,
            ),
        ]
        await agent.evaluate_tier3(candidates)
        assert candidates[0].tier3_score is None


# ============================================================================
# HubAgent — full pipeline (async)
# ============================================================================

class TestHubAgentFullPipeline:
    @pytest.mark.asyncio
    async def test_discover_from_graphs_and_rank(self):
        """End-to-end: load → evaluate Tier 2 → rank."""
        interest = QualifyingInterest(keywords=["machine learning"], domain="ai")
        agent = HubAgent(interest=interest, min_relevance=0.0)

        graphs = [
            ("ml", _make_trug_graph("ml", ["machine learning"], domain="ai")),
            ("bio", _make_trug_graph("bio", ["biology"], domain="science")),
            ("dl", _make_trug_graph("dl", ["deep learning"], domain="ai")),
        ]
        candidates = agent.discover_from_graphs(graphs)
        agent.evaluate_tier2(candidates)
        ranked = agent.rank(candidates)

        assert len(ranked) >= 1
        # ML should rank highest
        assert ranked[0].url == "ml"
