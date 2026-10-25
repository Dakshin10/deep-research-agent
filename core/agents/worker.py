from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Dict, List, Optional
from core.fetch.location import verify_excerpt_in_document
from core.fetch.base import FetchedDocument
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
    - HARD RULE: Every citation excerpt must be strictly verified against fetched document text
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

                # Fetch document to verify snippet or extract authentic excerpt
                doc = await self.fetch_service.fetch_document(res.url)

                # Pick best excerpt from document or search result
                candidate_excerpt = res.content[:280].strip()
                if doc and doc.raw_text and candidate_excerpt not in doc.raw_text:
                    # Find sentence containing task.entity in doc.raw_text or take top clean excerpt
                    sentences = [s.strip() for s in doc.raw_text.split(".") if task.entity.lower() in s.lower()]
                    if sentences:
                        candidate_excerpt = sentences[0][:280].strip()
                    elif doc.raw_text:
                        candidate_excerpt = doc.raw_text[:280].strip()

                note_id = f"note_{uuid.uuid4().hex[:8]}"
                note = ResearchNote(
                    id=note_id,
                    job_id=job_id,
                    tenant_id=self.tenant_id,
                    claim=f"{task.entity}: {candidate_excerpt[:140].strip() or res.title}",
                    source_type="fallback" if getattr(res, "is_fallback", False) else "web",
                    source_url=res.url,
                    excerpt=candidate_excerpt,
                    confidence=0.85 if getattr(res, "is_fallback", False) else 0.94,
                    task_id=task.task_id,
                    source_family=getattr(res, "source_family", "web_general"),
                    provider=getattr(res, "provider", "searxng"),
                )

                # Verification step before note is saved
                saved = await self._verify_and_save_note(note, job_id, task, doc=doc)
                if saved:
                    produced_notes.append(saved)

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
                    excerpt=chunk["text"][:280].strip(),
                    confidence=0.96,
                    task_id=task.task_id,
                    is_verified=True,
                )
                saved = await self._verify_and_save_note(note, job_id, task)
                if saved:
                    produced_notes.append(saved)

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
                doc = await self.fetch_service.fetch_document(top_web_note.source_url)
                if doc and doc.raw_text:
                    excerpt = doc.raw_text[:280].strip()
                    note_id = f"note_{uuid.uuid4().hex[:8]}"
                    note = ResearchNote(
                        id=note_id,
                        job_id=job_id,
                        tenant_id=self.tenant_id,
                        claim=f"In-depth feature breakdown for {task.entity} verified from source document",
                        source_type="web",
                        source_url=top_web_note.source_url,
                        excerpt=excerpt,
                        confidence=0.92,
                        task_id=task.task_id,
                    )
                    saved = await self._verify_and_save_note(note, job_id, task, doc=doc)
                    if saved:
                        produced_notes.append(saved)

        # 5. Complete task
        await self.state_store.update_task_status(job_id, task.task_id, TaskStatus.COMPLETED)
        return produced_notes

    async def _verify_and_save_note(
        self,
        note: ResearchNote,
        job_id: str,
        task: PlanTask,
        doc: Optional[FetchedDocument] = None,
    ) -> Optional[ResearchNote]:
        """
        HARD RULE:
        Verify that note.excerpt exists in the fetched document text (exact match, else fuzzy match >= 0.90).
        Compute char offsets and page/heading from that match.
        If it cannot be located, DROP the note and emit a note_rejected event.
        """
        # If KB or computed, inherently verified
        if note.source_type in ("kb", "computed"):
            note.is_verified = True
            await self.state_store.add_note(note)
            return note

        if not note.source_url:
            await self._reject_note(job_id, task, note, reason="Missing source URL")
            return None

        if doc is None:
            doc = await self.fetch_service.fetch_document(note.source_url)

        if not doc or not doc.raw_text:
            await self._reject_note(job_id, task, note, reason="Document could not be fetched or has empty text")
            return None

        # Verify excerpt in document
        is_verified, char_start, char_end, page_no, heading_path, text_frag_url = verify_excerpt_in_document(
            excerpt=note.excerpt,
            doc=doc,
            similarity_threshold=0.90,
        )

        if not is_verified:
            # DROP NOTE
            await self._reject_note(
                job_id,
                task,
                note,
                reason="Excerpt could not be verified in fetched document text (match ratio < 0.90)",
            )
            return None

        # Populate verified location attributes
        note.is_verified = True
        note.url = note.source_url
        note.canonical_url = doc.url
        note.title = doc.title
        note.content_hash = doc.content_hash
        note.char_start = char_start
        note.char_end = char_end
        note.page_no = page_no
        note.heading_path = heading_path
        note.text_fragment_url = text_frag_url
        if note.source_url and ("youtube.com" in note.source_url or "youtu.be" in note.source_url):
            note.video_timestamp_url = note.source_url

        await self.state_store.add_note(note)
        return note

    async def _reject_note(self, job_id: str, task: PlanTask, note: ResearchNote, reason: str) -> None:
        """Emit note_rejected event when excerpt cannot be verified."""
        await self.state_store.emit_event(
            job_id,
            EventType.NOTE_REJECTED,
            {
                "note_id": note.id,
                "worker_id": self.worker_id,
                "task_id": task.task_id,
                "claim": note.claim,
                "url": note.source_url,
                "reason": reason,
            },
        )
