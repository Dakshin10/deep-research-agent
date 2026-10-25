import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock
import pytest

from core.fetch.base import FetchedDocument, DocumentSection
from core.knowledge.web_index import WebIndexStore, WebIndexProvider, WebIndexHit
from core.state.schemas import ResearchNote
from core.tools.registry import DataSourceRegistry


@pytest.mark.asyncio
async def test_web_index_ingestion_and_hybrid_retrieval():
    store = WebIndexStore(tenant_id="tenant_alpha", db_url="sqlite+aiosqlite:///:memory:")
    await store.init_db()

    # 1. Ingest verified note passage
    note = ResearchNote(
        id="note_idx_1",
        job_id="job_idx_1",
        task_id="task_idx_1",
        tenant_id="tenant_alpha",
        claim="VectorDB Pro achieves sub-10ms latency on 100M vectors.",
        excerpt="VectorDB Pro achieves sub-10ms latency on 100M vectors under high concurrent load.",
        source_type="web",
        url="https://vectordb.example.com/benchmarks",
        title="VectorDB Performance Report",
        source_family="academic",
        char_start=150,
        char_end=235,
        heading_path=["Benchmarks", "Latency"],
        text_fragment_url="https://vectordb.example.com/benchmarks#:~:text=VectorDB%20Pro%20achieves",
        is_verified=True,
    )
    cid = await store.index_note_passage(note)
    assert cid.startswith("widx_")

    # 2. Ingest structured FetchedDocument with sections
    doc_text = "Pricing tiers for Enterprise start at $3,500/month with 99.99% uptime SLA guarantee."
    doc = FetchedDocument(
        url="https://vectordb.example.com/pricing",
        final_url="https://vectordb.example.com/pricing",
        status=200,
        content_type="text/html",
        title="VectorDB Pricing",
        raw_text=doc_text,
        sections=[
            DocumentSection(
                heading_path=["Pricing", "Enterprise"],
                char_start=0,
                char_end=len(doc_text),
                text=doc_text,
            )
        ],
    )
    doc_cids = await store.index_document(doc, source_family="web_general")
    assert len(doc_cids) == 1

    # 3. Hybrid search: Query matching benchmark latency
    latency_hits = await store.hybrid_search("latency 100M vectors benchmark", limit=3)
    assert len(latency_hits) >= 1
    top_hit = latency_hits[0]
    assert "VectorDB Pro achieves" in top_hit.passage_text
    assert top_hit.source_family == "academic"
    assert top_hit.heading_path == ["Benchmarks", "Latency"]
    assert top_hit.char_start == 150
    assert top_hit.char_end == 235

    # 4. Hybrid search: Query matching enterprise pricing
    pricing_hits = await store.hybrid_search("enterprise pricing SLA uptime guarantee", limit=3)
    assert len(pricing_hits) >= 1
    assert "$3,500/month" in pricing_hits[0].passage_text


@pytest.mark.asyncio
async def test_web_index_tenant_isolation_zero_leakage():
    db_url = "sqlite+aiosqlite:///:memory:"
    # Use shared engine/session factory for SQLite in-memory multi-tenant test
    store_a = WebIndexStore(tenant_id="tenant_secret_corp", db_url=db_url)
    await store_a.init_db()

    store_b = WebIndexStore(
        tenant_id="tenant_competitor_inc",
        db_url=db_url,
        session_factory=store_a._session_factory,
    )

    # Tenant A indexes confidential roadmap note
    note = ResearchNote(
        id="note_confidential_1",
        job_id="job_secret",
        task_id="task_conf",
        tenant_id="tenant_secret_corp",
        claim="Secret Corp Q4 product roadmap reveals quantum encryption feature.",
        excerpt="Secret Corp Q4 product roadmap reveals quantum encryption feature scheduled for release.",
        source_type="web",
        url="https://internal.secret.org/roadmap",
        is_verified=True,
    )
    await store_a.index_note_passage(note)

    # Tenant A can retrieve its note
    hits_a = await store_a.hybrid_search("quantum encryption roadmap")
    assert len(hits_a) == 1
    assert "quantum encryption" in hits_a[0].passage_text

    # Tenant B queries the exact same terms: MUST return ZERO results (zero leakage)
    hits_b = await store_b.hybrid_search("quantum encryption roadmap")
    assert len(hits_b) == 0, "Cross-tenant leakage detected! Tenant B saw Tenant A index data."


