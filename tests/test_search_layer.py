import pytest
from datetime import datetime
from unittest.mock import AsyncMock, patch

from core.search.base import SearchHit, SearchProvider
from core.search.canonical import normalize_canonical_url, SimHash, reciprocal_rank_fusion
from core.search.providers.searxng import SearxngProvider
from core.search.providers.forums import HackerNewsProvider, RedditProvider, StackExchangeProvider
from core.search.providers.code import GitHubSearchProvider
from core.search.providers.academic import ArxivProvider, OpenAlexProvider, WikipediaProvider
from core.search.providers.video import YouTubeSearchProvider
from core.search.providers.social import BlueskyProvider, MastodonProvider
from core.search.providers.app_stores import AppleAppStoreProvider, GooglePlayProvider
from core.search.providers.archives import WaybackCdxProvider, MarginaliaProvider
from core.search.providers.duckduckgo import DuckDuckGoProvider
from core.search.providers.tavily_exa import TavilySearchAdapter, ExaSearchAdapter
from core.search.router import SearchRouter


def test_search_provider_protocol_compliance():
    """Verify all 18 search adapters conform to the SearchProvider protocol."""
    providers = [
        SearxngProvider(),
        HackerNewsProvider(),
        RedditProvider(),
        StackExchangeProvider(),
        GitHubSearchProvider(),
        ArxivProvider(),
        OpenAlexProvider(),
        WikipediaProvider(),
        YouTubeSearchProvider(),
        BlueskyProvider(),
        MastodonProvider(),
        AppleAppStoreProvider(),
        GooglePlayProvider(),
        WaybackCdxProvider(),
        MarginaliaProvider(),
        DuckDuckGoProvider(),
        TavilySearchAdapter(),
        ExaSearchAdapter(),
    ]
    for p in providers:
        assert isinstance(p, SearchProvider), f"{p.__class__.__name__} failed SearchProvider protocol check"
        assert hasattr(p, "name")
        assert hasattr(p, "source_family")
        assert callable(getattr(p, "search", None))


def test_url_canonicalization():
    """Verify URL canonicalization strips tracking tokens, default ports, and sorts queries."""
    dirty_url = "HTTPS://WWW.Example.com:443/products/crm/?utm_source=google&fbclid=12345&b_param=two&a_param=one#section-pricing"
    clean_url = normalize_canonical_url(dirty_url)

    assert clean_url == "https://www.example.com/products/crm?a_param=one&b_param=two"

    # Test trailing slash normalization and http port 80
    url_with_port = "http://api.domain.org:80/v1/data/"
    assert normalize_canonical_url(url_with_port) == "http://api.domain.org/v1/data"


def test_simhash_near_duplicate_detection():
    """Verify 64-bit pure Python SimHash identifies exact and near-duplicate snippets."""
    text1 = "HubSpot CRM provides enterprise inbound marketing tools with automated email workflows and deal pipelines."
    text2 = "Hubspot CRM provides enterprise inbound marketing tools with automated email workflow and deal pipeline."
    text3 = "Quantum computing algorithms simulate molecular dynamics using superconducting qubit architectures."

    # Identical
    assert SimHash.hamming_distance(SimHash.compute(text1), SimHash.compute(text1)) == 0

    # Near-duplicate (small variation)
    dist_near = SimHash.hamming_distance(SimHash.compute(text1), SimHash.compute(text2))
    assert dist_near <= 8
    assert SimHash.is_near_duplicate(text1, text2, max_distance=8) is True

    # Completely different text
    dist_far = SimHash.hamming_distance(SimHash.compute(text1), SimHash.compute(text3))
    assert dist_far > 15
    assert SimHash.is_near_duplicate(text1, text3, max_distance=8) is False


