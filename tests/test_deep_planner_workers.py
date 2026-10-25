import pytest
from core.agents.clarifier import ClarifierAgent
from core.agents.planner import PlannerAgent
from core.agents.orchestrator import ResearchOrchestrator
from core.state.store import StateStore
from core.state.schemas import Job, JobStatus, JobMode, TaskStatus, Brief


@pytest.mark.asyncio
async def test_3_competitor_deep_research_workflow():
    """
    Test Step 4 requirement:
    A 3-competitor request produces plan and notes end to end.
    Verifies Clarifier, Planner, Orchestrator, Workers, and Notes Table.
    """
    tenant_id = "tenant_agency_audit"
    db_url = "sqlite+aiosqlite:///:memory:"
    state_store = StateStore(tenant_id=tenant_id, db_url=db_url)
    await state_store.init_db()

    query = (
        "Comprehensive competitive research and performance audit comparing "
        "HubSpot, Salesforce, and Zoho CRM for mid-market B2B marketing automation."
    )

    # 1. Initialize Job in StateStore
    job = Job(
        tenant_id=tenant_id,
        query=query,
        mode=JobMode.DEEP,
        status=JobStatus.RUNNING,
    )
    await state_store.create_job(job)

    # 2. Test Clarifier Agent
    clarifier = ClarifierAgent()
    brief, needs_interrupt, payload = await clarifier.process(query=query)

    # Verify competitors detected
    assert "Hubspot" in brief.named_competitors or "HubSpot" in [c.title() for c in brief.named_competitors]
    assert "Salesforce" in [c.title() for c in brief.named_competitors]
    assert "Zoho" in [c.title() for c in brief.named_competitors]

    # If missing fields exist, simulate user providing clarification
    if needs_interrupt:
        user_clarification = "Target geography is North America, audience is B2B Mid-Market CMOs."
        brief, needs_interrupt, _ = await clarifier.process(
            query=query,
            existing_brief=brief,
            user_response=user_clarification,
        )

    assert brief.geography is not None
    job.brief = brief
    await state_store.update_job(job)

    # 3. Test Planner Agent
    planner = PlannerAgent()
    plan = await planner.create_plan(query=query, brief=brief, tenant_id=tenant_id)

    # Validate Plan constraints
    assert len(plan.tasks) <= 8
    assert len(plan.tasks) >= 3, "Plan must decompose into at least 3 tasks for competitors"

    # Verify tasks cover the entities
    entities = [t.entity.lower() for t in plan.tasks]
    assert any("hubspot" in e for e in entities)
    assert any("salesforce" in e for e in entities)
    assert any("zoho" in e for e in entities)

    # Verify dependency mapping exists
    has_dependencies = any(len(t.depends_on) > 0 for t in plan.tasks)
    assert has_dependencies, "Planner must honor depends_on relationships"

    job.plan = plan
    await state_store.update_job(job)

    # 4. Test Orchestrator & Concurrent Workers
    orchestrator = ResearchOrchestrator(
        tenant_id=tenant_id,
        state_store=state_store,
        concurrency_cap=4,
    )

    notes = await orchestrator.run_plan(job_id=job.id, plan=plan)

    # 5. Verify Workers produce structured notes (NO free text)
    assert len(notes) > 0, "Workers must produce structured research notes"
    for note in notes:
        assert note.claim is not None and len(note.claim) > 5
        assert note.source_type in ["web", "kb", "mcp", "reddit", "computed"]
        assert note.excerpt is not None
        assert note.confidence >= 0.0 and note.confidence <= 1.0
        assert note.task_id is not None

    # 6. Verify Notes Table in StateStore (persisted in DB)
    persisted_notes = await state_store.get_notes(job.id)
    assert len(persisted_notes) == len(notes)

    # Check competitor notes exist in persisted store
    persisted_claims = " ".join([n.claim.lower() for n in persisted_notes])
    assert "hubspot" in persisted_claims
    assert "salesforce" in persisted_claims
    assert "zoho" in persisted_claims

    # 7. Verify Task Status Progress Checklist in Job
    refreshed_job = await state_store.get_job(job.id)
    assert refreshed_job is not None
    assert refreshed_job.plan is not None
    for task in refreshed_job.plan.tasks:
        assert task.status == TaskStatus.COMPLETED, f"Task {task.task_id} not marked completed"
