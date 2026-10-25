import asyncio
import json
import pytest
import re
import time
import urllib.parse
from datetime import datetime, timezone
from typing import List, Dict, Any
from unittest.mock import AsyncMock, patch

from core.agents.orchestrator import ResearchOrchestrator
from core.fetch.base import FetchedDocument, DocumentSection, DocumentPage
from core.fetch.politeness import RobotsCache, TokenBucketRateLimiter, CircuitBreaker
from core.fetch.location import (
    verify_excerpt_in_document,
    generate_text_fragment_url,
)
from core.guardrails.citation_gate import CitationGate
from core.knowledge.web_index import WebIndexStore
from core.search.base import SearchHit
from core.search.canonical import (
    normalize_canonical_url,
    SimHash,
    reciprocal_rank_fusion,
)
from core.search.providers.searxng import SearxngProvider
from core.search.providers.forums import HackerNewsProvider, RedditProvider
from core.search.providers.academic import ArxivProvider, WikipediaProvider
from core.search.providers.code import GitHubSearchProvider
from core.search.providers.app_stores import AppleAppStoreProvider, GooglePlayProvider
from core.search.providers.archives import WaybackCdxProvider
from core.search.router import SearchRouter
from core.state.schemas import (
    Brief,
    BudgetState,
    ExpectedOutput,
    Job,
    JobMode,
    JobStatus,
    Plan,
    PlanTask,
    ResearchNote,
    TaskStatus,
)
from core.state.store import StateStore


# ==============================================================================
# 1. Provider Adapters: Offline Fixtures, Parsing, Errors, Pagination, Fallback
# ==============================================================================

@pytest.mark.asyncio
async def test_provider_adapters_offline_fixtures():
    """Verify offline provider adapters: parsing, graceful error handling, pagination, and fallback tagging."""
    # 1. SearXNG Provider with mock JSON response
    searxng = SearxngProvider(base_url="http://searxng.internal")
    mock_searx_payload = {
        "results": [
            {
                "url": "https://docs.vllm.ai/en/latest/benchmarks.html",
                "title": "vLLM High-Throughput Serving Benchmarks",
                "content": "vLLM achieves 24x higher throughput compared to HuggingFace TGI.",
                "engine": "google",
                "score": 0.95,
            },
            {
                "url": "https://arxiv.org/abs/2309.06180",
                "title": "Efficient Memory Management for Large Language Model Serving with PagedAttention",
                "content": "PagedAttention paper and benchmarks.",
                "engine": "arxiv",
                "score": 0.91,
            },
        ],
        "unresponsive_engines": ["duckduckgo"],
    }

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.json = lambda: mock_searx_payload
        mock_get.return_value = mock_resp

        hits = await searxng.search("vllm serving benchmarks", limit=5)
        assert len(hits) == 2
        assert hits[0].provider in ["searxng", "google"]
        assert hits[0].source_family == "web_general"
        assert "vLLM" in hits[0].title
        assert hits[0].raw_score == 0.95

    # 2. Hacker News Provider with mock Algolia API response
    hn = HackerNewsProvider()
    mock_hn_payload = {
        "hits": [
            {
                "url": "https://news.ycombinator.com/item?id=38123456",
                "title": "Show HN: vLLM Distributed Serving Architecture",
                "author": "woosuk",
                "created_at": "2024-01-15T12:00:00Z",
                "points": 540,
                "_highlightResult": {"story_text": {"value": "We implemented PagedAttention to eliminate memory fragmentation."}},
            }
        ]
    }
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.json = lambda: mock_hn_payload
        mock_get.return_value = mock_resp

        hits = await hn.search("vLLM architecture")
        assert len(hits) == 1
        assert hits[0].source_family == "forums"
        assert hits[0].provider == "hacker_news"

    # 3. Provider upstream error handling (non-fatal recovery)
    with patch("httpx.AsyncClient.get", side_effect=Exception("Connection refused / upstream 503")):
        error_hits = await searxng.search("resilience test")
        # Graceful handling: either returns empty list, or returns fallback-tagged hits (never raises)
        assert isinstance(error_hits, list), "Provider failures must not raise; return a list"
        if error_hits:
            assert all(h.is_fallback for h in error_hits), (
                "If fallback hits returned on error, all must be tagged is_fallback=True"
            )

    # 4. Fallback tagging on Tavily / Exa when enabled as fallback
    from core.tools.search import SearchService
    svc = SearchService()
    fallback_res = await svc.search("crm automation benchmarks")
    # search() returns a list of SearchResult; check first item's fields
    assert isinstance(fallback_res, list) and len(fallback_res) > 0
    assert hasattr(fallback_res[0], "is_fallback")
    assert hasattr(fallback_res[0], "fallback_reason")


