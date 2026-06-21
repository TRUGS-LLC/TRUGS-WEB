"""Tier-B crawler-grade safety rails for the public trugs-web tool (AAA #2295 SP4).

A public, LLM-backed network crawler that strangers run against live sites and paid APIs needs
guard rails a local tool never does:

- secrets        — API keys read from the environment, never required inline, never logged.
- cost guard     — a budget ceiling on LLM calls/tokens so a crawl can't run up an unbounded bill.
- rate limit     — inter-request delay + exponential backoff on retryable HTTP status.
- logging        — a configured logger so failures are debuggable instead of silently swallowed.

robots.txt politeness lives in crawler.py (it needs the async HTTP client); the other rails are
here as standalone, unit-testable utilities.
"""

from __future__ import annotations

import logging
import os

__all__ = [
    "get_logger",
    "resolve_api_key",
    "CostGuard",
    "CostBudgetExceeded",
    "RETRYABLE_STATUS",
    "backoff_delay",
]

# --- logging -----------------------------------------------------------------
_LOGGER_NAME = "trugs_web"


def get_logger(name: str = _LOGGER_NAME) -> logging.Logger:
    """Return the package logger. The library does not configure handlers (that is the
    application's job); it just emits records so failures are visible, not swallowed."""
    return logging.getLogger(name)


# --- secrets -----------------------------------------------------------------
_ENV_KEYS = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}


def resolve_api_key(provider: str, explicit: str | None = None) -> str | None:
    """Resolve an LLM API key WITHOUT requiring it inline.

    Precedence: an explicit argument wins (back-compat), otherwise the provider's environment
    variable (ANTHROPIC_API_KEY / OPENAI_API_KEY). Returns None if neither is set. The key is
    never logged or echoed by this function.
    """
    if explicit:
        return explicit
    env_var = _ENV_KEYS.get((provider or "").lower())
    return os.environ.get(env_var) if env_var else None


# --- cost guard --------------------------------------------------------------
class CostBudgetExceeded(RuntimeError):
    """Raised when an LLM call would exceed the configured cost budget."""


class CostGuard:
    """A simple pre-flight budget ceiling for LLM usage.

    Call ``check()`` immediately BEFORE each LLM request; it accounts the (estimated) spend and
    raises ``CostBudgetExceeded`` if the call would push past ``max_calls`` or ``max_tokens``.
    With both limits ``None`` it is a no-op (default), so existing pipelines are unaffected.
    """

    def __init__(self, max_calls: int | None = None, max_tokens: int | None = None):
        self.max_calls = max_calls
        self.max_tokens = max_tokens
        self.calls = 0
        self.tokens = 0

    @staticmethod
    def estimate_tokens(text: str) -> int:
        return max(1, len(text or "") // 4)  # ~4 chars/token heuristic

    def check(self, prompt: str = "", max_tokens: int = 0) -> None:
        self.calls += 1
        self.tokens += self.estimate_tokens(prompt) + max(0, int(max_tokens))
        if self.max_calls is not None and self.calls > self.max_calls:
            raise CostBudgetExceeded(
                f"LLM call budget exceeded ({self.calls} > {self.max_calls})"
            )
        if self.max_tokens is not None and self.tokens > self.max_tokens:
            raise CostBudgetExceeded(
                f"LLM token budget exceeded (~{self.tokens} > {self.max_tokens})"
            )


# --- rate limit / backoff ----------------------------------------------------
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


def backoff_delay(attempt: int, base: float = 0.5, cap: float = 30.0) -> float:
    """Exponential backoff (seconds) for retry ``attempt`` (0-indexed), capped."""
    return min(cap, base * (2 ** max(0, attempt)))
