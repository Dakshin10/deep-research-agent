import asyncio
import pytest
from unittest.mock import AsyncMock, patch

from core.agents.expander import QueryExpander, SubQuery
from core.agents.orchestrator import ResearchOrchestrator
from core.agents.verifier import GapCheckVerifier
from core.fetch.base import FetchedDocument, DocumentSection
from core.search.base import SearchHit
from core.search.reranker import PassageReranker
from core.state.schemas import (
    Brief,
    ExpectedOutput,
    Job,
    JobStatus,
    Plan,
    PlanTask,
    ResearchNote,
    TaskStatus,
)
from core.state.store import StateStore
from core.tools.fetch import PageFetchService
from core.tools.search import SearchService


@pytest.mark.asyncio
async def test_query_expander_diverse_families():
    expander = QueryExpander()
    task = PlanTask(
        task_id="task_1",
        objective="Assess enterprise database security and benchmark latency",
        entity="VectorDB Pro",
        source_hints=["web_search"],
        expected_output=ExpectedOutput.NOTES,
    )
    brief = Brief(
        topic="VectorDB Pro Enterprise Review",
        questions=["Is it secure?"],
        geography="Germany",
    )

    sub_queries = await expander.expand(task, brief=brief, min_queries=5, max_queries=15)
    assert len(sub_queries) >= 5
    assert len(sub_queries) <= 15

    families = {sq.source_family for sq in sub_queries}
    assert "web_general" in families
    assert "forums" in families
    assert "code" in families
    assert "academic" in families
    assert "video" in families

    # Test geography variation was included
    geo_queries = [sq for sq in sub_queries if "Germany" in sq.query]
    assert len(geo_queries) >= 1


def test_passage_reranker_scoring():
    reranker = PassageReranker()
    query = "enterprise pricing and SLA guarantees"

    passages = [
        "The quick brown fox jumps over the lazy dog.",
        "VectorDB Pro Enterprise costs $4,000/mo and guarantees 99.99% uptime SLA.",
        "Our headquarters are located in Berlin and Tokyo.",
    ]

    ranked = reranker.rerank(query, passages, top_k=3)
    assert len(ranked) == 3
    # Top ranked passage must be the enterprise pricing passage
    assert "Enterprise costs $4,000/mo" in ranked[0][0]
    assert ranked[0][1] > ranked[1][1]
    assert ranked[0][1] > ranked[2][1]


@pytest.mark.asyncio
async def test_seen_url_deduplication():
    store = StateStore(tenant_id="default_tenant", db_url="sqlite+aiosqlite:///:memory:")
    await store.init_db()

    job_id = "job_test_seen"
    url = "https://example.com/product?utm_source=twitter"
    canonical = "https://example.com/product"

    # First check: not seen yet
    assert not await store.is_url_seen(job_id, canonical)

    # First mark: is_new should be True
    is_new_1 = await store.mark_url_seen(job_id, canonical)
    assert is_new_1 is True

    # Second check: now it is seen
    assert await store.is_url_seen(job_id, canonical)

    # Second mark: is_new should be False
    is_new_2 = await store.mark_url_seen(job_id, canonical)
    assert is_new_2 is False


@pytest.mark.asyncio
async def test_gap_check_verifier_missing_family():
    verifier = GapCheckVerifier()

    task = PlanTask(
        task_id="task_1",
        objective="Analyze cloud architecture",
        entity="CloudX",
        expected_output=ExpectedOutput.NOTES,
    )
    plan = Plan(brief_id="brief_1", tasks=[task])

    # Case 1: Task has no notes at all
    res1 = await verifier.verify_gaps(plan, notes=[], extra_research_rounds=0)
    assert res1.needs_more_research is True
    assert len(res1.extra_tasks) == 1
    assert "followup" in res1.extra_tasks[0].task_id

    # Case 2: Notes exist, but missing critical 'forums' family coverage
    notes = [
        ResearchNote(
            id=f"n{i}",
            job_id="j1",
            tenant_id="t1",
            claim=f"Claim {i}",
            excerpt=f"Excerpt {i}",
            source_type="web",
            task_id="task_1",
            source_family="web_general",
            is_verified=True,
        )
        for i in range(3)
    ]

    res2 = await verifier.verify_gaps(plan, notes=notes, extra_research_rounds=0)
    assert res2.needs_more_research is True
    assert len(res2.extra_tasks) == 1
    assert "gap_family_forums" in res2.extra_tasks[0].task_id

    # Case 3: Already had 1 extra round -> must be bounded
    res3 = await verifier.verify_gaps(plan, notes=notes, extra_research_rounds=1)
    assert res3.needs_more_research is False
    assert len(res3.extra_tasks) == 0


