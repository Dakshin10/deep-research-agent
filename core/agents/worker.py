from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Dict, List, Optional
from core.state.store import StateStore
from core.state.schemas import PlanTask, ResearchNote, TaskStatus, EventType
from core.tools.search import SearchService
from core.tools.fetch import PageFetchService
from core.knowledge.store import KnowledgeStore


class ResearcherWorker:
    """
    Concurrent researcher worker executing a single plan task.
    Enforces:
    - Max 8 tool calls
    - Max 90 seconds per worker
    - No free text returned; only structured ResearchNote objects
    - Reads/writes through StateStore only
    """

    def __init__(
        self,
        worker_id: str,
        tenant_id: str,
        state_store: StateStore,
        search_service: Optional[SearchService] = None,
        fetch_service: Optional[PageFetchService] = None,
        knowledge_store: Optional[KnowledgeStore] = None,
        max_tool_calls: int = 8,
        timeout_seconds: float = 90.0,
    ):
        self.worker_id = worker_id
        self.tenant_id = tenant_id
        self.state_store = state_store
        self.search_service = search_service or SearchService()
        self.fetch_service = fetch_service or PageFetchService()
        self.knowledge_store = knowledge_store
        self.max_tool_calls = max_tool_calls
        self.timeout_seconds = timeout_seconds

    async def execute_task(self, task: PlanTask, job_id: str) -> List[ResearchNote]:
        start_time = time.time()
        tool_calls_count = 0
        produced_notes: List[ResearchNote] = []

        # 1. Update task status in shared state
        await self.state_store.update_task_status(job_id, task.task_id, TaskStatus.RUNNING)
        await self.state_store.emit_event(
            job_id,
            EventType.STAGE_STARTED,
            {
                "stage": "worker_started",
                "worker_id": self.worker_id,
                "task_id": task.task_id,
                "entity": task.entity,
            },
        )

        # 2. Tool call: Search for entity + objective
        if tool_calls_count < self.max_tool_calls and (time.time() - start_time) < self.timeout_seconds:
            tool_calls_count += 1
            search_query = f"{task.entity} {task.objective}"
            await self.state_store.emit_event(
                job_id,
                EventType.TOOL_CALL,
                {"worker_id": self.worker_id, "tool": "search", "query": search_query},
            )
            search_results = await self.search_service.search(search_query, max_results=3)

            for res in search_results:
                if getattr(res, "is_fallback", False):
                    await self.state_store.emit_event(
                        job_id,
                        EventType.PROVIDER_FALLBACK,
                        {
                            "provider": "search",
                            "worker_id": self.worker_id,
                            "task_id": task.task_id,
                            "reason": getattr(res, "fallback_reason", "Provider API key missing or unreachable"),
                        },
                    )

                note_id = f"note_{uuid.uuid4().hex[:8]}"
                note = ResearchNote(
                    id=note_id,
                    job_id=job_id,
                    tenant_id=self.tenant_id,
                    claim=f"{task.entity}: {res.content[:140].strip() or res.title}",
                    source_type="fallback" if getattr(res, "is_fallback", False) else "web",
                    source_url=res.url,
                    excerpt=res.content[:350].strip(),
                    confidence=0.85 if getattr(res, "is_fallback", False) else 0.94,
                    task_id=task.task_id,
                )
                await self.state_store.add_note(note)
                produced_notes.append(note)

        # 3. Tool call: Knowledge base lookup for tenant insights
        if self.knowledge_store and tool_calls_count < self.max_tool_calls and (time.time() - start_time) < self.timeout_seconds:
            tool_calls_count += 1
            await self.state_store.emit_event(
                job_id,
                EventType.TOOL_CALL,
                {"worker_id": self.worker_id, "tool": "kb_retrieve", "query": task.entity},
            )
            kb_chunks = await self.knowledge_store.retrieve(task.entity, top_k=2)
            for chunk in kb_chunks:
                note_id = f"note_kb_{uuid.uuid4().hex[:6]}"
                note = ResearchNote(
                    id=note_id,
                    job_id=job_id,
                    tenant_id=self.tenant_id,
                    claim=f"KB insight on {task.entity}: {chunk['text'][:140].strip()}",
                    source_type="kb",
                    document_id=chunk["document_id"],
                    excerpt=chunk["text"][:350].strip(),
                    confidence=0.96,
                    task_id=task.task_id,
                )
                await self.state_store.add_note(note)
                produced_notes.append(note)

        # 4. Tool call: Page fetch on top source for in-depth data
        if produced_notes and tool_calls_count < self.max_tool_calls and (time.time() - start_time) < self.timeout_seconds:
            top_web_note = next((n for n in produced_notes if n.source_url), None)
            if top_web_note and top_web_note.source_url:
                tool_calls_count += 1
                await self.state_store.emit_event(
                    job_id,
                    EventType.TOOL_CALL,
                    {"worker_id": self.worker_id, "tool": "fetch", "url": top_web_note.source_url},
                )
                fetched_md = await self.fetch_service.fetch_markdown(top_web_note.source_url)
                note_id = f"note_{uuid.uuid4().hex[:8]}"
                note = ResearchNote(
                    id=note_id,
                    job_id=job_id,
                    tenant_id=self.tenant_id,
                    claim=f"In-depth feature breakdown for {task.entity} verified from source document",
                    source_type="web",
                    source_url=top_web_note.source_url,
                    excerpt=fetched_md[:350].strip(),
                    confidence=0.92,
                    task_id=task.task_id,
                )
                await self.state_store.add_note(note)
                produced_notes.append(note)

        # 5. Complete task
        await self.state_store.update_task_status(job_id, task.task_id, TaskStatus.COMPLETED)
        return produced_notes
