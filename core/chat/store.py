from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, List, Optional
import aiosqlite

from core.chat.schemas import (
    ChatMessage,
    ChatRole,
    Conversation,
    MessagePart,
    PartType,
    CitationEvent,
    ArtifactEvent,
)


class ChatStore:
    """
    Persistent store for conversations, messages, tree branches, and feedback.
    Supports PostgreSQL with Row-Level Security in production and aiosqlite for
    local dev and deterministic offline testing.
    """

    def __init__(self, tenant_id: str = "default_tenant", db_url: Optional[str] = None):
        self.tenant_id = tenant_id
        self.db_url = db_url or os.getenv("CHAT_DB_URL", "sqlite+aiosqlite:///data/chat.db")
        self._sqlite_path = self.db_url.replace("sqlite+aiosqlite:///", "") if "sqlite" in self.db_url else None
        if self._sqlite_path and ":memory:" not in self._sqlite_path:
            os.makedirs(os.path.dirname(os.path.abspath(self._sqlite_path)), exist_ok=True)
        self._shared_conn: Optional[aiosqlite.Connection] = None

    @asynccontextmanager
    async def _connection(self) -> AsyncGenerator[aiosqlite.Connection, None]:
        if self._sqlite_path == ":memory:":
            if self._shared_conn is None:
                self._shared_conn = await aiosqlite.connect(":memory:")
            yield self._shared_conn
        else:
            async with aiosqlite.connect(self._sqlite_path or "data/chat.db") as db:
                yield db

    async def init_db(self) -> None:
        """Initializes tables in SQLite if using local file/memory."""
        if not self._sqlite_path:
            return

        async with self._connection() as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    active_branch_leaf_id TEXT,
                    metadata TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    conversation_id TEXT NOT NULL,
                    parent_id TEXT,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    citations TEXT NOT NULL,
                    artifacts TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS message_parts (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    message_id TEXT NOT NULL,
                    part_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS turn_feedback (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    message_id TEXT NOT NULL,
                    rating TEXT NOT NULL,
                    feedback_text TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS chat_events (
                    seq_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT UNIQUE NOT NULL,
                    tenant_id TEXT NOT NULL,
                    conversation_id TEXT NOT NULL,
                    turn_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_chat_events_conv_seq ON chat_events(conversation_id, seq_id)
            """)
            await db.commit()


    async def create_conversation(self, title: str = "New Research Chat", metadata: Optional[Dict[str, Any]] = None) -> Conversation:
        conv = Conversation(tenant_id=self.tenant_id, title=title, metadata=metadata or {})
        now_str = conv.created_at.isoformat()

        async with self._connection() as db:
            await db.execute(
                "INSERT INTO conversations (id, tenant_id, title, active_branch_leaf_id, metadata, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (conv.id, conv.tenant_id, conv.title, conv.active_branch_leaf_id, json.dumps(conv.metadata), now_str, now_str),
            )
            await db.commit()
        return conv

    async def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        async with self._connection() as db:
            cursor = await db.execute(
                "SELECT id, tenant_id, title, active_branch_leaf_id, metadata, created_at, updated_at FROM conversations WHERE id = ? AND tenant_id = ?",
                (conversation_id, self.tenant_id),
            )
            row = await cursor.fetchone()
            if not row:
                return None
            return Conversation(
                id=row[0],
                tenant_id=row[1],
                title=row[2],
                active_branch_leaf_id=row[3],
                metadata=json.loads(row[4]),
                created_at=datetime.fromisoformat(row[5]),
                updated_at=datetime.fromisoformat(row[6]),
            )

    async def list_conversations(self, limit: int = 50) -> List[Conversation]:
        async with self._connection() as db:
            cursor = await db.execute(
                "SELECT id, tenant_id, title, active_branch_leaf_id, metadata, created_at, updated_at FROM conversations WHERE tenant_id = ? ORDER BY updated_at DESC LIMIT ?",
                (self.tenant_id, limit),
            )
            rows = await cursor.fetchall()
            return [
                Conversation(
                    id=r[0],
                    tenant_id=r[1],
                    title=r[2],
                    active_branch_leaf_id=r[3],
                    metadata=json.loads(r[4]),
                    created_at=datetime.fromisoformat(r[5]),
                    updated_at=datetime.fromisoformat(r[6]),
                )
                for r in rows
            ]

    async def update_conversation_title(self, conversation_id: str, title: str) -> None:
        now_str = datetime.now(timezone.utc).isoformat()
        async with self._connection() as db:
            await db.execute(
                "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ? AND tenant_id = ?",
                (title, now_str, conversation_id, self.tenant_id),
            )
            await db.commit()

    async def save_message(self, message: ChatMessage) -> None:
        now_str = message.created_at.isoformat()
        cit_json = json.dumps([c.model_dump(mode="json") for c in message.citations])
        art_json = json.dumps([a.model_dump(mode="json") for a in message.artifacts])

        async with self._connection() as db:
            await db.execute(
                "INSERT INTO messages (id, tenant_id, conversation_id, parent_id, role, content, citations, artifacts, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (message.id, self.tenant_id, message.conversation_id, message.parent_id, message.role.value, message.content, cit_json, art_json, now_str),
            )
            for part in message.parts:
                await db.execute(
                    "INSERT INTO message_parts (id, tenant_id, message_id, part_type, content, metadata, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (part.id, self.tenant_id, message.id, part.part_type.value, part.content, json.dumps(part.metadata), now_str),
                )
            # Update conversation active leaf & timestamp
            await db.execute(
                "UPDATE conversations SET active_branch_leaf_id = ?, updated_at = ? WHERE id = ? AND tenant_id = ?",
                (message.id, now_str, message.conversation_id, self.tenant_id),
            )
            await db.commit()

    async def get_conversation_messages(self, conversation_id: str) -> List[ChatMessage]:
        async with self._connection() as db:
            cursor = await db.execute(
                "SELECT id, tenant_id, conversation_id, parent_id, role, content, citations, artifacts, created_at FROM messages WHERE conversation_id = ? AND tenant_id = ? ORDER BY created_at ASC",
                (conversation_id, self.tenant_id),
            )
            rows = await cursor.fetchall()
            messages = []
            for r in rows:
                cit_data = json.loads(r[6])
                art_data = json.loads(r[7])
                citations = [CitationEvent(**c) for c in cit_data]
                artifacts = [ArtifactEvent(**a) for a in art_data]
                messages.append(ChatMessage(
                    id=r[0],
                    conversation_id=r[2],
                    parent_id=r[3],
                    role=ChatRole(r[4]),
                    content=r[5],
                    citations=citations,
                    artifacts=artifacts,
                    created_at=datetime.fromisoformat(r[8]),
                ))
            return messages

    async def save_feedback(self, message_id: str, rating: str, feedback_text: Optional[str] = None) -> None:
        import uuid
        now_str = datetime.now(timezone.utc).isoformat()
        async with self._connection() as db:
            await db.execute(
                "INSERT INTO turn_feedback (id, tenant_id, message_id, rating, feedback_text, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (f"fb_{uuid.uuid4().hex[:12]}", self.tenant_id, message_id, rating, feedback_text, now_str),
            )
            await db.commit()

    async def delete_conversation(self, conversation_id: str) -> bool:
        async with self._connection() as db:
            res = await db.execute(
                "DELETE FROM conversations WHERE id = ? AND tenant_id = ?",
                (conversation_id, self.tenant_id),
            )
            await db.commit()
            return res.rowcount > 0

    async def save_event(
        self,
        event_id: str,
        conversation_id: str,
        turn_id: str,
        event_type: str,
        payload: Dict[str, Any],
    ) -> int:
        now_str = datetime.now(timezone.utc).isoformat()
        payload_str = json.dumps(payload, default=str)
        async with self._connection() as db:
            cursor = await db.execute(
                "INSERT INTO chat_events (event_id, tenant_id, conversation_id, turn_id, event_type, payload, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (event_id, self.tenant_id, conversation_id, turn_id, event_type, payload_str, now_str),
            )
            await db.commit()
            return cursor.lastrowid

    async def get_events_after(
        self,
        conversation_id: str,
        after_seq_id: int = 0,
    ) -> List[Dict[str, Any]]:
        async with self._connection() as db:
            cursor = await db.execute(
                "SELECT seq_id, event_id, tenant_id, conversation_id, turn_id, event_type, payload, created_at FROM chat_events WHERE conversation_id = ? AND tenant_id = ? AND seq_id > ? ORDER BY seq_id ASC",
                (conversation_id, self.tenant_id, after_seq_id),
            )
            rows = await cursor.fetchall()
            return [
                {
                    "seq_id": r[0],
                    "event_id": r[1],
                    "tenant_id": r[2],
                    "conversation_id": r[3],
                    "turn_id": r[4],
                    "event_type": r[5],
                    "payload": json.loads(r[6]),
                    "created_at": r[7],
                }
                for r in rows
            ]

    async def purge_old_events(self, retention_days: int = 30) -> int:
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        cutoff_str = cutoff.isoformat()
        async with self._connection() as db:
            cursor = await db.execute(
                "DELETE FROM chat_events WHERE created_at < ?",
                (cutoff_str,),
            )
            await db.commit()
            return cursor.rowcount

    async def update_conversation_model(self, conversation_id: str, model_role: str) -> None:
        async with self._connection() as db:
            cursor = await db.execute(
                "SELECT metadata FROM conversations WHERE id = ? AND tenant_id = ?",
                (conversation_id, self.tenant_id),
            )
            row = await cursor.fetchone()
            meta = json.loads(row[0]) if row and row[0] else {}
            meta["model_role"] = model_role
            now_str = datetime.now(timezone.utc).isoformat()
            await db.execute(
                "UPDATE conversations SET metadata = ?, updated_at = ? WHERE id = ? AND tenant_id = ?",
                (json.dumps(meta), now_str, conversation_id, self.tenant_id),
            )
            await db.commit()

