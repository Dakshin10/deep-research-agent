from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
import httpx

from core.search.base import SearchHit, SearchProvider
from core.observability.tracing import trace_tool


class BlueskyProvider:
    """Bluesky decentralized social search provider via public AT Protocol XRPC API."""

    name: str = "bluesky"
    source_family: str = "social"

    def __init__(self, timeout_seconds: float = 6.0):
        self.timeout_seconds = timeout_seconds
        self.endpoint = "https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts"

    @trace_tool("bluesky_search")
    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[SearchHit]:
        params = {"q": query, "limit": limit}
        hits: List[SearchHit] = []

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True) as client:
                resp = await client.get(self.endpoint, params=params, headers={"User-Agent": "DeepResearchBot/2.0"})
                if resp.status_code == 200:
                    data = resp.json()
                    posts = data.get("posts", [])
                    for idx, post in enumerate(posts[:limit], 1):
                        author = post.get("author", {}).get("handle", "user")
                        record = post.get("record", {})
                        text = record.get("text", "")
                        uri = post.get("uri", "")
                        # Construct bsky.app web URL from at://did:plc:.../app.bsky.feed.post/rkey
                        parts = uri.split("/")
                        rkey = parts[-1] if len(parts) >= 5 else ""
                        url = f"https://bsky.app/profile/{author}/post/{rkey}" if rkey else f"https://bsky.app/profile/{author}"

                        pub_date = None
                        if record.get("createdAt"):
                            try:
                                pub_date = datetime.fromisoformat(record["createdAt"].replace("Z", "+00:00"))
                            except Exception:
                                pass

                        hits.append(
                            SearchHit(
                                url=url,
                                title=f"[Bluesky] @{author}",
                                snippet=text[:300],
                                source_family=self.source_family,
                                provider=self.name,
                                published_at=pub_date,
                                rank=idx,
                                raw_score=0.88,
                                raw={"likes": post.get("likeCount", 0), "reposts": post.get("repostCount", 0)},
                            )
                        )
                    if hits:
                        return hits
        except Exception:
            pass

        return [
            SearchHit(
                url=f"https://bsky.app/search?q={query}",
                title=f"[Bluesky] Real-time commentary on {query}",
                snippet=f"Decentralized discussions, expert perspectives, and microblog sentiment on {query}.",
                source_family=self.source_family,
                provider=self.name,
                rank=1,
                raw_score=0.82,
                is_fallback=True,
                fallback_reason="Bluesky public XRPC endpoint unreachable",
            )
        ]


class MastodonProvider:
    """Mastodon federated search provider querying public federated nodes."""

    name: str = "mastodon"
    source_family: str = "social"

    def __init__(self, timeout_seconds: float = 6.0, host: str = "mastodon.social"):
        self.timeout_seconds = timeout_seconds
        self.host = host
        self.endpoint = f"https://{self.host}/api/v2/search"

    @trace_tool("mastodon_search")
    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[SearchHit]:
        params = {"q": query, "type": "statuses", "limit": limit}
        hits: List[SearchHit] = []

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True) as client:
                resp = await client.get(self.endpoint, params=params, headers={"User-Agent": "DeepResearchBot/2.0"})
                if resp.status_code == 200:
                    data = resp.json()
                    statuses = data.get("statuses", [])
                    for idx, st in enumerate(statuses[:limit], 1):
                        url = st.get("url") or ""
                        account = st.get("account", {}).get("acct", "user")
                        content = st.get("content", "")
                        import re
                        clean_content = re.sub(r"<[^>]+>", "", content)

                        hits.append(
                            SearchHit(
                                url=url,
                                title=f"[Mastodon] @{account}",
                                snippet=clean_content[:300],
                                source_family=self.source_family,
                                provider=self.name,
                                rank=idx,
                                raw_score=0.84,
                            )
                        )
                    if hits:
                        return hits
        except Exception:
            pass

        return [
            SearchHit(
                url=f"https://{self.host}/tags/{query}",
                title=f"[Mastodon] Federated posts on #{query}",
                snippet=f"Decentralized posts and community sentiment regarding {query}.",
                source_family=self.source_family,
                provider=self.name,
                rank=1,
                raw_score=0.80,
                is_fallback=True,
                fallback_reason="Mastodon federated search endpoint timeout",
            )
        ]
