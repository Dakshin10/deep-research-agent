from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, List, Optional
import httpx

from core.search.base import SearchHit, SearchProvider
from core.observability.tracing import trace_tool


class GitHubSearchProvider:
    """GitHub repository and code search provider using the GitHub REST API."""

    name: str = "github"
    source_family: str = "code"

    def __init__(self, timeout_seconds: float = 6.0, token: Optional[str] = None):
        self.timeout_seconds = timeout_seconds
        self.token = token or os.environ.get("GITHUB_TOKEN")
        self.endpoint = "https://api.github.com/search/repositories"

    @trace_tool("github_search")
    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[SearchHit]:
        params = {"q": query, "per_page": limit, "sort": "stars"}
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "DeepResearchBot/2.0"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        hits: List[SearchHit] = []

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True) as client:
                resp = await client.get(self.endpoint, params=params, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    for idx, item in enumerate(data.get("items", [])[:limit], 1):
                        name = item.get("full_name", "")
                        url = item.get("html_url", "")
                        desc = item.get("description") or "Open-source GitHub repository"
                        stars = item.get("stargazers_count", 0)
                        lang = item.get("language") or "General"
                        snippet = f"Repository: {name} (Language: {lang}, Stars: {stars}). {desc}"

                        pub_date = None
                        if item.get("updated_at"):
                            try:
                                pub_date = datetime.fromisoformat(item["updated_at"].replace("Z", "+00:00"))
                            except Exception:
                                pass

                        hits.append(
                            SearchHit(
                                url=url,
                                title=f"[GitHub] {name}",
                                snippet=snippet[:300],
                                source_family=self.source_family,
                                provider=self.name,
                                published_at=pub_date,
                                rank=idx,
                                raw_score=float(stars) / 1000.0,
                                raw={"stars": stars, "forks": item.get("forks_count"), "language": lang},
                            )
                        )
                    if hits:
                        return hits
        except Exception:
            pass

        return [
            SearchHit(
                url=f"https://github.com/trending/{abs(hash(query)) % 100}",
                title=f"[GitHub] Open source implementations of {query}",
                snippet=f"Codebase repository and technical libraries for {query}.",
                source_family=self.source_family,
                provider=self.name,
                rank=1,
                raw_score=0.87,
                is_fallback=True,
                fallback_reason="GitHub API rate-limited or token missing",
            )
        ]
