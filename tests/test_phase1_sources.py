from __future__ import annotations

import os
import pytest

from core.sources.policy import SourcePolicyEngine
from core.sources.schemas import ProjectPlacement, RawProject, SourceKind
from core.sources.adapters.base import AdapterBrokenError
from core.sources.adapters.devpost import DevpostAdapter
from core.sources.adapters.hackathons import (
    DevfolioAdapter,
    DoraHacksAdapter,
    ETHGlobalAdapter,
    GitHubHackathonAdapter,
)
from core.sources.adapters.startups import (
    HNLaunchesAdapter,
    ProductHuntAdapter,
    YCAdapter,
)
from core.sources.adapters.writeups import YouTubePitchesAdapter
from core.sources.registry import SourceAdapterRegistry
from core.tools.registry import DataSourceRegistry
from core.search.router import SearchRouter


FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "sources")


def test_source_policy_allowed_and_denied_domains():
    """Verify source policy enforces allowed domains, blocks denied domains, and defaults unknown domains."""
    policy = SourcePolicyEngine()

    # 1. Allowed domains
    is_ok, reason, rule = policy.is_allowed("https://devpost.com/software/autodoc")
    assert is_ok is True
    assert "ALLOWED" in reason
    assert rule.get("access_method") == "html"
    assert rule.get("rate_limit_rps") == 0.5

    is_ok, reason, rule = policy.is_allowed("ycombinator.com")
    assert is_ok is True
    assert rule.get("max_pages_per_run") == 500

    # 2. Explicitly DENIED domains (anti-scraping Terms of Service)
    denied_list = ["linkedin.com", "x.com", "twitter.com", "facebook.com", "instagram.com", "crunchbase.com"]
    for domain in denied_list:
        is_ok, reason, rule = policy.is_allowed(f"https://www.{domain}/company/profile")
        assert is_ok is False, f"Domain {domain} must be strictly DENIED"
        assert "DENIED by policy" in reason

    # 3. Unknown domain default: refused on direct crawl, allowed via search hit
    is_ok, reason, _ = policy.is_allowed("https://random-unknown-startup-blog.io/post")
    assert is_ok is False
    assert "REFUSED" in reason

    is_ok, reason, _ = policy.is_allowed("https://random-unknown-startup-blog.io/post", is_search_result=True)
    assert is_ok is True
    assert "ALLOWED" in reason


def test_devpost_adapter_parsing_winner_fixture():
    """Verify DevpostAdapter extracts title, winner badge, team size, tech stack, and links."""
    fixture_path = os.path.join(FIXTURES_DIR, "devpost_project.html")
    with open(fixture_path, "r", encoding="utf-8") as f:
        html = f.read()

    adapter = DevpostAdapter()
    proj = adapter.parse("https://devpost.com/software/autodoc-ai", html)

    assert isinstance(proj, RawProject)
    assert proj.name == "AutoDoc AI: Automated Technical Documentation"
    assert "OpenAPI specs" in (proj.tagline or "")
    assert proj.placement == ProjectPlacement.WINNER
    assert "1st Place Overall" in (proj.prize_name or "")
    assert proj.team_size == 2
    assert "Alice Chen" in proj.authors
    assert "LangGraph" in proj.tech_stack
    assert "repo" in proj.links and "github.com/autodoc-ai/autodoc" in proj.links["repo"]
    assert "demo" in proj.links and "autodoc-demo.vercel.app" in proj.links["demo"]


def test_devfolio_adapter_parsing_json_fixture():
    """Verify DevfolioAdapter parses JSON API payload into structured RawProject."""
    fixture_path = os.path.join(FIXTURES_DIR, "devfolio_project.json")
    with open(fixture_path, "r", encoding="utf-8") as f:
        content = f.read()

    adapter = DevfolioAdapter()
    proj = adapter.parse("https://devfolio.co/projects/neuro-mesh-6a1b", content)

    assert proj.name == "NeuroMesh"
    assert proj.placement == ProjectPlacement.WINNER
    assert proj.prize_name == "Healthcare Track Gold Winner"
    assert proj.event_name == "ETHIndia 2026"
    assert proj.team_size == 3
    assert "PyTorch" in proj.tech_stack
    assert proj.links.get("repo") == "https://github.com/neuromesh/protocol"


def test_yc_adapter_parsing_html_fixture():
    """Verify YCAdapter extracts startup company name, pitch, batch, and links."""
    fixture_path = os.path.join(FIXTURES_DIR, "yc_company.html")
    with open(fixture_path, "r", encoding="utf-8") as f:
        html = f.read()

    adapter = YCAdapter()
    proj = adapter.parse("https://www.ycombinator.com/companies/synthea", html)

    assert proj.name == "Synthea"
    assert "Synthetic voice agents" in (proj.tagline or "")
    assert "EHRs" in proj.description_raw
    assert proj.links.get("website") == "https://synthea.health"
    assert proj.source_kind == SourceKind.STARTUP


def test_hn_launches_adapter_parsing_json_fixture():
    """Verify HNLaunchesAdapter parses Algolia Show HN payload."""
    fixture_path = os.path.join(FIXTURES_DIR, "hn_launch.json")
    with open(fixture_path, "r", encoding="utf-8") as f:
        content = f.read()

    adapter = HNLaunchesAdapter()
    proj = adapter.parse("https://news.ycombinator.com/item?id=39948210", content)

    assert "GitTrace" in proj.name
    assert "342 points" in (proj.tagline or "")
    assert "devguru" in proj.authors
    assert proj.links.get("website") == "https://gittrace.dev"
    assert "hn_discussion" in proj.links


def test_youtube_pitches_adapter_parsing_json_fixture():
    """Verify YouTubePitchesAdapter extracts demo video metadata and transcript."""
    fixture_path = os.path.join(FIXTURES_DIR, "youtube_pitch.json")
    with open(fixture_path, "r", encoding="utf-8") as f:
        content = f.read()

    adapter = YouTubePitchesAdapter()
    proj = adapter.parse("https://www.youtube.com/watch?v=v91kLq02aZ", content)

    assert "AetherOS" in proj.name
    assert "Transcript" in proj.description_raw
    assert "autonomous semantic memory layer" in proj.description_raw
    assert proj.source_kind == SourceKind.VIDEO


def test_adapter_broken_loud_failure():
    """Verify adapters raise AdapterBrokenError when page markup changes, never silently returning empty."""
    fixture_path = os.path.join(FIXTURES_DIR, "broken_markup.html")
    with open(fixture_path, "r", encoding="utf-8") as f:
        html = f.read()

    adapter = DevpostAdapter()
    with pytest.raises(AdapterBrokenError) as exc_info:
        adapter.parse("https://devpost.com/software/corrupted-page", html)

    assert "Adapter broken for 'devpost'" in str(exc_info.value)


@pytest.mark.asyncio
async def test_adapters_in_search_router_and_datasource_registry():
    """Verify that all Idea Miner adapters are registered as SearchProviders and DataSources."""
    registry = SourceAdapterRegistry()
    adapters = registry.list_adapters()
    assert len(adapters) >= 20, f"Expected >= 20 source adapters, found {len(adapters)}"

    # Check DataSourceRegistry
    ds_reg = DataSourceRegistry()
    assert ds_reg.get_source("hackathons") is not None
    assert ds_reg.get_source("startups") is not None
    assert ds_reg.get_source("writeups") is not None

    # Check SearchRouter integrates hackathon adapter hits
    router = SearchRouter()
    hackathon_hits = await router.search("autonomous coding agent", source_family="hackathons", limit=3)
    assert isinstance(hackathon_hits, list)
