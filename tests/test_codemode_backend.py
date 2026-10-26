"""
Unit and integration tests for CodeModeBackend (LocalBackend and MainAgent integration).
"""

import pytest
from core.chat.agent import MainChatAgent
from core.chat.schemas import CodeExecutionEvent, DoneEvent
from core.chat.store import ChatStore
from core.codemode.local import LocalBackend


@pytest.mark.asyncio
async def test_codemode_search_catalog():
    backend = LocalBackend()
    res = await backend.search("research")

    assert res.total_matches > 0
    assert any("research" in m["namespace"] for m in res.matches)
    assert "declare namespace api" in res.types_dts


@pytest.mark.asyncio
async def test_codemode_execute_pure_js():
    backend = LocalBackend()
    code = "const a = 10; const b = 20; return a + b;"
    res = await backend.execute(code)

    assert res.success is True
    assert res.result == 30
    assert res.error is None
    assert len(res.audit_hash) == 64


@pytest.mark.asyncio
async def test_codemode_execute_api_call():
    backend = LocalBackend()
    code = 'const res = await api.research.deep({ query: "solid state battery" }); return res;'
    res = await backend.execute(code)

    assert res.success is True
    assert res.result is not None
    assert "solid state battery" in res.result["findings_summary"]
    assert len(res.calls_made) == 1
    assert res.calls_made[0]["method"] == "research.deep"


@pytest.mark.asyncio
async def test_codemode_parallel_fanout_promise_all():
    backend = LocalBackend()
    code = """
    const queries = ['quantum', 'superconductors', 'fusion', 'batteries'];
    const results = await Promise.all(
      queries.map(q => api.research.deep({ query: q }))
    );
    return { count: results.length, summaries: results.map(r => r.findings_summary) };
    """
    res = await backend.execute(code)

    assert res.success is True
    assert res.result["count"] == 4
    assert len(res.calls_made) == 4


@pytest.mark.asyncio
async def test_codemode_mutation_blocked_without_token():
    backend = LocalBackend()
    # api.crawl.start is marked as a mutation
    code = 'const r = await api.crawl.start({ source: "devpost", max_depth: 1 }); return r;'
    res = await backend.execute(code, approval_token=None)

    assert res.success is False
    assert "approval token" in (res.error or "").lower()


@pytest.mark.asyncio
async def test_codemode_mutation_allowed_with_token():
    backend = LocalBackend()
    code = 'const r = await api.crawl.start({ source: "devpost", max_depth: 1 }); return r;'
    res = await backend.execute(code, approval_token="valid_approval_token_12345")

    assert res.success is True
    assert res.result["status"] == "active"


@pytest.mark.asyncio
async def test_codemode_agent_routing_and_event_stream():
    store = ChatStore(db_url="sqlite+aiosqlite:///:memory:", tenant_id="tenant_codemode")
    await store.init_db()

    backend = LocalBackend()
    agent = MainChatAgent(store=store, tenant_id="tenant_codemode", backend=backend)

    # Route message requiring Code Mode
    events = []
    async for event in agent.execute_turn(
        conversation_id="conv_cm_test",
        user_message="Execute JavaScript in Code Mode to query analytics hubspot deals",
    ):
        events.append(event)

    types = [e.type for e in events]
    assert "reasoning_summary" in types
    assert "code_execution" in types
    assert "text_delta" in types
    assert "done" in types

    exec_event = next(e for e in events if isinstance(e, CodeExecutionEvent))
    assert exec_event.sandboxed is True
    assert "hubspot_deals" in exec_event.code