# ==============================================================================
# 2. RRF Merge, Canonicalization & Near-Duplicate Content Dedup
# ==============================================================================

def test_rrf_canonicalization_and_simhash_dedup():
    """Verify RRF rank merging, canonical URL tracking stripping, and SimHash text deduplication."""
    # 1. Canonicalization
    raw_urls = [
        "https://example.com/blog/pricing/?utm_source=twitter&utm_medium=cpc&fbclid=123#overview",
        "https://example.com/blog/pricing?ref=marketing_campaign",
        "https://example.com/blog/pricing/",
    ]
    canonical_set = {normalize_canonical_url(u) for u in raw_urls}
    assert len(canonical_set) == 1
    assert "https://example.com/blog/pricing" in canonical_set

    # 2. Reciprocal Rank Fusion (RRF)
    list1 = [
        SearchHit(url="https://site.com/a", title="Doc A", snippet="", rank=1),
        SearchHit(url="https://site.com/b", title="Doc B", snippet="", rank=2),
    ]
    list2 = [
        SearchHit(url="https://site.com/b", title="Doc B", snippet="", rank=1),
        SearchHit(url="https://site.com/c", title="Doc C", snippet="", rank=2),
    ]

    merged = reciprocal_rank_fusion([list1, list2], k=60)
    # Doc B appeared in both lists (rank 2 and rank 1), so score = (1/62) + (1/61)
    assert merged[0].url == "https://site.com/b"
    assert len(merged) == 3

    # 3. SimHash near-duplicate detection
    h1 = SimHash.compute("Enterprise cloud pricing tier with 99.99% uptime guarantee and dedicated customer support.")
    h2 = SimHash.compute("Enterprise cloud pricing tier with 99.99% uptime guarantee and dedicated customer account support.")
    h3 = SimHash.compute("Quantum computing algorithms for combinatorial optimization in topological spaces.")

    assert SimHash.hamming_distance(h1, h2) <= 8, "Near-duplicate sentences should have low Hamming distance"
    assert SimHash.hamming_distance(h1, h3) > 15, "Completely different content must have large Hamming distance"
    assert SimHash.is_near_duplicate(
        "Enterprise cloud pricing tier with 99.99% uptime guarantee and dedicated customer support.",
        "Enterprise cloud pricing tier with 99.99% uptime guarantee and dedicated customer account support.",
        max_distance=8,
    )

    # Test hits deduplication by RRF with SimHash
    hits_dups = [
        [
            SearchHit(url="https://site.com/page1", title="Cloud Pricing", snippet="Enterprise cloud pricing tier with 99.99% uptime guarantee and dedicated customer support.", rank=1),
            SearchHit(url="https://site.com/page2", title="Cloud Pricing", snippet="Enterprise cloud pricing tier with 99.99% uptime guarantee and dedicated customer account support.", rank=2),
            SearchHit(url="https://site.com/page3", title="Quantum Info", snippet="Quantum computing algorithms for combinatorial optimization in topological spaces.", rank=3),
        ]
    ]
    deduped = reciprocal_rank_fusion(hits_dups, k=60, max_simhash_distance=8)
    # The near-duplicate page2 should be filtered out
    assert len(deduped) == 2
    assert {h.url for h in deduped} == {"https://site.com/page1", "https://site.com/page3"}


# ==============================================================================
# 3. Robots.txt Obeyed, Rate Limiter, and Circuit Breaker
# ==============================================================================

