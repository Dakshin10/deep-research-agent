from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable
from pydantic import BaseModel, Field


class SearchHit(BaseModel):
    """Normalized search result across all search providers and vertical engines."""
    url: str
    title: str
    snippet: str
    source_family: str = "web_general"  # web_general, news, forums, code, academic, video, social, app_stores, archives
    provider: str = "unknown"
    published_at: Optional[datetime] = None
    rank: int = 1
    raw_score: float = 1.0
    canonical_url: Optional[str] = None
    is_fallback: bool = False
    fallback_reason: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None


@runtime_checkable
class SearchProvider(Protocol):
    """Protocol for all unified search providers."""
    name: str
    source_family: str

    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[SearchHit]:
        """Execute async search returning normalized SearchHit objects."""
        ...
