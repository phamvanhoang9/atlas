"""Web search via the Tavily API, with a DuckDuckGo fallback and SQLite cache.

`TavilySearch` queries Tavily (biased toward academic/primary-source
domains via include/exclude domain lists) and transparently falls back to
DuckDuckGo if the Tavily request fails. Results are cached in a
`SQLiteTTLCache` keyed on query/max_results/provider when caching is
enabled.
"""

import logging
import os
from typing import Any

from ddgs import DDGS
from tavily import TavilyClient
from tavily.exceptions import TavilyError

from src.storage import SQLiteTTLCache


logger = logging.getLogger(__name__)


_DEFAULT_INCLUDE_DOMAINS = [
    "arxiv.org",
    "openreview.net",
    "huggingface.co",
    "scholar.google.com",
    "proceedings.neurips.cc",
    "proceedings.mlr.press",
    "openaccess.thecvf.com",
    "aclanthology.org",
    "aaai.org",
    "ieee.org",
    "acm.org",
    "springer.com",
    "nature.com",
    "science.org",
]

_DEFAULT_EXCLUDE_DOMAINS = [
    "medium.com",
    "substack.com",
    "viblo.asia",
    "hr1tech.com",
    "fpt.ai",
    "fpt.com",
    "youtube.com",
    "reddit.com",
    "linkedin.com",
    "facebook.com",
    "twitter.com",
]


class TavilySearch:
    """
    Tavily API retriever with DuckDuckGo fallback and result caching.
    """

    def __init__(
        self,
        query: str,
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
    ) -> None:
        """
        Initialize the TavilySearch object.

        Args:
          query: The search query string.
          include_domains: Domains to bias results toward. Defaults to a
            list of academic/primary-source domains (arXiv, ACM, IEEE,
            etc.) when not provided.
          exclude_domains: Domains to exclude from results. Defaults to a
            list of low-signal/social domains (Medium, Reddit, etc.) when
            not provided.
        """
        self.query = query
        self.include_domains = include_domains if include_domains is not None else _DEFAULT_INCLUDE_DOMAINS
        self.exclude_domains = exclude_domains if exclude_domains is not None else _DEFAULT_EXCLUDE_DOMAINS
        self.api_key = self.get_api_key()
        self.client = TavilyClient(self.api_key)
        self.cache_enabled = os.getenv("ENABLE_SEARCH_CACHE", "true").lower() == "true"
        self.cache_ttl_seconds = int(os.getenv("SEARCH_CACHE_TTL_SECONDS", "86400"))
        self.cache = SQLiteTTLCache.from_env() if self.cache_enabled else None

    def get_api_key(self) -> str:
        """
        Gets the Tavily API key.

        Returns:
          The value of the `TAVILY_API_KEY` environment variable.

        Raises:
          RuntimeError: If `TAVILY_API_KEY` is not set.
        """
        try:
            return os.environ["TAVILY_API_KEY"]
        except KeyError as exc:
            raise RuntimeError(
                "Tavily API key not found. Please set the TAVILY_API_KEY environment variable. "
                "You can get a key at https://app.tavily.com"
            ) from exc

    def search(self, max_results: int = 7) -> list[dict[str, Any]]:
        """
        Searches the query, with cache lookup and DuckDuckGo fallback.

        Checks the SQLite cache first (if enabled). On a miss, queries
        Tavily; if Tavily raises an error, falls back to a DuckDuckGo text
        search instead. Successful results are written back to the cache.

        Args:
          max_results: The maximum number of results to return.

        Returns:
          A list of result dicts. Tavily results are normalized to
          `{"href": str, "body": str}`; DuckDuckGo fallback results keep
          the `ddgs` library's native shape.
        """
        cache_key = None
        if self.cache is not None:
            cache_key = self.cache.make_key(
                {
                    "query": self.query,
                    "max_results": max_results,
                    "provider": "tavily",
                    "version": 1,
                }
            )
            cached = self.cache.get("search_results", cache_key)
            if cached is not None:
                logger.info("Search cache hit for query=%s", self.query)
                return list(cached)

        try:
            results = self.client.search(
                self.query,
                search_depth="advanced",
                max_results=max_results,
                include_domains=self.include_domains,
                exclude_domains=self.exclude_domains,
            )
            search_response = [
                {"href": obj["url"], "body": obj["content"]}
                for obj in results.get("results", [])
            ]
        except (TavilyError, RuntimeError, ValueError, OSError) as exc:
            logger.warning("Tavily search failed: %s, falling back to DuckDuckGo", exc)
            ddg = DDGS()
            search_response = ddg.text(self.query, region="wt-wt", max_results=max_results)

        search_response = list(search_response)
        if self.cache is not None and cache_key is not None:
            self.cache.set("search_results", cache_key, search_response, self.cache_ttl_seconds)

        return search_response