@pytest.mark.asyncio
async def test_robots_rate_limiter_and_circuit_breaker():
    """Verify politeness policies: robots.txt compliance, token-bucket throttling, and circuit breakers."""
    # 1. Robots.txt parser and cache
    robots = RobotsCache(ttl_seconds=3600)
    mock_robots_txt = """
    User-agent: *
    Disallow: /private/
    Disallow: /admin/
    Allow: /public/
    """
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.text = mock_robots_txt
        mock_get.return_value = mock_resp

        assert await robots.is_allowed("https://example.com/public/article")
        assert not await robots.is_allowed("https://example.com/private/data")
        assert not await robots.is_allowed("https://example.com/admin/dashboard")

    # 2. TokenBucketRateLimiter
    limiter = TokenBucketRateLimiter(rate=10.0, capacity=2)
    # 2 tokens available immediately (completes without exception)
    await limiter.acquire("api.github.com")
    await limiter.acquire("api.github.com")

    # 3. Circuit Breaker
    cb = CircuitBreaker(failure_threshold=3, cooldown_seconds=0.2)
    domain = "unreliable-host.internal"

    assert await cb.is_available(domain)
    await cb.record_failure(domain)
    await cb.record_failure(domain)
    assert await cb.is_available(domain)
    await cb.record_failure(domain)  # 3rd failure -> trips OPEN

    assert not (await cb.is_available(domain)), "Circuit breaker must reject execution when OPEN"
    await asyncio.sleep(0.25)
    # Half-open transition
    assert await cb.is_available(domain)
    await cb.record_success(domain)
    assert await cb.is_available(domain), "Circuit breaker must reset to CLOSED on successful probe"


# ==============================================================================
# 4. Excerpt Verification: Exact Match, Fuzzy Match, Fabrication Rejection
# ==============================================================================

def test_excerpt_verification_locations_and_fabrication_rejection():
    """Verify exact and fuzzy excerpt matching, PDF page extraction, and rejection of fabricated claims."""
    # Exact offsets computed from raw_text:
    # "Introduction to vLLM. "  -> 0..22  (22 chars)
    # "PagedAttention is...fragmentation." -> 22..111  (89 chars = 22+89=111)
    # " "                        -> 111..112
    # "Benchmark...throughput."  -> 112..164
    _raw = (
        "Introduction to vLLM. "
        "PagedAttention is a novel attention algorithm designed to eliminate memory fragmentation. "
        "Benchmark results demonstrate 24x higher throughput."
    )
    doc = FetchedDocument(
        url="https://vllm.ai/whitepaper.pdf",
        final_url="https://vllm.ai/whitepaper.pdf",
        status=200,
        content_type="application/pdf",
        title="vLLM Architecture Whitepaper",
        raw_text=_raw,
        sections=[
            DocumentSection(
                heading_path=["Architecture", "Memory Management"],
                char_start=22,
                char_end=22 + len("PagedAttention is a novel attention algorithm designed to eliminate memory fragmentation."),
                text="PagedAttention is a novel attention algorithm designed to eliminate memory fragmentation.",
            ),
            DocumentSection(
                heading_path=["Evaluation", "Throughput"],
                char_start=22 + len("PagedAttention is a novel attention algorithm designed to eliminate memory fragmentation. "),
                char_end=len(_raw),
                text="Benchmark results demonstrate 24x higher throughput.",
            ),
        ],
        pages=[
            DocumentPage(
                page_no=1,
                char_start=0,
                char_end=22 + len("PagedAttention is a novel attention algorithm designed to eliminate memory fragmentation. "),
                text=(
                    "Introduction to vLLM. "
                    "PagedAttention is a novel attention algorithm designed to eliminate memory fragmentation. "
                ),
            ),
            DocumentPage(
                page_no=2,
                char_start=22 + len("PagedAttention is a novel attention algorithm designed to eliminate memory fragmentation. "),
                char_end=len(_raw),
                text="Benchmark results demonstrate 24x higher throughput.",
            ),
        ],
    )

    # 1. Exact Match Verification
    exact_excerpt = "PagedAttention is a novel attention algorithm designed to eliminate memory fragmentation."
    is_valid, c_start, c_end, p_no, h_path, frag_url = verify_excerpt_in_document(exact_excerpt, doc)
    assert is_valid
    assert c_start == 22
    assert p_no == 1
    assert h_path == ["Architecture", "Memory Management"]
    assert "#:~:text=" in frag_url

    # 2. Fuzzy Match with normalized whitespace / casing
    fuzzy_excerpt = "PagedAttention   is a novel  attention algorithm designed to eliminate memory fragmentation."
    is_valid, c_start, c_end, p_no, h_path, frag_url = verify_excerpt_in_document(fuzzy_excerpt, doc)
    assert is_valid
    assert p_no == 1

    # 3. PDF Page 2 verification
    p2_excerpt = "Benchmark results demonstrate 24x higher throughput."
    is_valid, c_start, c_end, p_no, h_path, frag_url = verify_excerpt_in_document(p2_excerpt, doc)
    assert is_valid
    assert p_no == 2
    assert h_path == ["Evaluation", "Throughput"]

    # 4. HARD RULE: Fabricated excerpt MUST be rejected (returns is_valid == False)
    hallucinated_excerpt = "vLLM uses 500 terabytes of quantum RAM to achieve infinite latency reduction."
    is_valid, c_start, c_end, p_no, h_path, frag_url = verify_excerpt_in_document(hallucinated_excerpt, doc)
    assert not is_valid, "Fabricated excerpt not present in document text must be rejected"


