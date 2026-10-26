from __future__ import annotations

import json
import pytest
from httpx import AsyncClient, ASGITransport

from apps.api.main import app
from core.chat.agent import MainChatAgent
from core.chat.schemas import (
    ChatMessage,
    ChatRole,
    CitationEvent,
    ArtifactEvent,
    DoneEvent,
    PartType,
    TextDeltaEvent,
    ReasoningSummaryEvent,
    ClarificationRequestEvent,
)
from core.chat.store import ChatStore


@pytest.mark.asyncio
async def test_chat_event_serialization():
    """Verify that all typed SSE chat events conform to the schema."""
    delta = TextDeltaEvent(turn_id="turn_1", content="Hello world")
    assert delta.type == "text_delta"
    assert delta.content == "Hello world"

    cit = CitationEvent(
        turn_id="turn_1",
        note_id="note_01",
        url="https://example.com",
        title="Test Doc",
        excerpt="Important quote",
        location="p. 3",
        text_fragment_url="https://example.com#:~:text=quote",
        verified=True,
    )
    assert cit.type == "citation"
    assert cit.verified is True

    clarify = ClarificationRequestEvent(
        turn_id="turn_1",
        question="Which target market?",
        suggested_answers=["B2B", "B2C"],
    )
    assert clarify.type == "clarification_request"
    assert len(clarify.suggested_answers) == 2


@pytest.mark.asyncio
async def test_chat_store_crud_and_branching():
    """Test conversation creation, message persistence, branching, and feedback."""
    store = ChatStore(tenant_id="tenant_chat_test", db_url="sqlite+aiosqlite:///:memory:")
    await store.init_db()

    # 1. Create Conversation
    conv = await store.create_conversation(title="Initial Research")
    assert conv.id.startswith("conv_")
    assert conv.title == "Initial Research"

    # 2. Add Messages
    user_msg = ChatMessage(
        conversation_id=conv.id,
        role=ChatRole.USER,
        content="Critically evaluate solid-state batteries.",
    )
    await store.save_message(user_msg)

    asst_msg = ChatMessage(
        conversation_id=conv.id,
        parent_id=user_msg.id,
        role=ChatRole.ASSISTANT,
        content="Solid-state batteries offer higher energy density.",
        citations=[
            CitationEvent(
                turn_id="turn_1",
                note_id="n1",
                url="https://battery.org",
                title="Battery Report",
                excerpt="Energy density 450 Wh/kg",
                location="Section 2",
            )
        ],
    )
    await store.save_message(asst_msg)

    # 3. Retrieve Messages
    history = await store.get_conversation_messages(conv.id)
    assert len(history) == 2
    assert history[0].role == ChatRole.USER
    assert history[1].role == ChatRole.ASSISTANT
    assert len(history[1].citations) == 1
    assert history[1].citations[0].note_id == "n1"

    # 4. Update Title
    await store.update_conversation_title(conv.id, "Solid-State Battery Deep Dive")
    updated_conv = await store.get_conversation(conv.id)
    assert updated_conv.title == "Solid-State Battery Deep Dive"

    # 5. Feedback
    await store.save_feedback(message_id=asst_msg.id, rating="thumbs_up", feedback_text="Great citations!")

    # 6. Delete
    deleted = await store.delete_conversation(conv.id)
    assert deleted is True
    assert await store.get_conversation(conv.id) is None


@pytest.mark.asyncio
async def test_chat_store_tenant_isolation():
    """Verify strict tenant isolation: Tenant A cannot see Tenant B conversations on same database."""
    import os
    db_file = "sqlite+aiosqlite:///test_chat_tenant.db"
    store_a = ChatStore(tenant_id="tenant_alpha", db_url=db_file)
    store_b = ChatStore(tenant_id="tenant_beta", db_url=db_file)
    await store_a.init_db()

    try:
        conv_a = await store_a.create_conversation(title="Alpha Secret Strategy")

        # Tenant B lists conversations
        list_b = await store_b.list_conversations()
        assert not any(c.id == conv_a.id for c in list_b)

        # Tenant B tries to get Tenant A conversation directly
        get_b = await store_b.get_conversation(conv_a.id)
        assert get_b is None
    finally:
        if os.path.exists("test_chat_tenant.db"):
            try:
                os.remove("test_chat_tenant.db")
            except Exception:
                pass


@pytest.mark.asyncio
async def test_main_agent_router_decisions():
    """Verify routing decisions on diverse prompt types."""
    agent = MainChatAgent(tenant_id="tenant_route_test")

    assert agent.route_intent("hello there") == "direct"
    assert agent.route_intent("do a brand audit") == "clarify"
    assert agent.route_intent("research commercialization hurdles of Room Temperature Superconductors") == "deep_research"
    assert agent.route_intent("mine ideas for healthcare hackathons") == "ideas_search"
    assert agent.route_intent("generate ideas for autonomous agent workflows") == "ideas_generate"
    assert agent.route_intent("start crawl on devpost") == "crawl"


@pytest.mark.asyncio
async def test_main_agent_turn_execution_streaming():
    """Verify end-to-end streaming of events in a turn."""
    store = ChatStore(tenant_id="tenant_stream_test", db_url="sqlite+aiosqlite:///:memory:")
    await store.init_db()
    agent = MainChatAgent(store=store, tenant_id="tenant_stream_test")

    conv = await store.create_conversation()

    events = []
    async for event in agent.execute_turn(
        conversation_id=conv.id,
        user_message="Critically evaluate solid-state batteries vs lithium-ion.",
    ):
        events.append(event)

    event_types = [e.type for e in events]
    assert "reasoning_summary" in event_types
    assert "tool_call_started" in event_types
    assert "research_progress" in event_types
    assert "citation" in event_types
    assert "artifact" in event_types
    assert "text_delta" in event_types
    assert "done" in event_types

    # Check conversation auto-titling
    updated_conv = await store.get_conversation(conv.id)
    assert updated_conv.title != "New Research Chat"


@pytest.mark.asyncio
async def test_chat_api_endpoints():
    """Test FastAPI /v1/chat and conversation management endpoints."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = {"X-Tenant-ID": "tenant_api_chat_test"}

        # 1. Create conversation
        conv_resp = await client.post("/v1/chat/conversations", json={"title": "Test Chat"}, headers=headers)
        assert conv_resp.status_code == 200
        conv_id = conv_resp.json()["id"]

        # 2. List conversations
        list_resp = await client.get("/v1/chat/conversations", headers=headers)
        assert list_resp.status_code == 200
        assert len(list_resp.json()) >= 1

        # 3. Stream turn via POST /v1/chat
        turn_payload = {
            "conversation_id": conv_id,
            "message": "research solid state batteries",
        }
        chat_resp = await client.post("/v1/chat", json=turn_payload, headers=headers)
        assert chat_resp.status_code == 200
        assert "text/event-stream" in chat_resp.headers["content-type"]

        # 4. Get conversation with messages
        get_resp = await client.get(f"/v1/chat/conversations/{conv_id}", headers=headers)
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["conversation"]["id"] == conv_id
        assert len(data["messages"]) == 2  # user + assistant

        # 5. Send feedback
        asst_msg_id = data["messages"][1]["id"]
        fb_resp = await client.post("/v1/chat/feedback", json={"message_id": asst_msg_id, "rating": "thumbs_up"}, headers=headers)
        assert fb_resp.status_code == 200

        # 6. Delete conversation
        del_resp = await client.delete(f"/v1/chat/conversations/{conv_id}", headers=headers)
        assert del_resp.status_code == 200
