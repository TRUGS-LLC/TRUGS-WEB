"""Tier-B crawler-grade safety rails (AAA #2295 SP4).

Marked tests so the Phase-8 vacuity-guarded recipes (SC-6 robots/rate_limit, SC-7 cost,
SC-8 secret, SC-9 logging) and PC-6 resolve to real, passing tests.
"""

import asyncio

import httpx
import pytest
import respx

from trugs_web._safety import (
    RETRYABLE_STATUS,
    CostBudgetExceeded,
    CostGuard,
    backoff_delay,
    resolve_api_key,
)
from trugs_web.crawler import Source, SourceDiscoverer
from trugs_web.extractor import EntityExtractor, create_extractor


# --- secrets: API keys from the environment, never required inline ----------------------------
@pytest.mark.secret
def test_resolve_api_key_precedence(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert resolve_api_key("anthropic") is None
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-from-env")
    assert resolve_api_key("anthropic") == "sk-from-env"
    assert resolve_api_key("anthropic", "sk-explicit") == "sk-explicit"  # explicit wins


@pytest.mark.secret
def test_create_extractor_uses_env_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-from-env")
    ent, rel = create_extractor("anthropic")  # no inline key — read from env
    assert ent is not None and rel is not None
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ValueError) as ei:
        create_extractor("anthropic")  # neither inline nor env
    assert "ANTHROPIC_API_KEY" in str(ei.value)  # tells the user how to supply it


# --- cost guard: a budget ceiling on LLM usage -----------------------------------------------
@pytest.mark.cost
def test_cost_guard_call_budget():
    g = CostGuard(max_calls=2)
    g.check("a")
    g.check("b")
    with pytest.raises(CostBudgetExceeded):
        g.check("c")


@pytest.mark.cost
def test_cost_guard_token_budget():
    g = CostGuard(max_tokens=10)
    with pytest.raises(CostBudgetExceeded):
        g.check("x" * 100, max_tokens=50)


@pytest.mark.cost
def test_cost_guard_noop_by_default():
    g = CostGuard()
    for _ in range(50):
        g.check("anything")  # no limits configured → never raises


# --- rate limit / backoff --------------------------------------------------------------------
@pytest.mark.rate_limit
def test_backoff_monotonic_and_capped():
    assert backoff_delay(0) < backoff_delay(1) < backoff_delay(2)
    assert backoff_delay(100) <= 30.0
    assert 429 in RETRYABLE_STATUS and 503 in RETRYABLE_STATUS


@pytest.mark.rate_limit
@pytest.mark.asyncio
@respx.mock
async def test_crawler_retries_then_succeeds(monkeypatch):
    monkeypatch.setattr(
        "trugs_web.crawler.backoff_delay", lambda *a, **k: 0.0
    )  # no real sleep
    url = "https://ex.com/page"
    route = respx.get(url).mock(
        side_effect=[
            httpx.Response(503),
            httpx.Response(
                200,
                text="<html><title>OK</title><body>hello</body></html>",
                headers={"content-type": "text/html"},
            ),
        ]
    )
    d = SourceDiscoverer(respect_robots=False, max_retries=2)
    async with httpx.AsyncClient() as client:
        src = await d._fetch_source(client, url, 0)
    assert route.call_count == 2  # retried the 503 once, then succeeded
    assert src is not None and src.title == "OK"


# --- robots.txt politeness (fail-open) -------------------------------------------------------
@pytest.mark.robots
@pytest.mark.asyncio
@respx.mock
async def test_robots_disallow_blocks_path():
    respx.get("https://ex.com/robots.txt").mock(
        return_value=httpx.Response(200, text="User-agent: *\nDisallow: /private")
    )
    d = SourceDiscoverer()
    async with httpx.AsyncClient() as client:
        assert await d._can_fetch(client, "https://ex.com/private/x") is False
        assert await d._can_fetch(client, "https://ex.com/public/y") is True


@pytest.mark.robots
@pytest.mark.asyncio
@respx.mock
async def test_robots_fail_open_when_unavailable():
    respx.get("https://ex.com/robots.txt").mock(return_value=httpx.Response(404))
    d = SourceDiscoverer()
    async with httpx.AsyncClient() as client:
        assert await d._can_fetch(client, "https://ex.com/anything") is True


# --- structured logging instead of silent swallows -------------------------------------------
@pytest.mark.logging
def test_extractor_logs_swallowed_failure(caplog):
    class BoomClient:
        async def complete(self, prompt, max_tokens=1000):
            raise RuntimeError("boom")

    ent = EntityExtractor(BoomClient())
    with caplog.at_level("WARNING", logger="trugs_web"):
        result = asyncio.run(
            ent.extract(Source(url="https://ex.com/x", content="some text"))
        )
    assert result == []  # still returns a safe default (behavior unchanged)
    assert any(
        "extraction failed" in r.getMessage() for r in caplog.records
    )  # but now logged