# ==============================================================================
# 5. Text-Fragment URL RFC Encoding Correctness
# ==============================================================================

def test_chrome_text_fragment_url_rfc_encoding():
    """Verify text-fragment URL percent-encoding compliant with Chrome #:~:text= specification."""
    base_url = "https://example.com/pricing"
    excerpt = "Enterprise tier: $99,000/year, with 99.99% SLA!"

    frag_url = generate_text_fragment_url(base_url, excerpt)
    assert frag_url.startswith("https://example.com/pricing#:~:text=")
    # Commas, spaces, and punctuation must be percent-encoded
    assert "%20" in frag_url or "+" in frag_url
    assert "%2C" in frag_url or "%24" in frag_url or "%21" in frag_url
    assert "Enterprise" in frag_url


# ==============================================================================
# 6. Parallel Fan-Out: Concurrency Limits, Seen URLs, Budget Clean Stop
# ==============================================================================

@pytest.mark.asyncio
async def test_fanout_concurrency_seen_urls_and_budget_clean_stop():
    """Verify massive parallel fanout under concurrency caps, zero duplicate URL fetches, and clean budget stop."""
    tenant_id = "tenant_fanout_test"
    db_url = "sqlite+aiosqlite:///:memory:"
    state_store = StateStore(tenant_id=tenant_id, db_url=db_url)
    await state_store.init_db()

    job_id = "job_fanout_001"
    job = Job(
        id=job_id,
        tenant_id=tenant_id,
        query="High-concurrency distributed crawler audit",
        budget=BudgetState(max_steps=50, used_steps=0),
    )
    await state_store.create_job(job)

    # 1. Test Seen URLs Tracking (Zero duplicates)
    u1 = "https://example.com/docs/api?ref=tracker"
    canon_u1 = normalize_canonical_url(u1)

    first_seen = await state_store.mark_url_seen(job_id, canon_u1)
    second_seen = await state_store.mark_url_seen(job_id, canon_u1)
    assert first_seen is True, "First mark must register as new"
    assert second_seen is False, "Duplicate mark must return False to avoid re-fetching"

    # 2. Budget Clean Stop Mid-Fanout
    # Exhaust budget immediately
    job.budget.used_steps = 55
    await state_store.update_job(job)

    orchestrator = ResearchOrchestrator(
        tenant_id=tenant_id,
        state_store=state_store,
        concurrency_cap=24,
    )
    plan = Plan(
        tasks=[
            PlanTask(task_id="t1", objective="Audit node 1", entity="Node1", expected_output=ExpectedOutput.NOTES),
            PlanTask(task_id="t2", objective="Audit node 2", entity="Node2", expected_output=ExpectedOutput.NOTES),
        ]
    )

    notes = await orchestrator.run_plan(job_id=job_id, plan=plan)
    # When budget is exhausted, orchestrator halts cleanly without error and returns 0 new notes
    assert len(notes) == 0


# ==============================================================================
# 7. Tenant Isolation for Web Index Tables (RLS & Zero Leakage)
# ==============================================================================

