from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator, Dict, List, Optional

from core.search.base import SearchHit, SearchProvider
from core.sources.schemas import RawProject, SourceKind


class AdapterBrokenError(RuntimeError):
    """Raised when website markup changes and adapter selectors break."""
    def __init__(self, adapter_name: str, url: str, reason: str):
        super().__init__(f"Adapter broken for '{adapter_name}' on {url}: {reason}")
        self.adapter_name = adapter_name
        self.url = url
        self.reason = reason


class SourceAdapter(SearchProvider, ABC):
    """
    Abstract base class for all Idea Miner source adapters.
    Implements discover(), parse(), and SearchProvider protocol.
    """

    name: str = "base_adapter"
    domain: str = "example.com"
    source_kind: SourceKind = SourceKind.HACKATHON
    source_family: str = "hackathons"

    @abstractmethod
    async def discover(
        self,
        limit: int = 50,
        since_year: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        """Discovers project URLs via API, RSS, sitemap, or listing pages."""
        yield ""

    @abstractmethod
    def parse(self, url: str, content: str) -> RawProject:
        """
        Parses raw HTML or JSON payload into a structured RawProject.
        MUST raise AdapterBrokenError if markup selectors break.
        """
        pass

    async def search(
        self,
        query: str,
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[SearchHit]:
        """
        Default SearchProvider implementation for on-demand fan-out search.
        Can be overridden with native search API if available.
        """
        return []
