from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml

from core.search.base import SearchHit, SearchProvider
from core.search.canonical import normalize_canonical_url, reciprocal_rank_fusion
from core.search.providers.searxng import SearxngProvider
from core.search.providers.forums import HackerNewsProvider, RedditProvider, StackExchangeProvider
from core.search.providers.code import GitHubSearchProvider
from core.search.providers.academic import ArxivProvider, OpenAlexProvider, WikipediaProvider
from core.search.providers.video import YouTubeSearchProvider
from core.search.providers.social import BlueskyProvider, MastodonProvider
from core.search.providers.app_stores import AppleAppStoreProvider, GooglePlayProvider
from core.search.providers.archives import WaybackCdxProvider, MarginaliaProvider
from core.search.providers.duckduckgo import DuckDuckGoProvider
from core.search.providers.tavily_exa import TavilySearchAdapter, ExaSearchAdapter
from core.observability.tracing import trace_agent


class SearchRouter:
    """
    Central search router selecting provider sets by source family, executing concurrently,
    fusing with Reciprocal Rank Fusion, canonicalizing URLs, deduplicating with SimHash,
    and handling fallback to Tavily/Exa if primary returns too few hits.
    """

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or os.path.join("config", "search.yaml")
        self._config = self._load_config()
        self._providers: Dict[str, SearchProvider] = {}
        self._family_map: Dict[str, List[str]] = {}
        self._initialize_providers()

    def _load_config(self) -> Dict[str, Any]:
        p = Path(self.config_path)
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
            except Exception:
                pass
        return {}

    def _initialize_providers(self):
        searxng_cfg = self._config.get("searxng", {})
        searxng_url = searxng_cfg.get("url") or os.environ.get("SEARXNG_URL", "http://localhost:8080")

        # Register instances
        self._providers["searxng"] = SearxngProvider(base_url=searxng_url)
        self._providers["duckduckgo"] = DuckDuckGoProvider()
        self._providers["hacker_news"] = HackerNewsProvider()
        self._providers["reddit"] = RedditProvider()
        self._providers["stack_exchange"] = StackExchangeProvider()
        self._providers["github"] = GitHubSearchProvider()
        self._providers["arxiv"] = ArxivProvider()
        self._providers["openalex"] = OpenAlexProvider()
        self._providers["wikipedia"] = WikipediaProvider()
        self._providers["youtube"] = YouTubeSearchProvider()
        self._providers["bluesky"] = BlueskyProvider()
        self._providers["mastodon"] = MastodonProvider()
        self._providers["apple_app_store"] = AppleAppStoreProvider()
        self._providers["google_play"] = GooglePlayProvider()
        self._providers["wayback_cdx"] = WaybackCdxProvider()
        self._providers["marginalia"] = MarginaliaProvider()
        self._providers["tavily"] = TavilySearchAdapter()
        self._providers["exa"] = ExaSearchAdapter()

        # Map source_family -> provider names
        self._family_map = {
            "web_general": ["searxng", "duckduckgo"],
            "news": ["searxng"],
            "forums": ["reddit", "hacker_news", "stack_exchange"],
            "code": ["github", "stack_exchange"],
            "academic": ["arxiv", "openalex", "wikipedia"],
            "video": ["youtube"],
            "social": ["bluesky", "mastodon"],
            "app_stores": ["apple_app_store", "google_play"],
            "archives": ["wayback_cdx", "marginalia"],
            "web_index": ["web_index"],
        }

    def register_provider(self, name: str, provider: SearchProvider):
        """Allows dynamic registration of contextual providers like tenant WebIndexProvider."""
        self._providers[name] = provider

    @trace_agent("search_router")
    async def search(
        self,
        query: str,
        *,
        source_family: str = "web_general",
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[SearchHit]:
        """
        Executes concurrent search across all providers mapped to source_family,
        fuses results with RRF, and deduplicates canonical URLs.
        """
        provider_names = self._family_map.get(source_family, ["searxng", "duckduckgo"])
        tasks = []
        for name in provider_names:
            provider = self._providers.get(name)
            if provider:
                tasks.append(self._safe_search(provider, query, limit=limit, filters=filters))

        if not tasks:
            tasks.append(self._safe_search(self._providers["searxng"], query, limit=limit, filters=filters))

        # Run concurrently
        results_lists: List[List[SearchHit]] = await asyncio.gather(*tasks)

        # Apply Reciprocal Rank Fusion & Deduplication
        fused_hits = reciprocal_rank_fusion(results_lists, k=60)

        # Fallback check: if primary returned too few results (< 2), query fallback providers if enabled
        min_threshold = self._config.get("routing", {}).get("min_hits_threshold", 2)
        if len(fused_hits) < min_threshold:
            fallback_cfg = self._config.get("providers", {}).get("tavily", {})
            if fallback_cfg.get("enabled", False) or os.environ.get("TAVILY_API_KEY"):
                tavily_provider = self._providers.get("tavily")
                if tavily_provider:
                    fallback_hits = await self._safe_search(tavily_provider, query, limit=limit)
                    for hit in fallback_hits:
                        hit.is_fallback = True
                        hit.fallback_reason = "SearXNG/primary returned fewer than threshold; using Tavily fallback"
                    fused_hits = reciprocal_rank_fusion([fused_hits, fallback_hits], k=60)

        return fused_hits[:limit]

    async def _safe_search(
        self,
        provider: SearchProvider,
        query: str,
        limit: int,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[SearchHit]:
        import time
        from core.observability.tracing import record_provider_span
        p_name = getattr(provider, "name", type(provider).__name__)
        start = time.time()
        try:
            hits = await provider.search(query, limit=limit, filters=filters)
            record_provider_span(provider=p_name, query=query, duration=time.time() - start, hits_count=len(hits))
            return hits
        except Exception as e:
            record_provider_span(provider=p_name, query=query, duration=time.time() - start, hits_count=0, error=str(e))
            return []