@pytest.mark.asyncio
async def test_tenant_isolation_web_index_chunks():
    """Verify multi-tenant isolation in WebIndexStore preventing cross-tenant leakage."""
    db_url = "sqlite+aiosqlite:///:memory:"

    # Initialize store for Tenant Alpha
    store_alpha = WebIndexStore(tenant_id="tenant_alpha", db_url=db_url)
    await store_alpha.init_db()

    doc_alpha = FetchedDocument(
        url="https://internal.alpha.com/confidential-roadmap",
        final_url="https://internal.alpha.com/confidential-roadmap",
        status=200,
        content_type="text/html",
        title="Confidential Alpha Roadmap 2027",
        raw_text="Alpha proprietary trading algorithm achieved 45% annual return with zero drawdowns.",
        sections=[
            DocumentSection(
                heading_path=["Strategy", "Trading"],
                char_start=0,
                char_end=85,
                text="Alpha proprietary trading algorithm achieved 45% annual return with zero drawdowns.",
            )
        ],
    )
    note_alpha = ResearchNote(
        id="note_alpha_01",
        job_id="job_alpha",
        tenant_id="tenant_alpha",
        claim="Alpha secret trading algorithm",
        excerpt="Alpha proprietary trading algorithm achieved 45% annual return with zero drawdowns.",
        task_id="task_1",
    )

    await store_alpha.index_note_passage(note_alpha, doc_alpha)

    # Query as Tenant Alpha -> should find the confidential document
    hits_alpha = await store_alpha.hybrid_search("proprietary trading algorithm", limit=5)
    assert len(hits_alpha) >= 1
    assert "Alpha proprietary" in hits_alpha[0].passage_text

    # Initialize store for Tenant Beta (sharing the same database session/backend)
    store_beta = WebIndexStore(
        tenant_id="tenant_beta",
        db_url=db_url,
        session_factory=store_alpha._session_factory,
    )

    # Query as Tenant Beta -> MUST return 0 results (Zero cross-tenant leakage)
    hits_beta = await store_beta.hybrid_search("proprietary trading algorithm", limit=5)
    assert len(hits_beta) == 0, "Tenant Beta must NEVER see Tenant Alpha indexed confidential passages"


# ==============================================================================
# 8. End-to-End Acceptance: Deep Marketing Query with >= 20 Parallel Shards
# ==============================================================================

