from __future__ import annotations

import re
from typing import Optional
import httpx

from core.fetch.tiered_fetcher import TieredFetcher
from core.fetch.base import FetchedDocument
from core.guardrails.injection import PromptInjectionDefense
from core.observability.tracing import trace_tool


class PageFetchService:
    """
    Fetches web page content using TieredFetcher (HTTPX -> Crawl4AI -> Playwright -> Wayback),
    extracts clean markdown with heading structure, and fences untrusted data.
    """

    def __init__(self, max_chars: int = 10000, fetcher: Optional[TieredFetcher] = None):
        self.max_chars = max_chars
        self.fetcher = fetcher or TieredFetcher()

    @trace_tool("fetch_markdown")
    async def fetch_markdown(self, url: str) -> str:
        doc: FetchedDocument = await self.fetcher.fetch(url)
        clean_text = doc.to_clean_markdown(max_chars=self.max_chars)
        return PromptInjectionDefense.fence(
            content=clean_text,
            source_type=doc.content_type,
            source_url_or_id=doc.final_url or url,
        )

    async def fetch_document(self, url: str) -> FetchedDocument:
        """Fetch the full structured FetchedDocument with sections, pages, and offsets."""
        return await self.fetcher.fetch(url)

    async def _fetch_raw(self, url: str) -> str:
        doc = await self.fetcher.fetch(url)
        return doc.raw_text

    def _html_to_clean_markdown(self, html_content: str) -> str:
        # Strip script, style, nav, footer, aside tags
        cleaned = re.sub(r"(?i)<(script|style|nav|footer|aside)[\s\S]*?</\1>", "", html_content)
        # Convert simple tags to markdown
        cleaned = re.sub(r"(?i)<h[1-3][^>]*>(.*?)</h[1-3]>", r"\n### \1\n", cleaned)
        cleaned = re.sub(r"(?i)<p[^>]*>(.*?)</p>", r"\n\1\n", cleaned)
        cleaned = re.sub(r"(?i)<li[^>]*>(.*?)</li>", r"\n* \1", cleaned)
        # Strip all other tags
        cleaned = re.sub(r"<[^>]+>", "", cleaned)
        # Condense spaces
        cleaned = re.sub(r"\n\s*\n", "\n\n", cleaned)
        return cleaned.strip()
