import pytest
from core.agents.verifier import GapCheckVerifier
from core.agents.writer import WriterAgent
from core.agents.followup import FollowupAgent
from core.guardrails.citation_gate import CitationGate
from core.state.store import StateStore
from core.state.schemas import (
    Job,
    JobStatus,
    JobMode,
    Plan,
    PlanTask,
    ResearchNote,
    ExpectedOutput,
    Brief,
)


@pytest.mark.asyncio
async def test_gap_check_verifier_bounds():
    """Verify gap check triggers at most one extra round of tasks."""
    verifier = GapCheckVerifier()

    plan = Plan(
        tasks=[
            PlanTask(task_id="t1", objective="Market scan", entity="Market"),
            PlanTask(task_id="t2", objective="Missing task", entity="Entity B"),
        ]
    )

    notes = [
        ResearchNote(
            id="n1",
            job_id="j1",
            tenant_id="ten1",
            claim="Market growth verified",
            excerpt="Excerpt",
            task_id="t1",
        )
    ]

    # Round 0: should detect gap for t2 and request extra research
    res0 = await verifier.verify_gaps(plan=plan, notes=notes, extra_research_rounds=0)
    assert res0.needs_more_research is True
    assert len(res0.extra_tasks) == 1
    assert "t2" in res0.extra_tasks[0].task_id

    # Round 1: strictly bounded; must NOT allow a second extra round
    res1 = await verifier.verify_gaps(plan=plan, notes=notes, extra_research_rounds=1)
    assert res1.needs_more_research is False
    assert len(res1.extra_tasks) == 0


@pytest.mark.asyncio
async def test_full_teardown_report_every_claim_maps_to_note():
    """
    Test Step 5 requirement:
    Full teardown report where every quantitative, comparative, or superlative claim maps to a note.
    Follow-up query answered without re-running research.
    """
    tenant_id = "tenant_teardown_suite"
    db_url = "sqlite+aiosqlite:///:memory:"
    state_store = StateStore(tenant_id=tenant_id, db_url=db_url)
    await state_store.init_db()

    query = "Enterprise CRM Teardown: HubSpot vs Salesforce vs Zoho"
    job = Job(
        tenant_id=tenant_id,
        query=query,
        mode=JobMode.DEEP,
        status=JobStatus.RUNNING,
    )
    await state_store.create_job(job)

    # Seed structured research notes covering competitors and metrics
    notes_data = [
        ("note_hs1", "task_hs", "HubSpot: Annual recurring revenue grew by 21.4% in 2024", "https://hubspot.com/investor"),
        ("note_hs2", "task_hs", "HubSpot: Professional marketing tier starts at $800 monthly", "https://hubspot.com/pricing"),
        ("note_sf1", "task_sf", "Salesforce: Enterprise Marketing Cloud adoption reached 62% in North America", "https://salesforce.com/cloud"),
        ("note_sf2", "task_sf", "Salesforce: Custom deployment cycles average 4.5 months for mid-market", "https://salesforce.com/cases"),
        ("note_zh1", "task_zh", "Zoho: CRM Plus edition offers 40% lower TCO compared to enterprise rivals", "https://zoho.com/crm"),
        ("note_zh2", "task_zh", "Zoho: Retained over 85% customer satisfaction in SMB customer surveys", "https://zoho.com/reports"),
        ("note_mkt", "task_mkt", "Market Overview: B2B marketing automation spending increased by 19.2% overall", "https://gartner.com/mkt"),
    ]

    seeded_notes: list[ResearchNote] = []
    for nid, tid, claim, url in notes_data:
        note = ResearchNote(
            id=nid,
            job_id=job.id,
            tenant_id=tenant_id,
            claim=claim,
            source_type="web",
            source_url=url,
            excerpt=f"Full excerpt text validating claim: {claim}",
            confidence=0.96,
            task_id=tid,
        )
        await state_store.add_note(note)
        seeded_notes.append(note)

    # 1. Writer Agent generates teardown report
    writer = WriterAgent(tenant_id=tenant_id, state_store=state_store)
    brief = Brief(audience="B2B CMOs", geography="North America", goal_kpi="Market share expansion")
    report = await writer.write_report(
        job_id=job.id,
        query=query,
        brief=brief,
        notes=seeded_notes,
    )

    assert report is not None
    assert len(report) > 300
    job.report = report
    job.status = JobStatus.COMPLETED
    await state_store.update_job(job)

    # 2. Strict Citation Gate Validation: Every quantitative/comparative claim MUST map to a note
    valid_note_ids = {n.id for n in seeded_notes}
    gate = CitationGate(valid_note_ids=valid_note_ids, strict=True)
    gate_result = gate.evaluate(report)

    assert gate_result.passed is True, f"Citation gate found unlinked claims: {gate_result.flagged_issues}"
    assert len(gate_result.valid_citations_found) >= 4, "Report must link multiple verified note citations"

    # Every cited note ID must exist in our seeded notes
    for cite in gate_result.valid_citations_found:
        assert cite in valid_note_ids, f"Cited note {cite} not in registered notes"

    # 3. Artifact Persistence
    artifacts = await state_store.get_artifacts(job.id)
    report_artifacts = [a for a in artifacts if a.artifact_type == "report"]
    assert len(report_artifacts) == 1
    assert report_artifacts[0].content == report

    # 4. Report Follow-Up
    followup_agent = FollowupAgent(tenant_id=tenant_id, state_store=state_store)
    followup_q = "What is HubSpot's professional tier monthly price?"
    followup_ans = await followup_agent.answer_followup(job_id=job.id, question=followup_q)

    assert followup_ans is not None and len(followup_ans) > 20
    assert "note_hs2" in followup_ans or "800" in followup_ans or "note_" in followup_ans
