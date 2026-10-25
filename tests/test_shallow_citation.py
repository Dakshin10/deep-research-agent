import pytest
from core.agents.classifier import IntentClassifier
from core.agents.shallow import ShallowResearchAgent
from core.guardrails.citation_gate import CitationGate
from core.state.store import StateStore
from core.state.schemas import Job, JobStatus, JobMode


LOOKUP_QUESTIONS_20 = [
    "What is the average B2B email open rate in 2024?",
    "What is the typical customer acquisition cost (CAC) in FinTech SaaS?",
    "What was HubSpot's revenue growth in FY2024?",
    "What is the average click-through rate (CTR) for Google Search Ads in eCommerce?",
    "What percentage of marketing budgets is spent on generative AI tools?",
    "What is the average ROAS for Facebook video ads in retail?",
    "How much did enterprise spend on influencer marketing increase in 2024?",
    "What is the standard conversion rate benchmark for B2B landing pages?",
    "What is the average cost-per-click (CPC) on LinkedIn sponsored content?",
    "What was Salesforce's reported marketing cloud expansion rate?",
    "What is the median churn rate for mid-market subscription software?",
    "What is the adoption percentage of marketing automation among Fortune 500?",
    "What was the year-over-year market growth for retail media networks?",
    "What is the average retention rate for omnichannel retail campaigns?",
    "What is the benchmark bounce rate for professional services websites?",
    "What is the estimated market size of global digital marketing by 2026?",
    "What is the typical discount margin offered in enterprise SaaS renewals?",
    "What is the average response time for lead qualification in top B2B agencies?",
    "What percentage of marketing leaders prioritize first-party data strategies?",
    "What is the average ROI per dollar spent on email marketing in 2024?",
]


@pytest.mark.asyncio
async def test_intent_classifier():
    """Verify that intent classifier properly distinguishes shallow vs deep vs chit-chat."""
    classifier = IntentClassifier()

    res_chit = await classifier.classify("Hello! How are you doing today?")
    assert res_chit.mode == JobMode.CHIT_CHAT

    res_deep = await classifier.classify("Comprehensive competitor audit and market landscape for CRM")
    assert res_deep.mode in [JobMode.DEEP, JobMode.CLARIFY]

    res_shallow = await classifier.classify("What is the average B2B CPC?")
    assert res_shallow.mode in [JobMode.SHALLOW, JobMode.DEEP]


@pytest.mark.asyncio
async def test_20_lookup_questions_return_valid_citations():
    """
    Test Step 3 requirement:
    20 lookup questions return valid citations verified via CitationGate v1.
    """
    tenant_id = "tenant_shallow_suite"
    state_store = StateStore(tenant_id=tenant_id, db_url="sqlite+aiosqlite:///:memory:")
    await state_store.init_db()

    shallow_agent = ShallowResearchAgent(
        tenant_id=tenant_id,
        state_store=state_store,
        max_tool_calls=6,
    )

    for i, question in enumerate(LOOKUP_QUESTIONS_20, 1):
        job = Job(
            tenant_id=tenant_id,
            query=question,
            mode=JobMode.SHALLOW,
            status=JobStatus.RUNNING,
        )
        await state_store.create_job(job)

        result = await shallow_agent.execute(job_id=job.id, query=question)

        # 1. Answer must be non-empty
        assert result.report is not None and len(result.report) > 20, f"Empty report for query {i}: {question}"

        # 2. Must produce notes and valid citations
        assert len(result.notes) > 0, f"No notes generated for query {i}: {question}"
        assert len(result.citations) > 0, f"No citations found for query {i}: {question}"

        # 3. Every citation must map to an existing note ID
        existing_note_ids = {n.id for n in result.notes}
        for cite_id in result.citations:
            assert cite_id in existing_note_ids, f"Orphaned citation {cite_id} in query {i}"

        # 4. Strict CitationGate evaluation
        gate = CitationGate(valid_note_ids=existing_note_ids, strict=True)
        eval_result = gate.evaluate(result.report)
        assert eval_result.passed is True, (
            f"Citation gate failed on query {i} '{question}': {eval_result.flagged_issues}"
        )

        # 5. Tool calls must obey budget (<= 6)
        assert result.tool_calls_used <= 6