@pytest.mark.asyncio
async def test_sharded_orchestrator_execution():
    store = StateStore(tenant_id="default_tenant", db_url="sqlite+aiosqlite:///:memory:")
    await store.init_db()

    job_id = "job_fanout_test"
    job = Job(
        id=job_id,
        tenant_id="default_tenant",
        query="Cloud Scale",
        title="Fanout Test",
        brief=Brief(topic="Cloud Scale", questions=["Performance?"]),
        status=JobStatus.RUNNING,
    )
    await store.create_job(job)

    # Mock Search Service
    mock_search = AsyncMock()
    mock_search.router = AsyncMock()
    mock_search.router.search = AsyncMock(
        return_value=[
            SearchHit(
                url="https://cloudx.org/benchmarks",
                title="CloudX Benchmarks",
                snippet="CloudX throughput hits 100k queries per second.",
                source_family="web_general",
                provider="mock",
                rank=1,
            ),
            SearchHit(
                url="https://cloudx.org/pricing",
                title="CloudX Pricing",
                snippet="Pricing starts at $99 per node.",
                source_family="web_general",
                provider="mock",
                rank=2,
            ),
        ]
    )

    # Mock Fetch Service
    doc_text = "CloudX throughput hits 100k queries per second under high concurrency workloads. Enterprise support is available."
    mock_fetch = AsyncMock()
    mock_fetch.fetch_document = AsyncMock(
        return_value=FetchedDocument(
            url="https://cloudx.org/benchmarks",
            final_url="https://cloudx.org/benchmarks",
            status=200,
            content_type="text/html",
            raw_text=doc_text,
            title="CloudX Benchmarks",
            sections=[
                DocumentSection(
                    heading_path=["Benchmarks"],
                    char_start=0,
                    char_end=len(doc_text),
                    text=doc_text,
                )
            ],
        )
    )

    orchestrator = ResearchOrchestrator(
        tenant_id="default_tenant",
        state_store=store,
        concurrency_cap=4,
        per_provider_cap=2,
        per_domain_cap=1,
        search_service=mock_search,
        fetch_service=mock_fetch,
        search_router=mock_search.router,
    )

    plan = Plan(
        brief_id="brief_test",
        tasks=[
            PlanTask(
                task_id="task_1",
                objective="Evaluate throughput performance",
                entity="CloudX",
                expected_output=ExpectedOutput.NOTES,
            )
        ],
    )

    notes = await orchestrator.run_plan(job_id=job_id, plan=plan)

    # Verify that research notes were produced and verified
    assert len(notes) >= 1
    for note in notes:
        assert note.is_verified is True
        assert note.char_start is not None
        assert note.char_end is not None
        assert note.text_fragment_url is not None
        assert "cloudx.org" in (note.url or "")


@pytest.mark.asyncio
async def test_orchestrator_budget_clean_stop():
    store = StateStore(tenant_id="default_tenant", db_url="sqlite+aiosqlite:///:memory:")
    await store.init_db()

    job_id = "job_budget_test"
    job = Job(
        id=job_id,
        tenant_id="default_tenant",
        query="Exhaustion",
        title="Budget Test",
        brief=Brief(topic="Exhaustion", questions=["Exhaust?"]),
        status=JobStatus.RUNNING,
    )
    await store.create_job(job)

    # Artificially exhaust the job budget
    job = await store.get_job(job_id)
    job.budget.max_steps = 1
    job.budget.used_steps = 1
    job.budget.exhausted = True
    await store.update_job(job)

    orchestrator = ResearchOrchestrator(
        tenant_id="default_tenant",
        state_store=store,
        concurrency_cap=2,
    )

    plan = Plan(
        brief_id="brief_test",
        tasks=[
            PlanTask(
                task_id="task_1",
                objective="Should stop due to budget",
                entity="BudgetTest",
                expected_output=ExpectedOutput.NOTES,
            )
        ],
    )

    notes = await orchestrator.run_plan(job_id=job_id, plan=plan)
    # With budget exhausted at start of shard execution, no notes should be generated
    assert len(notes) == 0
