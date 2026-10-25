from __future__ import annotations

from typing import Dict, List, Optional

from core.sources.adapters.base import SourceAdapter
from core.sources.adapters.devpost import DevpostAdapter
from core.sources.adapters.hackathons import (
    DevfolioAdapter,
    DoraHacksAdapter,
    ETHGlobalAdapter,
    GitHubHackathonAdapter,
    Hack2skillAdapter,
    KaggleAdapter,
    MLHAdapter,
    SIHAdapter,
    UnstopAdapter,
)
from core.sources.adapters.startups import (
    BetaListAdapter,
    HNLaunchesAdapter,
    IndieHackersAdapter,
    ProductHuntAdapter,
    RedditStartupsAdapter,
    YCAdapter,
)
from core.sources.adapters.writeups import (
    DevToAdapter,
    HashnodeAdapter,
    PDFReportsAdapter,
    RSSWriteupsAdapter,
    YouTubePitchesAdapter,
)


class SourceAdapterRegistry:
    """
    Registry for Idea Miner source adapters.
    Provides domain-to-adapter resolution and SearchProvider integration.
    """

    def __init__(self):
        self._adapters: Dict[str, SourceAdapter] = {}
        self._domain_map: Dict[str, SourceAdapter] = {}
        self._register_defaults()

    def _register_defaults(self):
        default_instances: List[SourceAdapter] = [
            # Hackathons
            DevpostAdapter(),
            DevfolioAdapter(),
            DoraHacksAdapter(),
            ETHGlobalAdapter(),
            MLHAdapter(),
            UnstopAdapter(),
            Hack2skillAdapter(),
            SIHAdapter(),
            KaggleAdapter(),
            GitHubHackathonAdapter(),
            # Startups & Launches
            YCAdapter(),
            ProductHuntAdapter(),
            HNLaunchesAdapter(),
            BetaListAdapter(),
            IndieHackersAdapter(),
            RedditStartupsAdapter(),
            # Write-ups & Video
            DevToAdapter(),
            HashnodeAdapter(),
            RSSWriteupsAdapter(),
            YouTubePitchesAdapter(),
            PDFReportsAdapter(),
        ]

        for adapter in default_instances:
            self._adapters[adapter.name] = adapter
            self._domain_map[adapter.domain.lower()] = adapter

    def get_adapter(self, name: str) -> Optional[SourceAdapter]:
        return self._adapters.get(name)

    def get_adapter_for_domain(self, domain: str) -> Optional[SourceAdapter]:
        clean_domain = domain.lower().replace("www.", "").split("/")[0].split(":")[0]
        if clean_domain in self._domain_map:
            return self._domain_map[clean_domain]

        # Check suffix
        for d, adapter in self._domain_map.items():
            if clean_domain.endswith(f".{d}"):
                return adapter
        return None

    def list_adapters(self) -> List[SourceAdapter]:
        return list(self._adapters.values())


_default_source_registry = SourceAdapterRegistry()


class SourceRegistry:
    @classmethod
    def get(cls, name: str) -> Optional[SourceAdapter]:
        return _default_source_registry.get_adapter(name)

    @classmethod
    def get_for_domain(cls, domain: str) -> Optional[SourceAdapter]:
        return _default_source_registry.get_adapter_for_domain(domain)

    @classmethod
    def list(cls) -> List[SourceAdapter]:
        return _default_source_registry.list_adapters()
