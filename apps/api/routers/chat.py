from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sse_starlette.sse import EventSourceResponse

from core.chat.agent import MainChatAgent
from core.chat.schemas import (
    ChatMessage,
    ChatTurnRequest,
    Conversation,
)
from core.chat.store import ChatStore

router = APIRouter(prefix="/v1/chat", tags=["chat"])


def get_tenant_id(x_tenant_id: Optional[str] = Header(None)) -> str:
    return x_tenant_id or "default_tenant"


def get_chat_store(tenant_id: str = Depends(get_tenant_id)) -> ChatStore:
    return ChatStore(tenant_id=tenant_id)


def get_chat_agent(store: ChatStore = Depends(get_chat_store), tenant_id: str = Depends(get_tenant_id)) -> MainChatAgent:
    return MainChatAgent(store=store, tenant_id=tenant_id)


# Active background jobs registry mapping job_id/conv_id to running tasks
ACTIVE_BACKGROUND_JOBS: Dict[str, Any] = {}


@router.post("")
async def create_chat_turn(
    req: ChatTurnRequest,
    agent: MainChatAgent = Depends(get_chat_agent),
    store: ChatStore = Depends(get_chat_store),
):
    """
    Unified chat endpoint streaming typed Server-Sent Events (SSE).
    Persists durable events with monotonically increasing IDs into store.
    """
    await store.init_db()

    # 1. Resolve or create conversation
    conv_id = req.conversation_id
    if not conv_id:
        conv = await store.create_conversation(title="New Research Chat")
        conv_id = conv.id
    else:
        conv = await store.get_conversation(conv_id)
        if not conv:
            conv = await store.create_conversation(title="New Research Chat")
            conv_id = conv.id

    async def event_generator():
        async for event in agent.execute_turn(
            conversation_id=conv_id,
            user_message=req.message,
            parent_message_id=req.parent_message_id,
            incognito=req.incognito,
            model_role=req.model_role,
            approval_token=req.approval_token,
        ):
            # Durable server-side event logging with monotonic integer seq_id
            sse_id = event.event_id
            if not req.incognito:
                try:
                    seq_id = await store.save_event(
                        event_id=event.event_id,
                        conversation_id=conv_id,
                        turn_id=event.turn_id,
                        event_type=event.type,
                        payload=event.model_dump(mode="json"),
                    )
                    sse_id = str(seq_id)
                except Exception:
                    pass

            yield {
                "id": sse_id,
                "event": event.type,
                "data": event.model_dump_json(),
            }

    return EventSourceResponse(event_generator())


@router.get("/stream")
async def resume_chat_stream(
    conversation_id: str = Query(...),
    last_event_id: Optional[str] = Header(None, alias="Last-Event-ID"),
    after_id: Optional[str] = Query(None, alias="last_event_id"),
    store: ChatStore = Depends(get_chat_store),
):
    """
    Resumes an SSE stream from the server-side durable event log starting after Last-Event-ID.
    Guarantees no lost or duplicated events across network drops or tab refreshes.
    """
    await store.init_db()
    effective_last_id = last_event_id or after_id
    after_seq = 0
    if effective_last_id:
        try:
            after_seq = int(effective_last_id)
        except ValueError:
            after_seq = 0

    async def replay_generator():
        missed_events = await store.get_events_after(conversation_id, after_seq_id=after_seq)
        for ev in missed_events:
            yield {
                "id": str(ev["seq_id"]),
                "event": ev["event_type"],
                "data": json.dumps(ev["payload"]),
            }

    return EventSourceResponse(replay_generator())


@router.get("/conversations", response_model=List[Conversation])
async def list_conversations(
    limit: int = Query(50, ge=1, le=200),
    store: ChatStore = Depends(get_chat_store),
):
    await store.init_db()
    return await store.list_conversations(limit=limit)


@router.post("/conversations", response_model=Conversation)
async def create_conversation(
    payload: Dict[str, Any] = None,
    store: ChatStore = Depends(get_chat_store),
):
    await store.init_db()
    title = (payload or {}).get("title", "New Research Chat")
    return await store.create_conversation(title=title)


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    store: ChatStore = Depends(get_chat_store),
):
    await store.init_db()
    conv = await store.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    messages = await store.get_conversation_messages(conversation_id)
    return {
        "conversation": conv,
        "messages": messages,
    }


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    store: ChatStore = Depends(get_chat_store),
):
    await store.init_db()
    deleted = await store.delete_conversation(conversation_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"status": "deleted", "id": conversation_id}


@router.post("/feedback")
async def record_feedback(
    payload: Dict[str, Any],
    store: ChatStore = Depends(get_chat_store),
):
    await store.init_db()
    msg_id = payload.get("message_id")
    rating = payload.get("rating", "thumbs_up")
    text = payload.get("feedback_text")
    if not msg_id:
        raise HTTPException(status_code=400, detail="message_id is required")
    await store.save_feedback(message_id=msg_id, rating=rating, feedback_text=text)
    return {"status": "recorded"}