@pytest.mark.asyncio
async def test_web_index_source_family_filtering():
    store = WebIndexStore(tenant_id="tenant_multi_family", db_url="sqlite+aiosqlite:///:memory:")
    await store.init_db()

    doc_academic = FetchedDocument(
        url="https://arxiv.org/abs/2401.0001",
        final_url="https://arxiv.org/abs/2401.0001",
        status=200,
        content_type="text/html",
        title="Deep Learning Optimization",
        raw_text="Paper methodology analyzes stochastic gradient descent convergence in deep architectures.",
    )
    doc_forums = FetchedDocument(
        url="https://reddit.com/r/MachineLearning/comments/123",
        final_url="https://reddit.com/r/MachineLearning/comments/123",
        status=200,
        content_type="text/html",
        title="Reddit ML Discussion",
        raw_text="Community discussion analyzes stochastic gradient descent convergence practical tricks.",
    )

    await store.index_document(doc_academic, source_family="academic")
    await store.index_document(doc_forums, source_family="forums")

    # Filter by academic: should only return academic
    academic_hits = await store.hybrid_search("stochastic gradient descent", source_family="academic")
    assert len(academic_hits) == 1
    assert academic_hits[0].source_family == "academic"
    assert "arxiv.org" in academic_hits[0].url

    # Filter by forums: should only return forums
    forum_hits = await store.hybrid_search("stochastic gradient descent", source_family="forums")
    assert len(forum_hits) == 1
    assert forum_hits[0].source_family == "forums"
    assert "reddit.com" in forum_hits[0].url


@pytest.mark.asyncio
async def test_web_index_stale_marking_and_recrawl():
    store = WebIndexStore(tenant_id="tenant_lifecycle", db_url="sqlite+aiosqlite:///:memory:")
    await store.init_db()

    doc = FetchedDocument(
        url="https://news-site.org/breaking",
        final_url="https://news-site.org/breaking",
        status=200,
        content_type="text/html",
        title="Breaking News Article",
        raw_text="Original breaking story published with early facts and initial witness accounts.",
    )
    await store.index_document(doc, source_family="news")

    # Entry is fresh initially
    fresh_hits = await store.hybrid_search("breaking story initial accounts")
    assert len(fresh_hits) == 1
    assert fresh_hits[0].is_stale is False

    # Simulate passage being 5 days old (exceeds news TTL of 1 day)
    from core.state.models import WebIndexChunkModel
    from sqlalchemy import select
    async with await store.get_session() as session:
        stmt = select(WebIndexChunkModel).where(WebIndexChunkModel.tenant_id == "tenant_lifecycle")
        res = await session.execute(stmt)
        record = res.scalars().first()
        record.updated_at = datetime.now(timezone.utc) - timedelta(days=5)
        await session.commit()

    # Audit and mark stale entries
    stale_count = await store.mark_stale_entries()
    assert stale_count == 1

    # Stale entry must be filtered out of regular search
    search_after_stale = await store.hybrid_search("breaking story initial accounts", include_stale=False)
    assert len(search_after_stale) == 0

    # Search with include_stale=True can still retrieve it
    search_stale_included = await store.hybrid_search("breaking story initial accounts", include_stale=True)
    assert len(search_stale_included) == 1
    assert search_stale_included[0].is_stale is True

    # Re-crawl stale entries with mock fetch service
    mock_fetcher = AsyncMock()
    updated_doc_text = "Updated comprehensive report on breaking story with official statements and final casualty figures."
    mock_fetcher.fetch_document = AsyncMock(
        return_value=FetchedDocument(
            url="https://news-site.org/breaking",
            final_url="https://news-site.org/breaking",
            status=200,
            content_type="text/html",
            title="Breaking News Article (Updated)",
            raw_text=updated_doc_text,
        )
    )

    refreshed_count = await store.recrawl_stale_entries(mock_fetcher, limit=5)
    assert refreshed_count == 1

    # After re-crawl, fresh entry is now retrievable and marked is_stale=False
    refreshed_hits = await store.hybrid_search("official statements casualty figures", include_stale=False)
    assert len(refreshed_hits) == 1
    assert refreshed_hits[0].is_stale is False
    assert "official statements" in refreshed_hits[0].passage_text


@pytest.mark.asyncio
async def test_web_index_search_provider_adapter():
    store = WebIndexStore(tenant_id="tenant_adapter_test", db_url="sqlite+aiosqlite:///:memory:")
    await store.init_db()

    note = ResearchNote(
        id="note_test_1",
        job_id="job_test_1",
        task_id="task_adapter",
        tenant_id="tenant_adapter_test",
        claim="Autonomous agents reduce manual review hours by 72 percent.",
        excerpt="Autonomous agents reduce manual review hours by 72 percent in production testing.",
        source_type="web",
        url="https://agents-ai.org/study",
        title="Agentic Productivity Study",
        source_family="academic",
        char_start=50,
        char_end=140,
        is_verified=True,
    )
    await store.index_note_passage(note)

    provider = WebIndexProvider(web_index_store=store)
    hits = await provider.search("autonomous agents manual review hours", limit=3)
    assert len(hits) == 1

    hit = hits[0]
    assert hit.provider == "web_index"
    assert hit.source_family == "academic"
    assert "[Local Index]" in hit.title
    assert hit.raw["char_start"] == 50
    assert hit.raw["char_end"] == 140


def test_web_index_in_datasource_registry():
    registry = DataSourceRegistry()
    source = registry.get_source("web_index")
    assert source is not None
    assert source.read_only is True

    # Test tool building for a tenant
    tools = source.build_tools(tenant_id="tenant_xyz")
    assert len(tools) == 1
    assert callable(tools[0])
