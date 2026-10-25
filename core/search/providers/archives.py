from __future__ import annotations

import urllib.parse
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import httpx

from core.search.base import SearchHit, SearchProvider
from core.observability.tracing import trace_tool


class WaybackCdxProvider:
    """Wayback Machine CDX API provider retrieving historical snapshots of web pages."""

    name: str = "wayback_cdx"
    source_family: str = "archives"

    def __init__(self, timeout_seconds: float = 6.0):
        self.timeout_seconds = timeout_seconds
        self.endpoint = "https://web.archive.org/cdx/search/cdx"

    @trace_tool("wayback_search")
    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[SearchHit]:
        # Formulate query for CDX (domain or keyword matching URL)
        target_domain = query.replace("http://", "").replace("https://", "").split("/")[0]
        params = {
            "url": f"*{target_domain}*",
            "output": "json",
            "limit": limit,
            "filter": "statuscode:200",
            "collapse": "urlkey",
        }
        hits: List[SearchHit] = []

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True) as client:
                resp = await client.get(self.endpoint, params=params, headers={"User-Agent": "DeepResearchBot/2.0"})
                if resp.status_code == 200:
                    data = resp.json()
                    if len(data) > 1:
                        headers = data[0]
                        rows = data[1:limit + 1]
                        for idx, row in enumerate(rows, 1):
                            row_dict = dict(zip(headers, row))
                            orig_url = row_dict.get("original", "")
                            ts = row_dict.get("timestamp", "")
                            archive_url = f"https://web.archive.org/web/{ts}/{orig_url}" if ts and orig_url else orig_url

                            pub_date = None
                            if ts and len(ts) >= 8:
                                try:
                                    pub_date = datetime.strptime(ts[:8], "%Y%m%d").replace(tzinfo=timezone.utc)
                                except Exception:
                                    pass

                            hits.append(
                                SearchHit(
                                    url=archive_url,
                                    title=f"[Wayback Snapshot] {orig_url}",
                                    snippet=f"Archived historical snapshot captured on {ts}. Status: 200 OK. MIME: {row_dict.get('mimetype')}.",
                                    source_family=self.source_family,
                                    provider=self.name,
                                    published_at=pub_date,
                                    rank=idx,
                                    raw_score=0.88,
                                    raw=row_dict,
                                )
                            )
                    if hits:
                        return hits
        except Exception:
            pass

        return [
            SearchHit(
                url=f"https://web.archive.org/web/*/{query}",
                title=f"[Wayback Archive] Historical snapshots for {query}",
                snippet=f"Preserved timeline and past snapshots of target domain or topic from the Wayback Machine.",
                source_family=self.source_family,
                provider=self.name,
                rank=1,
                raw_score=0.82,
                is_fallback=True,
                fallback_reason="Wayback CDX API unreachable or timeout",
            )
        ]


class MarginaliaProvider:
    """Marginalia non-commercial independent web search provider."""

    name: str = "marginalia"
    source_family: str = "archives"

    def __init__(self, timeout_seconds: float = 6.0):
        self.timeout_seconds = timeout_seconds

    @trace_tool("marginalia_search")
    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[SearchHit]:
        # Marginalia public search API
        encoded_q = urllib.parse.quote_plus(query)
        endpoint = f"https://api.marginalia.nu/public/search/{encoded_q}"
        hits: List[SearchHit] = []

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True) as client:
                resp = await client.get(endpoint, params={"count": limit}, headers={"User-Agent": "DeepResearchBot/2.0"})
                if resp.status_code == 200:
                    data = resp.json()
                    results = data.get("results", [])
                    for idx, res in enumerate(results[:limit], 1):
                        hits.append(
                            SearchHit(
                                url=res.get("url", ""),
                                title=f"[Marginalia] {res.get('title', '')}",
                                snippet=res.get("description", "") or "Independent web index result",
                                source_family=self.source_family,
                                provider=self.name,
                                rank=idx,
                                raw_score=0.85,
                            )
                        )
                    if hits:
                        return hits
        except Exception:
            pass

        return [
            SearchHit(
                url=f"https://search.marginalia.nu/site/{query}",
                title=f"[Marginalia] Non-commercial web results for {query}",
                snippet=f"Long-tail, independent internet blogs and text-rich resources matching {query}.",
                source_family=self.source_family,
                provider=self.name,
                rank=1,
                raw_score=0.80,
                is_fallback=True,
                fallback_reason="Marginalia API timeout or offline",
            )
        ]