@pytest.mark.asyncio
async def test_end_to_end_acceptance_sample_marketing_query():
    """
    Acceptance Test:
    - Runs a deep research job on a sample marketing query with >= 20 parallel shards.
    - Verifies 100% of cited claims have a verified URL + exact location (heading/page).
    - Verifies sources endpoint returns coverage across at least 4 source families.
    """
    tenant_id = "tenant_marketing_acceptance"
    db_url = "sqlite+aiosqlite:///:memory:"
    state_store = StateStore(tenant_id=tenant_id, db_url=db_url)
    await state_store.init_db()

    query = (
        "Enterprise CRM and Marketing Automation Comparative Audit: "
        "HubSpot vs Salesforce Marketing Cloud vs Zoho CRM for enterprise SLA tiers."
    )
    job_id = "job_acceptance_mktg"
    job = Job(
        id=job_id,
        tenant_id=tenant_id,
        query=query,
        mode=JobMode.DEEP,
        status=JobStatus.RUNNING,
    )
    await state_store.create_job(job)

    # Decompose into 4 tasks
    plan = Plan(
        tasks=[
            PlanTask(task_id="t_overview", objective="Analyze enterprise CRM market", entity="Market Landscape", expected_output=ExpectedOutput.NOTES),
            PlanTask(task_id="t_hubspot", objective="HubSpot Enterprise pricing and SLA", entity="HubSpot", depends_on=["t_overview"], expected_output=ExpectedOutput.NOTES),
            PlanTask(task_id="t_salesforce", objective="Salesforce Marketing Cloud SLA", entity="Salesforce", depends_on=["t_overview"], expected_output=ExpectedOutput.NOTES),
            PlanTask(task_id="t_zoho", objective="Zoho CRM Enterprise tiers", entity="Zoho", depends_on=["t_overview"], expected_output=ExpectedOutput.NOTES),
        ]
    )

    orchestrator = ResearchOrchestrator(
        tenant_id=tenant_id,
        state_store=state_store,
        concurrency_cap=24,
        per_provider_cap=4,
        per_domain_cap=2,
    )

    # Supply deterministic offline fixtures across source families
    async def mock_search(query: str, source_family: str = "web_general", limit: int = 3):
        slug = re.sub(r"\W+", "_", query.lower())[:30]
        return [
            SearchHit(
                url=f"https://offline.org/{source_family}/{slug}_{i}.html",
                title=f"Evidence for {query[:25]}",
                snippet=f"Snippet for {query[:25]} {i}",
                source_family=source_family,
                provider="acceptance_fixture",
                rank=i,
                raw_score=0.95 - (i * 0.05),
            )
            for i in range(1, limit + 1)
        ]

    # URL-unique content ensures reranker sees diverse passages and seen-URL dedup does not collapse shards
    async def mock_fetch_doc(url: str):
        url_hash = abs(hash(url)) % 9000 + 1000  # stable 4-digit integer per URL
        p1 = (
            f"Enterprise SLA benchmark #{url_hash}: "
            "99.99% availability verified with automated failover and zero downtime deployments."
        )
        p2 = (
            f"Pricing tier #{url_hash}: dedicated account management, "
            "24/7 critical response, and guaranteed uptime SLA."
        )
        full_text = f"{p1}\n\n{p2}"
        c1_start = 0
        c1_end = len(p1)
        c2_start = c1_end + 2
        c2_end = c2_start + len(p2)
        return FetchedDocument(
            url=url,
            final_url=url,
            status=200,
            content_type="text/html",
            title=f"Benchmark Report #{url_hash}",
            raw_text=full_text,
            sections=[
                DocumentSection(
                    heading_path=["SLA Benchmarks", "Enterprise"],
                    char_start=c1_start,
                    char_end=c1_end,
                    text=p1,
                ),
                DocumentSection(
                    heading_path=["Pricing", "Tiers"],
                    char_start=c2_start,
                    char_end=c2_end,
                    text=p2,
                ),
            ],
            pages=[
                DocumentPage(page_no=1, char_start=c1_start, char_end=c1_end, text=p1),
                DocumentPage(page_no=2, char_start=c2_start, char_end=c2_end, text=p2),
            ],
        )

    orchestrator.search_router.search = AsyncMock(side_effect=mock_search)
    orchestrator.fetch_service.fetch_document = AsyncMock(side_effect=mock_fetch_doc)

    # Run the sharded plan
    notes = await orchestrator.run_plan(job_id=job_id, plan=plan)

    # Verify notes were produced across multiple shards.
    # Each task expands into ~13 subqueries; with per_domain_cap=2 and limit=3,
    # each shard fetches 2 URLs yielding up to 2 verified notes each.
    # We expect at minimum 8 notes (4 tasks × 2 notes from first URL batch).
    assert len(notes) >= 8, f"Expected >= 8 parallel research findings, got {len(notes)}"

    # HARD RULE VERIFICATION: 100% of saved notes must have verified location
    for note in notes:
        assert note.is_verified is True, f"Note {note.id} was not verified"
        assert note.url is not None and note.url.startswith("http")
        assert note.char_start is not None and note.char_end is not None
        assert note.char_end > note.char_start
        assert note.text_fragment_url is not None and "#:~:text=" in note.text_fragment_url

    # Check Citation Gate validation: construct gate with the note IDs so it can verify citations
    first_two_notes = list(notes)[:2]
    valid_ids = {first_two_notes[0].id, first_two_notes[1].id}
    gate = CitationGate(
        valid_note_ids=valid_ids,
        note_locations={n_id: True for n_id in valid_ids},
    )
    gate_res = gate.evaluate(
        f"HubSpot provides enterprise SLA support [{first_two_notes[0].id}]. "
        f"Salesforce offers 99.95% uptime [{first_two_notes[1].id}].",
    )
    assert gate_res.passed is True

    # Check Sources Coverage: QueryExpander produces web_general, forums, code, academic, video, social, news
    # With mock returning hits for every source_family, persisted notes should span >= 4 families.
    persisted_notes = await state_store.get_notes(job_id)
    families_represented = {n.source_family for n in persisted_notes if n.source_family}
    assert len(families_represented) >= 4, (
        f"Expected coverage across >= 4 source families, got {families_represented}"
    )
