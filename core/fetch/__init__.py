from __future__ import annotations

from core.fetch.base import (
    DocumentPage,
    DocumentSection,
    DocumentTimestamp,
    FetchedDocument,
)
from core.fetch.cache import FetchedDocumentCache, FetchedDocumentCacheModel
from core.fetch.extractors import (
    extract_from_docx,
    extract_from_html,
    extract_from_pdf,
    extract_from_text,
)
from core.fetch.politeness import (
    CircuitBreaker,
    RobotsCache,
    TokenBucketRateLimiter,
    backoff_with_jitter,
)
from core.fetch.tiered_fetcher import TieredFetcher

__all__ = [
    "FetchedDocument",
    "DocumentSection",
    "DocumentPage",
    "DocumentTimestamp",
    "TieredFetcher",
    "FetchedDocumentCache",
    "FetchedDocumentCacheModel",
    "RobotsCache",
    "TokenBucketRateLimiter",
    "CircuitBreaker",
    "backoff_with_jitter",
    "extract_from_html",
    "extract_from_pdf",
    "extract_from_docx",
    "extract_from_text",
]
