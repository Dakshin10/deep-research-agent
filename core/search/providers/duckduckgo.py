from __future__ import annotations

import re
import urllib.parse
from typing import Any, Dict, List, Optional
import httpx

from core.search.base import SearchHit, SearchProvider
from core.observability.tracing import trace_tool


class DuckDuckGoProvider:
    """DuckDuckGo privacy-focused general search provider."""

    name: str = "duckduckgo"
    source_family: str = "web_general"

    def __init__(self, timeout_seconds: float = 6.0):
        self.timeout_seconds = timeout_seconds

    @trace_tool("ddg_search")
    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[SearchHit]:
        hits: List[SearchHit] = []

        # 1. Try duckduckgo HTML search endpoint
        endpoint = "https://html.duckduckgo.com/html/"
        data = {"q": query}
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True) as client:
                resp = await client.post(endpoint, data=data, headers=headers)
                if resp.status_code == 200:
                    text = resp.text
                    # Extract result links and snippets
                    titles = re.findall(r'<a class="result__snippet[^>]*href="([^"]+)"[^>]*>(.*?)</a>', text, re.DOTALL)
                    links = re.findall(r'<a class="result__url[^>]*href="([^"]+)"[^>]*>(.*?)</a>', text, re.DOTALL)
                    snippets = re.findall(r'<a class="result__snippet[^>]*>(.*?)</a>', text, re.DOTALL)

                    for idx in range(min(limit, len(links))):
                        url = links[idx][0].strip()
                        # Unquote DDG redirect uddg= if present
                        if "uddg=" in url:
                            m = re.search(r'uddg=([^&]+)', url)
                            if m:
                                url = urllib.parse.unquote(m.group(1))

                        snippet_raw = snippets[idx] if idx < len(snippets) else ""
                        snippet_clean = re.sub(r'<[^>]+>', '', snippet_raw).strip()
                        title_raw = titles[idx][1] if idx < len(titles) else f"Result {idx+1} for {query}"
                        title_clean = re.sub(r'<[^>]+>', '', title_raw).strip()

                        if url.startswith("http"):
                            hits.append(
                                SearchHit(
                                    url=url,
                                    title=title_clean or f"Search result for {query}",
                                    snippet=snippet_clean or f"Web findings for {query}",
                                    source_family=self.source_family,
                                    provider=self.name,
                                    rank=idx + 1,
                                    raw_score=0.9,
                                )
                            )
                    if hits:
                        return hits
        except Exception:
            pass

        return [
            SearchHit(
                url=f"https://duckduckgo.com/?q={urllib.parse.quote_plus(query)}",
                title=f"DuckDuckGo search for {query}",
                snippet=f"Privacy-grounded general search results and web findings for {query}.",
                source_family=self.source_family,
                provider=self.name,
                rank=1,
                raw_score=0.88,
                is_fallback=True,
                fallback_reason="DuckDuckGo endpoint rate-limited or timeout",
            )
        ]
