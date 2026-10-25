import asyncio
import json
import os
import pytest
from httpx import AsyncClient, ASGITransport

from apps.api.main import app
from core.state.store import StateStore
from core.state.schemas import Job, JobStatus, JobMode, EventType


@pytest.mark.asyncio
async def test_job_creation_and_retrieval():
    """Test creating a research job via the API and retrieving its state."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = {
            "query": "Market analysis of enterprise AI agents in 2025",
            "mode": "shallow",
        }
        headers = {"X-Tenant-ID": "tenant_test_1"}

        # 1. Create Job
        resp = await client.post("/v1/jobs", json=payload, headers=headers)
        assert resp.status_code == 202
        data = resp.json()
        job_id = data["id"]
        assert job_id.startswith("job_")
        assert data["tenant_id"] == "tenant_test_1"

        # 2. Wait a moment for background execution
        await asyncio.sleep(0.5)

        # 3. Retrieve Job
        get_resp = await client.get(f"/v1/jobs/{job_id}", headers=headers)
        assert get_resp.status_code == 200
        job_data = get_resp.json()
        assert job_data["id"] == job_id
        assert job_data["status"] in ["running", "completed"]


@pytest.mark.asyncio
async def test_sse_event_streaming():
    """Test SSE event streaming from a running research job."""
    tenant_id = "tenant_stream_test"
    store = StateStore(tenant_id=tenant_id, db_url="sqlite+aiosqlite:///:memory:")
    await store.init_db()

    job = Job(
        tenant_id=tenant_id,
        query="Quick lookup of AI market growth",
        mode=JobMode.SHALLOW,
        status=JobStatus.RUNNING,
    )
    await store.create_job(job)

    # Emit test events
    await store.emit_event(job.id, EventType.STAGE_STARTED, {"stage": "search"})
    await store.emit_event(job.id, EventType.TOOL_CALL, {"tool": "tavily", "query": "AI market"})
    await store.emit_event(job.id, EventType.DONE, {"status": "success"})

    # Collect events via subscribe_events generator
    events = []
    async for event in store.subscribe_events(job.id):
        events.append(event)
        if event.event_type == EventType.DONE:
            break

    event_types = [e.event_type for e in events]
    assert EventType.STAGE_STARTED in event_types
    assert EventType.TOOL_CALL in event_types
    assert EventType.DONE in event_types


@pytest.mark.asyncio
async def test_checkpoint_and_resume_after_interrupt():
    """Test that an interrupted job preserves checkpoint state and resumes cleanly."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = {"X-Tenant-ID": "tenant_hitl_test"}
        payload = {
            "query": "Deep brand audit requiring clarification on target audience",
            "mode": "clarify",
        }

        # 1. Start job that triggers clarification
        resp = await client.post("/v1/jobs", json=payload, headers=headers)
        assert resp.status_code == 202
        job_id = resp.json()["id"]

        # Wait for the interrupt to be hit
        for _ in range(40):
            await asyncio.sleep(0.5)
            get_resp = await client.get(f"/v1/jobs/{job_id}", headers=headers)
            if get_resp.json()["status"] == "needs_clarification":
                break

        assert get_resp.json()["status"] == "needs_clarification"

        # 2. Post clarification to resume graph execution
        clarify_payload = {
            "response": "Target audience is Fortune 500 CMOs in North America",
            "audience": "Enterprise CMOs",
            "geography": "North America",
        }
        clarify_resp = await client.post(
            f"/v1/jobs/{job_id}/clarify",
            json=clarify_payload,
            headers=headers,
        )
        assert clarify_resp.status_code == 200

        # 3. Wait for resumed graph execution to finish
        for _ in range(50):
            await asyncio.sleep(0.5)
            final_resp = await client.get(f"/v1/jobs/{job_id}", headers=headers)
            if final_resp.json()["status"] == "completed":
                break

        final_data = final_resp.json()
        assert final_data["status"] == "completed"
        assert final_data["report"] is not None
        assert len(final_data["report"]) > 0


@pytest.mark.asyncio
async def test_kill_process_mid_interrupt_and_resume_from_disk():
    """
    Test Step 4 requirement:
    Simulates a persistent checkpointer where a process dies / is killed mid-interrupt
    and a brand new process starts up, loads thread state from the SQLite disk file, and resumes.
    """
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    from langgraph.types import Command
    from core.graph.builder import ResearchGraphBuilder
    from pathlib import Path

    db_path = "test_kill_resume.db"
    if Path(db_path).exists():
        try:
            os.remove(db_path)
        except Exception:
            pass

    thread_id = "job_process_killed_thread"
    config = {"configurable": {"thread_id": thread_id}}

    # --- PROCESS 1: Starts graph, gets interrupted, then process is killed ---
    async with AsyncSqliteSaver.from_conn_string(db_path) as saver1:
        builder1 = ResearchGraphBuilder(checkpointer=saver1)
        graph1 = builder1.build()

        initial_state = {
            "job_id": thread_id,
            "tenant_id": "tenant_kill_test",
            "query": "Deep competitive teardown with missing audience details",
            "mode": "clarify",
            "stage": "started",
        }

        # Invoke until interrupt
        result1 = await graph1.ainvoke(initial_state, config=config)
        assert "__interrupt__" in result1

    # Simulate hard process termination: graph1 and saver1 are completely gone.
    del graph1
    del saver1
    del builder1

    # Verify checkpoint file exists on disk
    assert Path(db_path).exists(), "Checkpoint database file must exist on disk"

    # --- PROCESS 2: Fresh process starts up, opens disk DB, resumes checkpoint ---
    async with AsyncSqliteSaver.from_conn_string(db_path) as saver2:
        builder2 = ResearchGraphBuilder(checkpointer=saver2)
        graph2 = builder2.build()

        # Check that saved state is restored from disk
        saved_state = await graph2.aget_state(config)
        assert saved_state is not None
        assert saved_state.next == ("hitl_clarification",)

        # Resume the interrupted execution
        resume_command = Command(resume="Target Audience: B2B Marketers in Europe; Goal: Increase enterprise pipeline")
        result2 = await graph2.ainvoke(resume_command, config=config)

        # Graph should resume from checkpoint and proceed to completion
        assert result2 is not None
        assert result2.get("done") is True
        assert result2.get("report") is not None
        assert len(result2["report"]) > 0

    # Cleanup test DB
    if Path(db_path).exists():
        try:
            os.remove(db_path)
        except Exception:
            pass

