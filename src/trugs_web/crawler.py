"""
Source Discovery Module

Discovers sources for a given topic using web scraping and link extraction.
Uses async HTTP (httpx + asyncio) — no LLM required for discovery.

Requires: pip install trugs-tools[web]
"""

import asyncio
import re
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urljoin, urlparse

from ._safety import RETRYABLE_STATUS, backoff_delay, get_logger

logger = get_logger()


@dataclass
class Source:
    """A discovered web source."""

    url: str
    title: str = ""
    description: str = ""
    source_type: str = (
        "WEB_SOURCE"  # WEB_SOURCE, PAPER, PROJECT, DOCUMENTATION, ARTICLE
    )
    content: str = ""
    outbound_links: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    @property
    def domain(self) -> str:
        """Extract domain from URL."""
        return urlparse(self.url).netloc

    @property
    def is_academic(self) -> bool:
        """Check if source is likely academic."""
        academic_domains = [
            "arxiv.org",
            "scholar.google",
            "pubmed",
            "doi.org",
            "nature.com",
            "science.org",
            "ieee.org",
            "acm.org",
            "springer.com",
            "wiley.com",
            "elsevier.com",
        ]
        return any(d in self.domain for d in academic_domains)

    @property
    def is_github(self) -> bool:
        """Check if source is a GitHub repo."""
        return self.domain == "github.com" or self.domain.endswith(".github.com")