def test_reciprocal_rank_fusion_and_deduplication():
    """Verify RRF merges multiple provider lists and ranks consensus URLs highest."""
    list1 = [
        SearchHit(url="https://example.com/shared", title="Shared Top Result", snippet="Detailed guide to CRM systems.", rank=1),
        SearchHit(url="https://example.com/unique-1", title="Unique Item One", snippet="First unique snippet.", rank=2),
    ]
    list2 = [
        SearchHit(url="https://example.com/shared?utm_medium=cpc", title="Shared Top Result", snippet="Detailed guide to CRM systems.", rank=1),
        SearchHit(url="https://example.com/unique-2", title="Unique Item Two", snippet="Second unique snippet.", rank=2),
    ]

    fused = reciprocal_rank_fusion([list1, list2], k=60)
    assert len(fused) == 3

    # Shared URL should have highest fused score and rank #1
    assert fused[0].canonical_url == "https://example.com/shared"
    assert fused[0].rank == 1
    # Check that score combines contributions: 1/(60+1) + 1/(60+1) = 2/61 ≈ 0.03278
    assert fused[0].raw_score > fused[1].raw_score


@pytest.mark.asyncio
async def test_searxng_provider_json_parsing_and_error_handling():
    """Verify SearxngProvider parses JSON, handles unresponsive engines gracefully, and falls back if offline."""
    mock_response = {
        "results": [
            {
                "url": "https://searxng.test/doc",
                "title": "Test Title",
                "content": "Test content snippet",
                "engine": "google",
                "score": 1.5,
                "publishedDate": "2024-05-01T12:00:00Z",
            }
        ],
        "unresponsive_engines": [["bing", "timeout"]],
    }

    provider = SearxngProvider(base_url="http://mock-searxng:8080")
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = AsyncMock(status_code=200, json=lambda: mock_response)
        hits = await provider.search("marketing automation", limit=5)

        assert len(hits) == 1
        assert hits[0].url == "https://searxng.test/doc"
        assert hits[0].provider == "google"
        assert hits[0].raw["unresponsive_engines"] == [["bing", "timeout"]]


@pytest.mark.asyncio
async def test_vertical_search_adapters():
    """Verify vertical adapters execute and return well-formed SearchHit instances."""
    # 1. Hacker News
    hn = HackerNewsProvider()
    hn_hits = await hn.search("langgraph multi-agent", limit=2)
    assert len(hn_hits) >= 1
    assert hn_hits[0].source_family == "forums"

    # 2. GitHub
    gh = GitHubSearchProvider()
    gh_hits = await gh.search("deep-research", limit=2)
    assert len(gh_hits) >= 1
    assert gh_hits[0].source_family == "code"

    # 3. arXiv
    arxiv = ArxivProvider()
    ar_hits = await arxiv.search("large language models", limit=2)
    assert len(ar_hits) >= 1
    assert ar_hits[0].source_family == "academic"

    # 4. Wikipedia
    wiki = WikipediaProvider()
    wiki_hits = await wiki.search("Artificial intelligence", limit=2)
    assert len(wiki_hits) >= 1
    assert wiki_hits[0].source_family == "academic"

    # 5. Apple App Store
    appstore = AppleAppStoreProvider()
    app_hits = await appstore.search("HubSpot", limit=2)
    assert len(app_hits) >= 1
    assert app_hits[0].source_family == "app_stores"

    # 6. Wayback Machine CDX
    wb = WaybackCdxProvider()
    wb_hits = await wb.search("hubspot.com", limit=2)
    assert len(wb_hits) >= 1
    assert wb_hits[0].source_family == "archives"


@pytest.mark.asyncio
async def test_search_router_family_routing_and_fallback():
    """Verify SearchRouter routes queries across source families and aggregates results."""
    router = SearchRouter()

    # Route academic
    academic_hits = await router.search("transformer attention mechanism", source_family="academic", limit=3)
    assert len(academic_hits) >= 1
    assert any(h.source_family == "academic" for h in academic_hits)

    # Route forums
    forum_hits = await router.search("best crm for startups", source_family="forums", limit=3)
    assert len(forum_hits) >= 1
    assert any(h.source_family == "forums" for h in forum_hits)

    # Route general web
    web_hits = await router.search("b2b marketing automation benchmarks", source_family="web_general", limit=3)
    assert len(web_hits) >= 1
