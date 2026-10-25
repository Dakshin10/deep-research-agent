import pytest
from httpx import AsyncClient, ASGITransport

from apps.api.main import app
from core.observability.tracing import get_tracer, record_shard_span, record_provider_span
from core.state.schemas import (
    Brief,
    EventType,
    Job,
    JobStatus,
    ResearchNote,
)
from core.state.store import StateStore
import app as gradio_app


@pytest.mark.asyncio
async def test_get_job_sources_endpoint():
    tenant_id = "tenant_sources_test"
    job_id = "job_sources_123"

    store = StateStore(tenant_id=tenant_id, db_url="sqlite+aiosqlite:///:memory:")
    await store.init_db()

    job = Job(
        id=job_id,
        tenant_id=tenant_id,
        query="Enterprise LLM Infrastructure",
        title="Enterprise LLM Infrastructure",
        brief=Brief(topic="LLM Infra"),
        status=JobStatus.COMPLETED,
    )
    await store.create_job(job)

    # Add verified notes across families
    note_web = ResearchNote(
        id="note_web_01",
        job_id=job_id,
        task_id="task_1",
        tenant_id=tenant_id,
        claim="vLLM achieves 24x throughput over vanilla HuggingFace.",
        excerpt="vLLM achieves 24x throughput over vanilla HuggingFace via PagedAttention.",
        source_type="web",
        url="https://vllm.ai/benchmarks",
        title="vLLM Benchmarks",
        source_family="web_general",
        char_start=100,
        char_end=176,
        heading_path=["Benchmarks", "PagedAttention"],
        text_fragment_url="https://vllm.ai/benchmarks#:~:text=vLLM%20achieves",
        is_verified=True,
    )
    await store.add_note(note_web)

    note_forum = ResearchNote(
        id="note_forum_02",
        job_id=job_id,
        task_id="task_1",
        tenant_id=tenant_id,
        claim="Hacker News discussion debates memory overhead in TensorRT-LLM.",
        excerpt="HN comments debate memory overhead in TensorRT-LLM compared to vLLM.",
        source_type="web",
        url="https://news.ycombinator.com/item?id=9999",
        title="HN Discussion",
        source_family="forums",
        char_start=50,
        char_end=120,
        heading_path=["Comments"],
        text_fragment_url="https://news.ycombinator.com/item?id=9999#:~:text=debate%20memory",
        is_verified=True,
    )
    await store.add_note(note_forum)

    # Emit blocked and rejected events
    await store.emit_event(
        job_id=job_id,
        event_type=EventType.PAGE_BLOCKED,
        payload={"url": "https://walled-garden.com/paywall", "reason": "Cloudflare captcha / 403 forbidden"},
    )
    await store.emit_event(
        job_id=job_id,
        event_type=EventType.NOTE_REJECTED,
        payload={"url": "https://flimsy-source.org/claim", "reason": "Excerpt verification match failed in document text"},
    )

    from apps.api.dependencies import get_state_store
    app.dependency_overrides[get_state_store] = lambda: store

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/v1/jobs/{job_id}/sources", headers={"X-Tenant-ID": tenant_id})
            assert resp.status_code == 200
            data = resp.json()
    finally:
        app.dependency_overrides.pop(get_state_store, None)

    assert data["job_id"] == job_id
    assert data["tenant_id"] == tenant_id
    assert "web_general" in data["source_families"]
    assert "forums" in data["source_families"]
    assert "blocked" in data["source_families"]
    assert "rejected" in data["source_families"]

    # Check exact location structure
    web_item = data["source_families"]["web_general"][0]
    assert web_item["note_id"] == "note_web_01"
    assert web_item["status"] == "verified"
    assert web_item["location"]["heading_path"] == ["Benchmarks", "PagedAttention"]
    assert web_item["location"]["char_start"] == 100
    assert web_item["text_fragment_url"] == "https://vllm.ai/benchmarks#:~:text=vLLM%20achieves"

    # Check coverage counts
    assert data["coverage_counts"]["web_general"] == 1
    assert data["coverage_counts"]["forums"] == 1
    assert data["total_sources"] == 4


def test_langfuse_spans_per_shard_and_provider():
    tracer = get_tracer()
    tracer.clear()

    # Record shard span
    record_shard_span(
        shard_id="shard_academic_01",
        task_id="task_research",
        query="arxiv transformer efficiency",
        duration=0.85,
        notes_count=3,
    )

    # Record provider span
    record_provider_span(
        provider="searxng",
        query="arxiv transformer efficiency",
        duration=0.42,
        hits_count=10,
    )

    traces = tracer.get_traces()
    assert len(traces) == 2

    shard_trace = next(t for t in traces if t.trace_type == "shard")
    assert "shard_academic_01" in shard_trace.name
    assert shard_trace.inputs["task_id"] == "task_research"
    assert shard_trace.outputs["notes_count"] == "3"
    assert shard_trace.duration_seconds == 0.85

    prov_trace = next(t for t in traces if t.trace_type == "provider")
    assert prov_trace.name == "provider_searxng"
    assert prov_trace.outputs["hits_count"] == "10"
    assert prov_trace.duration_seconds == 0.42


def test_gradio_ui_components_formatters():
    # 1. Shards panel formatter
    shards = [
        {"shard_id": "shard_001", "source_family": "forums", "query": "reddit AI review", "status": "done", "duration": "0.7s", "notes_count": 2}
    ]
    html_shards = gradio_app.format_shards_panel_html(shards)
    assert "shard_001" in html_shards
    assert "forums" in html_shards
    assert "DONE" in html_shards

    # 2. Source coverage formatter
    coverage = {"web_general": 5, "academic": 3, "forums": 2}
    html_cov = gradio_app.format_source_coverage_html(coverage)
    assert "web_general" in html_cov
    assert "5" in html_cov
    assert "50.0%" in html_cov

    # 3. Evidence table formatter
    evidence = [
        {
            "id": "note_xyz",
            "source_family": "academic",
            "title": "Quantum Study",
            "excerpt": "Quantum supremacy achieved with 70 qubits.",
            "location_str": "p. 14 of PDF (offsets 200-240)",
            "text_fragment_url": "https://study.org/quantum#:~:text=Quantum%20supremacy",
        }
    ]
    html_ev = gradio_app.format_evidence_table_html(evidence)
    assert "[note_xyz]" in html_ev
    assert "Quantum Study" in html_ev
    assert "p. 14 of PDF" in html_ev
    assert "Scroll to Text ↗" in html_ev

    # 4. run_agent execution returns all 7 components
    res = gradio_app.run_agent("Evaluate solid-state batteries vs lithium-ion")
    assert len(res) == 7
    final_rep, s_html, c_html, e_html, init_out, ref_html, q_out = res
    assert "Research Report" in final_rep
    assert "shard_001" in s_html
    assert "web_general" in c_html
    assert "note_widx_8a" in e_html
