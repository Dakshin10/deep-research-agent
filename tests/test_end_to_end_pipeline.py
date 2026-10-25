import os
import re
import pytest
from langgraph.types import Command
from langgraph.checkpoint.memory import InMemorySaver

from core.graph.builder import ResearchGraphBuilder
from core.state.store import StateStore
from core.state.schemas import Job, JobStatus, JobMode, BudgetState, ResearchNote
from core.observability.tracing import get_tracer

SAMPLE_MARKETING_CSV = b"""campaign,impressions,clicks,spend,conversions,revenue
SaaS_Search_Intent,150000,7500,3750.00,300,18750.00
LinkedIn_ABM_Display,250000,5000,4000.00,200,12000.00
YouTube_Product_Demo,600000,12000,9000.00,250,22500.00
"""


@pytest.mark.asyncio
async def test_end_to_end_research_pipeline_vague_deep_request():
    """
    Test Step 7 requirement:
    Runs a vague deep request end-to-end through:
      1. Clarify (HITL interrupt)
      2. Plan & source routing
      3. Parallel research workers
      4. Quantitative CSV analysis in sandbox (notes+table/chart)
      5. Synthesis writing
      6. Citation gate
      7. Compliance gate
      8. Delivery & artifact storage (MinIO + PPTX)
    Then asserts every single claim in the delivered report maps directly to a verified note.
    """
    tenant_id = "tenant_e2e_agency"
    job_id = "job_e2e_full_pipeline"
    db_url = "sqlite+aiosqlite:///:memory:"

    # 1. Initialize StateStore and seed job
    store = StateStore(tenant_id=tenant_id, db_url=db_url)
    await store.init_db()

    job = Job(
        id=job_id,
        tenant_id=tenant_id,
        query="Analyze competitive marketing efficiency and campaign ROI for enterprise expansion",
        mode=JobMode.CLARIFY,
        status=JobStatus.RUNNING,
        budget=BudgetState(max_steps=25, max_tokens=100000, max_seconds=300.0),
    )
    await store.create_job(job)

    # 2. Build graph with in-memory checkpointer for deterministic isolated test run
    checkpointer = InMemorySaver()
    builder = ResearchGraphBuilder(checkpointer=checkpointer)
    graph = builder.build()

    config = {"configurable": {"thread_id": job_id}}

    initial_state = {
        "job_id": job_id,
        "tenant_id": tenant_id,
        "query": job.query,
        "mode": "clarify",
        "stage": "started",
        "input_files": {"campaigns.csv": SAMPLE_MARKETING_CSV},
        "budget": job.budget.model_dump(),
        "extra_research_rounds": 0,
    }

    # 3. Step 1: Run graph until HITL clarification interrupt
    interrupt_res = await graph.ainvoke(initial_state, config=config)
    assert "__interrupt__" in interrupt_res, "Graph must pause and interrupt on ambiguous/vague deep inquiry"

    interrupt_data = interrupt_res["__interrupt__"][0].value
    assert "questions" in interrupt_data
    assert len(interrupt_data["questions"]) > 0

    # 4. Step 2: Resume with user clarification
    clarification_input = (
        "Audience: Enterprise B2B SaaS buyers and CMOs; "
        "Geography: North America and Europe; "
        "Goal KPI: Maximize Return on Ad Spend (ROAS) and lower Customer Acquisition Cost"
    )

    resume_command = Command(resume=clarification_input)
    final_state = await graph.ainvoke(resume_command, config=config)

    # 5. Verify Workflow Completion and Stages
    assert final_state.get("done") is True, f"Workflow failed to complete: {final_state.get('error')}"
    assert final_state.get("stage") == "completed"

    # 6. Verify Analyst Node executed CSV computation in sandbox
    raw_notes = final_state.get("notes", [])
    assert len(raw_notes) >= 3, f"Expected research notes, got {len(raw_notes)}"

    computed_notes = [n for n in raw_notes if n.get("source_type") == "computed"]
    assert len(computed_notes) >= 3, "Analyst node must produce computed notes from campaigns.csv"

    # Verify exact math computed from CSV:
    # Total spend: 3750 + 4000 + 9000 = 16750.0
    # Total revenue: 18750 + 12000 + 22500 = 53250.0
    # Total ROAS = 53250 / 16750 = 3.18
    computed_claims_str = " ".join([n.get("claim", "") for n in computed_notes])
    assert "16750" in computed_claims_str, f"Missing total spend 16750 in computed notes: {computed_claims_str}"
    assert "3.18" in computed_claims_str, f"Missing total ROAS 3.18 in computed notes: {computed_claims_str}"

    # 7. Verify Gates
    assert final_state.get("gate_passed") is True, f"Citation gate must pass: {final_state.get('gate_issues')}"
    assert final_state.get("compliance_passed") is True, "Compliance gate must pass"

    # 8. Verify Delivery Artifacts
    delivered = final_state.get("delivered_artifacts", [])
    assert len(delivered) >= 2, "Delivered artifacts must contain report and presentation deck"
    art_types = [a.get("artifact_type") for a in delivered]
    assert "report" in art_types
    assert "presentation" in art_types

    # 9. Verify Groundedness: Every bracket claim [note_...] in report maps to a real note
    report_text = final_state.get("report", "")
    assert len(report_text) > 200, "Delivered report must contain comprehensive text"

    cited_brackets = re.findall(r"\[(note_[a-zA-Z0-9_]+)\]", report_text)
    assert len(cited_brackets) > 0, "Report must contain citations"

    valid_note_ids = {n.get("id") for n in raw_notes if n.get("id")}
    for cite in cited_brackets:
        assert cite in valid_note_ids, f"Groundedness failure: Citation [{cite}] does not map to any verified note"

    # 10. Verify Observability Traces
    tracer = get_tracer()
    traces = tracer.get_traces()
    agent_traces = {t.name for t in traces if t.trace_type == "agent"}
    assert "planner" in agent_traces
    assert "workers" in agent_traces
    assert "analyst" in agent_traces
    assert "writer" in agent_traces
    assert "deliver" in agent_traces
