from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional
from pydantic import BaseModel


class DataSourceMetadata(BaseModel):
    name: str
    description: str
    read_only: bool = True
    enabled: bool = True


class DataSource(ABC):
    """Abstract protocol for data sources available to research workers."""

    name: str
    description: str
    read_only: bool = True

    @abstractmethod
    def build_tools(self, tenant_id: str) -> List[Callable]:
        """Build tools exposed to researcher workers for this tenant."""
        pass

    def is_enabled(self, tenant_id: str) -> bool:
        return True


class WebSearchDataSource(DataSource):
    name = "web_search"
    description = "Public web search via Tavily/Exa for real-time news, market statistics, competitor websites."

    def build_tools(self, tenant_id: str) -> List[Callable]:
        from core.tools.search import SearchService
        service = SearchService()
        return [service.search]


class WebFetchDataSource(DataSource):
    name = "web_fetch"
    description = "Extracts clean markdown from specific URLs using crawl4ai/html parser with prompt-injection fencing."

    def build_tools(self, tenant_id: str) -> List[Callable]:
        from core.tools.fetch import PageFetchService
        service = PageFetchService()
        return [service.fetch_markdown]


class KnowledgeBaseDataSource(DataSource):
    name = "knowledge_base"
    description = "Tenant-scoped proprietary documents and global marketing benchmark vector/keyword knowledge layer."

    def build_tools(self, tenant_id: str) -> List[Callable]:
        from core.knowledge.store import KnowledgeStore
        store = KnowledgeStore(tenant_id=tenant_id)
        return [store.retrieve]


class RedditDataSource(DataSource):
    name = "reddit"
    description = "Voice-of-customer social sentiment, user complaints, and product feedback on relevant subreddits."

    def build_tools(self, tenant_id: str) -> List[Callable]:
        return []

    def is_enabled(self, tenant_id: str) -> bool:
        return False  # Configurable flag


class GA4DataSource(DataSource):
    name = "ga4_mcp"
    description = "Google Analytics 4 marketing reporting via read-only stdio MCP server."

    def build_tools(self, tenant_id: str) -> List[Callable]:
        return []


class HubSpotDataSource(DataSource):
    name = "hubspot_mcp"
    description = "HubSpot CRM pipeline, deals, and company data via read-only allow-listed MCP tools."

    def build_tools(self, tenant_id: str) -> List[Callable]:
        return []


class WebGeneralDataSource(DataSource):
    name = "web_general"
    description = "SearXNG metasearch and DuckDuckGo general web crawling across indexed public sites."

    def build_tools(self, tenant_id: str) -> List[Callable]:
        from core.search.router import SearchRouter
        router = SearchRouter()
        return [lambda q: router.search(q, source_family="web_general")]


class NewsDataSource(DataSource):
    name = "news"
    description = "Real-time news headlines, RSS feeds, and breaking media publications."

    def build_tools(self, tenant_id: str) -> List[Callable]:
        from core.search.router import SearchRouter
        router = SearchRouter()
        return [lambda q: router.search(q, source_family="news")]


class ForumsDataSource(DataSource):
    name = "forums"
    description = "Community discussion forums including Reddit, Hacker News, and Stack Exchange."

    def build_tools(self, tenant_id: str) -> List[Callable]:
        from core.search.router import SearchRouter
        router = SearchRouter()
        return [lambda q: router.search(q, source_family="forums")]


class CodeDataSource(DataSource):
    name = "code"
    description = "Open source code repositories, GitHub libraries, documentation, and technical issues."

    def build_tools(self, tenant_id: str) -> List[Callable]:
        from core.search.router import SearchRouter
        router = SearchRouter()
        return [lambda q: router.search(q, source_family="code")]


class AcademicDataSource(DataSource):
    name = "academic"
    description = "Scientific papers and formal knowledge bases from arXiv, OpenAlex, and Wikipedia."

    def build_tools(self, tenant_id: str) -> List[Callable]:
        from core.search.router import SearchRouter
        router = SearchRouter()
        return [lambda q: router.search(q, source_family="academic")]


class VideoDataSource(DataSource):
    name = "video"
    description = "Video recordings, conference presentations, and timestamped transcripts from YouTube."

    def build_tools(self, tenant_id: str) -> List[Callable]:
        from core.search.router import SearchRouter
        router = SearchRouter()
        return [lambda q: router.search(q, source_family="video")]


class SocialDataSource(DataSource):
    name = "social"
    description = "Decentralized real-time microblogs and commentary from Bluesky and Mastodon."

    def build_tools(self, tenant_id: str) -> List[Callable]:
        from core.search.router import SearchRouter
        router = SearchRouter()
        return [lambda q: router.search(q, source_family="social")]


class AppStoresDataSource(DataSource):
    name = "app_stores"
    description = "Mobile and desktop applications from Apple App Store and Google Play Store."

    def build_tools(self, tenant_id: str) -> List[Callable]:
        from core.search.router import SearchRouter
        router = SearchRouter()
        return [lambda q: router.search(q, source_family="app_stores")]


class ArchivesDataSource(DataSource):
    name = "archives"
    description = "Historical web snapshots from the Wayback Machine and non-commercial archives."

    def build_tools(self, tenant_id: str) -> List[Callable]:
        from core.search.router import SearchRouter
        router = SearchRouter()
        return [lambda q: router.search(q, source_family="archives")]


class WebIndexDataSource(DataSource):
    name = "web_index"
    description = "Tenant-scoped local web index of previously fetched, verified passages with hybrid vector + full-text retrieval."

    def build_tools(self, tenant_id: str) -> List[Callable]:
        from core.knowledge.web_index import WebIndexStore
        store = WebIndexStore(tenant_id=tenant_id)
        return [store.hybrid_search]


class DataSourceRegistry:
    """Central registry of all data sources available in the Deep Researcher."""

    def __init__(self):
        self._sources: Dict[str, DataSource] = {}
        self._register_defaults()

    def _register_defaults(self):
        # Legacy mappings for backward compatibility
        self.register(WebSearchDataSource())
        self.register(WebFetchDataSource())
        self.register(KnowledgeBaseDataSource())
        self.register(RedditDataSource())
        self.register(GA4DataSource())
        self.register(HubSpotDataSource())

        # Source families
        self.register(WebGeneralDataSource())
        self.register(NewsDataSource())
        self.register(ForumsDataSource())
        self.register(CodeDataSource())
        self.register(AcademicDataSource())
        self.register(VideoDataSource())
        self.register(SocialDataSource())
        self.register(AppStoresDataSource())
        self.register(ArchivesDataSource())
        self.register(WebIndexDataSource())

    def register(self, source: DataSource):
        self._sources[source.name] = source

    def get_source(self, name: str) -> Optional[DataSource]:
        return self._sources.get(name)

    def list_sources(self, tenant_id: str) -> List[DataSourceMetadata]:
        return [
            DataSourceMetadata(
                name=src.name,
                description=src.description,
                read_only=src.read_only,
                enabled=src.is_enabled(tenant_id),
            )
            for src in self._sources.values()
        ]

    def get_descriptions(self, tenant_id: str) -> Dict[str, str]:
        return {
            name: src.description
            for name, src in self._sources.items()
            if src.is_enabled(tenant_id)
        }
