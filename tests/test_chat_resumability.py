import asyncio
import pytest
from httpx import AsyncClient, ASGITransport
from datetime import datetime, timezone, timedelta

from apps.api.main import app
from core.chat.store import ChatStore
from core.chat.schemas import TextDeltaEvent, ArtifactEvent


@pytest.mark.asyncio
async def test_durable_event_log_monotonic_ids(tmp_path):
    """Test server-side durable event logging produces monotonically increasing sequential IDs."""
    db_file = tmp_path / "chat_resumable.db"
    store = ChatStore(tenant_id="test_tenant", db_url=f"sqlite+aiosqlite:///{db_file}")
    await store.init_db()

    conv = await store.create_conversation("Monotonic Test")
    
    seq1 = await store.save_event("evt_1", conv.id, "turn_1", "text_delta", {"content": "Hello "})
    seq2 = await store.save_event("evt_2", conv.id, "turn_1", "text_delta", {"content": "world"})
    seq3 = await store.save_event("evt_3", conv.id, "turn_1", "turn_complete", {"message_id": "msg_1"})

    assert seq1 < seq2 < seq3
    assert seq1 == 1
    assert seq2 == 2
    assert seq3 == 3

    # Fetch after seq 1
    missed = await store.get_events_after(conv.id, after_seq_id=1)
    assert len(missed) == 2
    assert missed[0]["seq_id"] == 2
    assert missed[0]["payload"]["content"] == "world"
    assert missed[1]["seq_id"] == 3


@pytest.mark.asyncio
async def test_get_stream_replay_from_last_event_id(tmp_path):
    """Test GET /v1/chat/stream correctly replays missed events starting from Last-Event-ID."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Start a turn
        res = await client.post(
            "/v1/chat",
            json={"message": "what is 15% of 2,340"},
            headers={"X-Tenant-ID": "test_tenant"},
        )
        assert res.status_code == 200
        
        import re
        # Read events and simulate network drop after receiving event id 1
        lines = [c for c in re.split(r"\r?\n\r?\n", res.text.strip()) if c]
        assert len(lines) >= 2

        # Extract event id of first chunk
        first_chunk = lines[0]
        event_id_line = [l for l in first_chunk.splitlines() if l.startswith("id: ")][0]
        last_seen_id = event_id_line.replace("id: ", "").strip()

        # Get conversation id from conversations endpoint
        convs = (await client.get("/v1/chat/conversations", headers={"X-Tenant-ID": "test_tenant"})).json()
        assert len(convs) > 0
        conv_id = convs[0]["id"]

        # 2. Reconnect using GET /v1/chat/stream with Last-Event-ID header
        replay_res = await client.get(
            f"/v1/chat/stream?conversation_id={conv_id}",
            headers={"X-Tenant-ID": "test_tenant", "Last-Event-ID": last_seen_id},
        )
        assert replay_res.status_code == 200

        replay_chunks = [c for c in re.split(r"\r?\n\r?\n", replay_res.text.strip()) if c]
        for chunk in replay_chunks:
            id_lines = [l for l in chunk.splitlines() if l.startswith("id: ")]
            if id_lines:
                rec_id = int(id_lines[0].replace("id: ", "").strip())
                assert rec_id > int(last_seen_id)


@pytest.mark.asyncio
async def test_event_retention_purge(tmp_path):
    """Test purging events older than retention_days."""
    db_file = tmp_path / "chat_purge.db"
    store = ChatStore(tenant_id="test_tenant", db_url=f"sqlite+aiosqlite:///{db_file}")
    await store.init_db()

    conv = await store.create_conversation("Purge Test")

    # Insert old event directly into DB with timestamp 40 days ago
    old_time = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
    now_time = datetime.now(timezone.utc).isoformat()

    async with store._connection() as db:
        await db.execute(
            "INSERT INTO chat_events (event_id, tenant_id, conversation_id, turn_id, event_type, payload, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("evt_old", "test_tenant", conv.id, "turn_0", "text_delta", "{}", old_time),
        )
        await db.execute(
            "INSERT INTO chat_events (event_id, tenant_id, conversation_id, turn_id, event_type, payload, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("evt_new", "test_tenant", conv.id, "turn_1", "text_delta", "{}", now_time),
        )
        await db.commit()

    # Purge events older than 30 days
    purged_count = await store.purge_old_events(retention_days=30)
    assert purged_count == 1

    remaining = await store.get_events_after(conv.id, after_seq_id=0)
    assert len(remaining) == 1
    assert remaining[0]["event_id"] == "evt_new"


@pytest.mark.asyncio
async def test_concurrent_second_message_does_not_cancel():
    """Test sending a second message while a background turn runs does not cancel the initial turn."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create a conversation
        conv_res = await client.post("/v1/chat/conversations", json={"title": "Concurrent Test"})
        conv_id = conv_res.json()["id"]

        # Launch two requests concurrently
        t1 = client.post(
            "/v1/chat",
            json={"conversation_id": conv_id, "message": "research the latest breakthroughs in solid-state batteries"},
        )
        t2 = client.post(
            "/v1/chat",
            json={"conversation_id": conv_id, "message": "what is 15% of 2,340"},
        )

        res1, res2 = await asyncio.gather(t1, t2)

        assert res1.status_code == 200
        assert res2.status_code == 200
        assert "research" in res1.text.lower() or "report" in res1.text.lower() or "status" in res1.text.lower()
        assert "351" in res2.text