class SourceDiscoverer:
    """
    Discovers sources starting from seed URLs.

    Uses async HTTP scraping (no LLM) to find and categorize sources. Tier-B safety rails
    (AAA #2295 SP4): robots.txt politeness (fail-open), an inter-request delay, and
    exponential backoff on retryable HTTP status — all opt-in via the constructor so default
    construction is unchanged.
    """

    def __init__(
        self,
        max_sources: int = 50,
        max_depth: int = 2,
        timeout: float = 10.0,
        user_agent: str = "TRUGSWebCrawler/1.0 (research bot)",
        request_delay: float = 0.0,
        respect_robots: bool = True,
        max_retries: int = 2,
    ):
        self.max_sources = max_sources
        self.max_depth = max_depth
        self.timeout = timeout
        self.user_agent = user_agent
        self.request_delay = request_delay
        self.respect_robots = respect_robots
        self.max_retries = max_retries
        self._seen_urls: set = set()
        self._robots_cache: dict = {}

    async def _can_fetch(self, client, url: str) -> bool:
        """robots.txt politeness, cached per host. **Fail-open**: if robots.txt cannot be
        fetched or parsed, allow the fetch — we never block on infrastructure errors."""
        from urllib.parse import urlparse
        from urllib.robotparser import RobotFileParser

        parts = urlparse(url)
        host = f"{parts.scheme}://{parts.netloc}"
        rp = self._robots_cache.get(host)
        if rp is None:
            rp = RobotFileParser()
            try:
                resp = await client.get(f"{host}/robots.txt")
                if resp.status_code == 200:
                    rp.parse(resp.text.splitlines())
                else:
                    rp.allow_all = True  # type: ignore[attr-defined]
            except Exception as exc:  # network/mocking error → fail-open
                logger.debug("robots.txt unavailable for %s (%s) — allowing", host, exc)
                rp.allow_all = True  # type: ignore[attr-defined]
            self._robots_cache[host] = rp
        try:
            return rp.can_fetch(self.user_agent, url)
        except Exception:
            return True

    async def discover(
        self,
        seed_urls: list,
        topic: str = "",
    ) -> list:
        """
        Discover sources starting from seed URLs.

        Args:
            seed_urls: Starting URLs to crawl
            topic: Optional topic hint for context

        Returns:
            List of discovered Source objects
        """
        try:
            import httpx
        except ImportError as exc:
            raise ImportError(
                "httpx is required for web crawling. "
                "Install with: pip install trugs-tools[web]"
            ) from exc

        sources: list = []
        to_visit: list = [(url, 0) for url in seed_urls]

        async with httpx.AsyncClient(
            timeout=self.timeout,
            headers={"User-Agent": self.user_agent},
            follow_redirects=True,
        ) as client:
            while to_visit and len(sources) < self.max_sources:
                batch: list[tuple[str, int]] = []
                while to_visit and len(batch) < 10:
                    url, depth = to_visit.pop(0)
                    if url not in self._seen_urls:
                        self._seen_urls.add(url)
                        batch.append((url, depth))

                if not batch:
                    break

                # Tier-B: robots.txt politeness + inter-request delay (both opt-in)
                allowed = []
                for url, depth in batch:
                    if self.respect_robots and not await self._can_fetch(client, url):
                        logger.info("robots.txt disallows %s — skipping", url)
                        continue
                    allowed.append((url, depth))
                    if self.request_delay:
                        await asyncio.sleep(self.request_delay)

                tasks = [
                    self._fetch_source(client, url, depth) for url, depth in allowed
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                for result in results:
                    if isinstance(result, Source):
                        sources.append(result)

                        if result.metadata.get("depth", 0) < self.max_depth:
                            for link in result.outbound_links[:10]:
                                if link not in self._seen_urls:
                                    to_visit.append(
                                        (link, result.metadata["depth"] + 1)
                                    )

        return sources

    async def _fetch_source(
        self,
        client,
        url: str,
        depth: int,
    ) -> Optional[Source]:
        """Fetch and parse a single source."""
        try:
            from bs4 import BeautifulSoup
        except ImportError as exc:
            raise ImportError(
                "beautifulsoup4 is required for web crawling. "
                "Install with: pip install trugs-tools[web]"
            ) from exc

        try:
            response = None
            for attempt in range(self.max_retries + 1):
                response = await client.get(url)
                if (
                    response.status_code in RETRYABLE_STATUS
                    and attempt < self.max_retries
                ):
                    logger.info(
                        "retryable HTTP %s for %s (attempt %d/%d) — backing off",
                        response.status_code,
                        url,
                        attempt + 1,
                        self.max_retries,
                    )
                    await asyncio.sleep(backoff_delay(attempt))
                    continue
                break
            assert response is not None  # loop runs ≥1 time (max_retries + 1 ≥ 1)
            response.raise_for_status()

            content_type = response.headers.get("content-type", "")
            if "text/html" not in content_type:
                return None

            html = response.text
            soup = BeautifulSoup(html, "html.parser")

            title = ""
            if soup.title:
                title = soup.title.string or ""

            description = ""
            meta_desc = soup.find("meta", attrs={"name": "description"})
            if meta_desc:
                content_val = meta_desc.get("content", "")
                description = content_val if isinstance(content_val, str) else ""

            content = self._extract_content(soup)
            links = self._extract_links(soup, url)
            source_type = self._classify_source(url, soup)

            return Source(
                url=url,
                title=title.strip(),
                description=description.strip(),
                source_type=source_type,
                content=content,
                outbound_links=links,
                metadata={
                    "depth": depth,
                    "content_length": len(content),
                },
            )

        except Exception as exc:
            logger.warning("fetch failed for %s: %s", url, exc)
            return None

    def _extract_content(self, soup) -> str:
        """Extract main text content from HTML."""
        for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
            tag.decompose()

        text = soup.get_text(separator="\n", strip=True)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        text = "\n".join(lines)
        return text[:10000]

    def _extract_links(self, soup, base_url: str) -> list:
        """Extract and normalize outbound links."""
        links = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith(("#", "javascript:", "mailto:")):
                continue
            full_url = urljoin(base_url, href)
            if full_url.startswith(("http://", "https://")):
                links.append(full_url)
        return list(set(links))

    def _classify_source(self, url: str, soup) -> str:
        """Classify source type based on URL and content."""
        domain = urlparse(url).netloc

        if any(d in domain for d in ["arxiv.org", "doi.org", "pubmed"]):
            return "PAPER"

        if domain == "github.com" or domain.endswith(".github.com"):
            path = urlparse(url).path
            if re.match(r"^/[^/]+/[^/]+/?$", path):
                return "PROJECT"

        if any(d in domain for d in ["readthedocs", "docs.", "documentation"]):
            return "DOCUMENTATION"

        if any(d in domain for d in ["medium.com", "blog.", "news."]):
            return "ARTICLE"

        return "WEB_SOURCE"


async def discover_sources(
    seed_urls: list,
    topic: str = "",
    max_sources: int = 50,
) -> list:
    """
    Convenience function to discover sources.

    Args:
        seed_urls: Starting URLs
        topic: Research topic hint
        max_sources: Maximum sources to discover

    Returns:
        List of Source objects
    """
    discoverer = SourceDiscoverer(max_sources=max_sources)
    return await discoverer.discover(seed_urls, topic)
