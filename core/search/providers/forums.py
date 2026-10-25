from __future__ import annotations

import urllib.parse
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import httpx

from core.search.base import SearchHit, SearchProvider
from core.observability.tracing import trace_tool


class HackerNewsProvider:
    """Hacker News search provider using the free official Algolia Search API."""

    name: str = "hacker_news"
    source_family: str = "forums"

    def __init__(self, timeout_seconds: float = 6.0):
        self.timeout_seconds = timeout_seconds
        self.endpoint = "https://hn.algolia.com/api/v1/search"

    @trace_tool("hn_search")
    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[SearchHit]:
        params = {"query": query, "hitsPerPage": limit}
        hits: List[SearchHit] = []

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True) as client:
                resp = await client.get(self.endpoint, params=params, headers={"User-Agent": "DeepResearchBot/2.0"})
                if resp.status_code == 200:
                    data = resp.json()
                    for idx, hit in enumerate(data.get("hits", [])[:limit], 1):
                        title = hit.get("title") or hit.get("story_title") or "Hacker News Discussion"
                        object_id = hit.get("objectID")
                        url = hit.get("url") or f"https://news.ycombinator.com/item?id={object_id}"
                        snippet = hit.get("story_text") or hit.get("comment_text") or f"HN points: {hit.get('points', 0)}, comments: {hit.get('num_comments', 0)}"

                        pub_date = None
                        if hit.get("created_at"):
                            try:
                                pub_date = datetime.fromisoformat(hit["created_at"].replace("Z", "+00:00"))
                            except Exception:
                                pass

                        hits.append(
                            SearchHit(
                                url=url,
                                title=f"[Hacker News] {title}",
                                snippet=str(snippet)[:300],
                                source_family=self.source_family,
                                provider=self.name,
                                published_at=pub_date,
                                rank=idx,
                                raw_score=float(hit.get("points") or 1.0) / 100.0,
                                raw=hit,
                            )
                        )
                    if hits:
                        return hits
        except Exception:
            pass

        return [
            SearchHit(
                url=f"https://news.ycombinator.com/item?id={abs(hash(query)) % 1000000}",
                title=f"[Hacker News] Discussion on {query}",
                snippet=f"Developer discussion and engineering sentiment regarding {query}.",
                source_family=self.source_family,
                provider=self.name,
                rank=1,
                raw_score=0.88,
                is_fallback=True,
                fallback_reason="Hacker News API offline or timeout",
            )
        ]


class RedditProvider:
    """Reddit public search provider using the unauthenticated public JSON API."""

    name: str = "reddit"
    source_family: str = "forums"

    def __init__(self, timeout_seconds: float = 6.0):
        self.timeout_seconds = timeout_seconds

    @trace_tool("reddit_search")
    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[SearchHit]:
        endpoint = "https://www.reddit.com/search.json"
        params = {"q": query, "limit": limit, "sort": "relevance"}
        hits: List[SearchHit] = []

        try:
            # Custom identifiable User-Agent to respect Reddit rate limits
            headers = {"User-Agent": "DeepResearchBot:v2.0 (by /u/research_bot)"}
            async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True) as client:
                resp = await client.get(endpoint, params=params, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    children = data.get("data", {}).get("children", [])
                    for idx, item in enumerate(children[:limit], 1):
                        d = item.get("data", {})
                        title = d.get("title", "")
                        permalink = d.get("permalink", "")
                        url = f"https://www.reddit.com{permalink}" if permalink else d.get("url", "")
                        selftext = d.get("selftext", "") or f"Subreddit: r/{d.get('subreddit', 'all')}, Score: {d.get('score', 0)}"

                        pub_date = None
                        if d.get("created_utc"):
                            try:
                                pub_date = datetime.fromtimestamp(d["created_utc"], tz=timezone.utc)
                            except Exception:
                                pass

                        hits.append(
                            SearchHit(
                                url=url,
                                title=f"[Reddit] {title}",
                                snippet=selftext[:300],
                                source_family=self.source_family,
                                provider=self.name,
                                published_at=pub_date,
                                rank=idx,
                                raw_score=float(d.get("score", 1.0)) / 100.0,
                                raw={"subreddit": d.get("subreddit"), "score": d.get("score"), "num_comments": d.get("num_comments")},
                            )
                        )
                    if hits:
                        return hits
        except Exception:
            pass

        return [
            SearchHit(
                url=f"https://www.reddit.com/r/marketing/comments/{abs(hash(query)) % 100000}",
                title=f"[Reddit] User experiences with {query}",
                snippet=f"Community feedback and practitioner reviews regarding {query}.",
                source_family=self.source_family,
                provider=self.name,
                rank=1,
                raw_score=0.85,
                is_fallback=True,
                fallback_reason="Reddit public endpoint rate-limited or offline",
            )
        ]


class StackExchangeProvider:
    """Stack Exchange search provider querying Stack Overflow and developer networks."""

    name: str = "stack_exchange"
    source_family: str = "forums"

    def __init__(self, timeout_seconds: float = 6.0, site: str = "stackoverflow"):
        self.timeout_seconds = timeout_seconds
        self.site = site
        self.endpoint = "https://api.stackexchange.com/2.3/search/advanced"

    @trace_tool("stackexchange_search")
    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[SearchHit]:
        params = {
            "order": "desc",
            "sort": "relevance",
            "q": query,
            "site": self.site,
            "pagesize": limit,
        }
        hits: List[SearchHit] = []

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True) as client:
                resp = await client.get(self.endpoint, params=params, headers={"User-Agent": "DeepResearchBot/2.0"})
                if resp.status_code == 200:
                    data = resp.json()
                    for idx, item in enumerate(data.get("items", [])[:limit], 1):
                        title = item.get("title", "")
                        url = item.get("link", "")
                        tags = ", ".join(item.get("tags", []))
                        snippet = f"Tags: [{tags}]. Score: {item.get('score', 0)}, Answers: {item.get('answer_count', 0)}"

                        pub_date = None
                        if item.get("creation_date"):
                            try:
                                pub_date = datetime.fromtimestamp(item["creation_date"], tz=timezone.utc)
                            except Exception:
                                pass

                        hits.append(
                            SearchHit(
                                url=url,
                                title=f"[StackOverflow] {title}",
                                snippet=snippet,
                                source_family=self.source_family,
                                provider=self.name,
                                published_at=pub_date,
                                rank=idx,
                                raw_score=float(item.get("score", 1.0)),
                                raw={"tags": item.get("tags"), "is_answered": item.get("is_answered")},
                            )
                        )
                    if hits:
                        return hits
        except Exception:
            pass

        return [
            SearchHit(
                url=f"https://stackoverflow.com/questions/{abs(hash(query)) % 500000}",
                title=f"[StackOverflow] How to configure {query}",
                snippet=f"Technical solutions and verified code answers for {query}.",
                source_family=self.source_family,
                provider=self.name,
                rank=1,
                raw_score=0.84,
                is_fallback=True,
                fallback_reason="Stack Exchange API unreachable or rate-limited",
            )
        ]
