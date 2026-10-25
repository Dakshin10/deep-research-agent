from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, List, Optional
from collections import defaultdict

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy import create_engine

from core.state.models import (
    Base,
    JobModel,
    ResearchNoteModel,
    ArtifactModel,
    RunEventModel,
    DocumentModel,
    DocumentChunkModel,
)
from core.state.schemas import (
    Job,
    JobStatus,
    JobMode,
    ResearchNote,
    Artifact,
    RunEvent,
    EventType,
    Brief,
    Plan,
    PlanTask,
    BudgetState,
    TaskStatus,
)


class StateStore:
    """Thread-safe, multi-tenant state store managing jobs, notes, artifacts, and event streaming."""

    # In-memory broadcast queues for SSE clients keyed by job_id
    _subscribers: Dict[str, List[asyncio.Queue]] = defaultdict(list)
    _lock = asyncio.Lock()

    def __init__(
        self,
        tenant_id: str,
        db_url: str = "sqlite+aiosqlite:///:memory:",
        session_factory: Optional[Any] = None,
    ):
        self.tenant_id = tenant_id
        self.db_url = db_url
        self._session_factory = session_factory
        self._engine = None

    async def init_db(self):
        """Initialize database schema if not already initialized."""
        if self._session_factory is None:
            self._engine = create_async_engine(self.db_url, echo=False)
            async with self._engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
                # Auto-migrate SQLite schema for missing columns if table pre-existed
                if "sqlite" in self.db_url:
                    for col, col_type in [
                        ("url", "TEXT"),
                        ("canonical_url", "TEXT"),
                        ("title", "TEXT"),
                        ("source_family", "VARCHAR(64)"),
                        ("provider", "VARCHAR(64)"),
                        ("retrieved_at", "DATETIME"),
                        ("content_hash", "VARCHAR(64)"),
                        ("char_start", "INTEGER"),
                        ("char_end", "INTEGER"),
                        ("page_no", "INTEGER"),
                        ("heading_path", "JSON"),
                        ("text_fragment_url", "TEXT"),
                        ("video_timestamp_url", "TEXT"),
                        ("archive_url", "TEXT"),
                        ("is_verified", "BOOLEAN DEFAULT 0"),
                    ]:
                        try:
                            await conn.execute(text(f"ALTER TABLE research_notes ADD COLUMN {col} {col_type}"))
                        except Exception:
                            pass
            self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)

    async def get_session(self) -> AsyncSession:
        if self._session_factory is None:
            await self.init_db()
        session: AsyncSession = self._session_factory()
        # Set RLS variable for Postgres connections
        if "postgresql" in self.db_url:
            if self.tenant_id:
                await session.execute(
                    text("SET LOCAL app.tenant_id = :tenant_id"),
                    {"tenant_id": self.tenant_id},
                )
            else:
                await session.execute(text("SET LOCAL app.tenant_id = ''"))
        return session

    # ---------------------------------------------------------
    # Job Operations
    # ---------------------------------------------------------
    async def create_job(self, job: Job) -> Job:
        job.tenant_id = self.tenant_id
        async with await self.get_session() as session:
            model = JobModel(
                id=job.id,
                tenant_id=job.tenant_id,
                query=job.query,
                status=job.status.value,
                mode=job.mode.value,
                confidence=job.confidence,
                brief=job.brief.model_dump() if job.brief else None,
                plan=job.plan.model_dump() if job.plan else None,
                report=job.report,
                budget=job.budget.model_dump(),
                created_at=job.created_at,
                updated_at=job.updated_at,
            )
            session.add(model)
            await session.commit()

        await self.emit_event(
            job_id=job.id,
            event_type=EventType.STAGE_STARTED,
            payload={"stage": "job_created", "status": job.status.value, "query": job.query},
        )
        return job

    async def get_job(self, job_id: str) -> Optional[Job]:
        async with await self.get_session() as session:
            stmt = select(JobModel).where(
                JobModel.id == job_id,
                JobModel.tenant_id == self.tenant_id,
            )
            res = await session.execute(stmt)
            model = res.scalar_one_or_none()
            if not model:
                return None

            return Job(
                id=model.id,
                tenant_id=model.tenant_id,
                query=model.query,
                status=JobStatus(model.status),
                mode=JobMode(model.mode),
                confidence=model.confidence or 1.0,
                brief=Brief(**model.brief) if model.brief else None,
                plan=Plan(**model.plan) if model.plan else None,
                report=model.report,
                budget=BudgetState(**model.budget) if model.budget else BudgetState(),
                created_at=model.created_at,
                updated_at=model.updated_at,
            )

    async def update_job(self, job: Job) -> Job:
        job.tenant_id = self.tenant_id
        job.updated_at = datetime.now(timezone.utc)
        async with await self.get_session() as session:
            stmt = select(JobModel).where(
                JobModel.id == job.id,
                JobModel.tenant_id == self.tenant_id,
            )
            res = await session.execute(stmt)
            model = res.scalar_one_or_none()
            if model:
                model.status = job.status.value
                model.mode = job.mode.value
                model.confidence = job.confidence
                model.brief = job.brief.model_dump() if job.brief else None
                model.plan = job.plan.model_dump() if job.plan else None
                model.report = job.report
                model.budget = job.budget.model_dump()
                model.updated_at = job.updated_at
                await session.commit()
        return job

    # ---------------------------------------------------------
    # Note Operations
    # ---------------------------------------------------------
    async def add_note(self, note: ResearchNote) -> ResearchNote:
        note.tenant_id = self.tenant_id
        async with self._task_lock:
            async with await self.get_session() as session:
                model = ResearchNoteModel(
                    id=note.id,
                    job_id=note.job_id,
                    tenant_id=note.tenant_id,
                    claim=note.claim,
                    source_type=note.source_type,
                    source_url=note.source_url,
                    document_id=note.document_id,
                    excerpt=note.excerpt,
                    confidence=note.confidence,
                    task_id=note.task_id,
                    created_at=note.created_at,
                    url=note.url,
                    canonical_url=note.canonical_url,
                    title=note.title,
                    source_family=note.source_family,
                    provider=note.provider,
                    retrieved_at=note.retrieved_at,
                    content_hash=note.content_hash,
                    char_start=note.char_start,
                    char_end=note.char_end,
                    page_no=note.page_no,
                    heading_path=note.heading_path,
                    text_fragment_url=note.text_fragment_url,
                    video_timestamp_url=note.video_timestamp_url,
                    archive_url=note.archive_url,
                    is_verified=note.is_verified,
                )
                session.add(model)
                await session.commit()

        await self.emit_event(
            job_id=note.job_id,
            event_type=EventType.NOTE_ADDED,
            payload={
                "note_id": note.id,
                "task_id": note.task_id,
                "claim": note.claim,
                "source_type": note.source_type,
                "source_url": note.source_url,
                "location": {
                    "page_no": note.page_no,
                    "heading_path": note.heading_path,
                    "char_start": note.char_start,
                    "char_end": note.char_end,
                    "text_fragment_url": note.text_fragment_url,
                },
                "is_verified": note.is_verified,
            },
        )
        return note

    async def get_notes(self, job_id: str, task_id: Optional[str] = None) -> List[ResearchNote]:
        async with await self.get_session() as session:
            stmt = select(ResearchNoteModel).where(
                ResearchNoteModel.job_id == job_id,
                ResearchNoteModel.tenant_id == self.tenant_id,
            )
            if task_id:
                stmt = stmt.where(ResearchNoteModel.task_id == task_id)
            res = await session.execute(stmt)
            models = res.scalars().all()
            return [
                ResearchNote(
                    id=m.id,
                    job_id=m.job_id,
                    tenant_id=m.tenant_id,
                    claim=m.claim,
                    source_type=m.source_type,
                    source_url=m.source_url,
                    document_id=m.document_id,
                    excerpt=m.excerpt,
                    confidence=m.confidence,
                    task_id=m.task_id,
                    created_at=m.created_at,
                    url=m.url,
                    canonical_url=m.canonical_url,
                    title=m.title,
                    source_family=m.source_family,
                    provider=m.provider,
                    retrieved_at=m.retrieved_at,
                    content_hash=m.content_hash,
                    char_start=m.char_start,
                    char_end=m.char_end,
                    page_no=m.page_no,
                    heading_path=m.heading_path or [],
                    text_fragment_url=m.text_fragment_url,
                    video_timestamp_url=m.video_timestamp_url,
                    archive_url=m.archive_url,
                    is_verified=bool(m.is_verified),
                )
                for m in models
            ]

    # ---------------------------------------------------------
    # Artifact Operations
    # ---------------------------------------------------------
    async def add_artifact(self, artifact: Artifact) -> Artifact:
        artifact.tenant_id = self.tenant_id
        async with await self.get_session() as session:
            model = ArtifactModel(
                id=artifact.id,
                job_id=artifact.job_id,
                tenant_id=artifact.tenant_id,
                artifact_type=artifact.artifact_type,
                title=artifact.title,
                file_path=artifact.file_path,
                content=artifact.content,
                metadata_json=artifact.metadata,
                created_at=artifact.created_at,
            )
            session.add(model)
            await session.commit()

        await self.emit_event(
            job_id=artifact.job_id,
            event_type=EventType.ARTIFACT_READY,
            payload={
                "artifact_id": artifact.id,
                "artifact_type": artifact.artifact_type,
                "title": artifact.title,
                "file_path": artifact.file_path,
            },
        )
        return artifact

    async def get_artifacts(self, job_id: str) -> List[Artifact]:
        async with await self.get_session() as session:
            stmt = select(ArtifactModel).where(
                ArtifactModel.job_id == job_id,
                ArtifactModel.tenant_id == self.tenant_id,
            )
            res = await session.execute(stmt)
            models = res.scalars().all()
            return [
                Artifact(
                    id=m.id,
                    job_id=m.job_id,
                    tenant_id=m.tenant_id,
                    artifact_type=m.artifact_type,
                    title=m.title,
                    file_path=m.file_path,
                    content=m.content,
                    metadata=m.metadata_json or {},
                    created_at=m.created_at,
                )
                for m in models
            ]

    # ---------------------------------------------------------
    # Event Operations & SSE Broadcasting
    # ---------------------------------------------------------
    async def emit_event(
        self,
        job_id: str,
        event_type: EventType,
        payload: Optional[Dict[str, Any]] = None,
    ) -> RunEvent:
        event = RunEvent(
            job_id=job_id,
            tenant_id=self.tenant_id,
            event_type=event_type,
            payload=payload or {},
        )
        async with await self.get_session() as session:
            model = RunEventModel(
                id=event.id,
                job_id=event.job_id,
                tenant_id=event.tenant_id,
                event_type=event.event_type.value,
                payload_json=event.payload,
                timestamp=event.timestamp,
            )
            session.add(model)
            await session.commit()

        # Broadcast to all live SSE queues for this job
        queues = self._subscribers.get(job_id, [])
        for q in list(queues):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

        return event

    async def get_events(self, job_id: str) -> List[RunEvent]:
        async with await self.get_session() as session:
            stmt = select(RunEventModel).where(
                RunEventModel.job_id == job_id,
                RunEventModel.tenant_id == self.tenant_id,
            ).order_by(RunEventModel.timestamp.asc())
            res = await session.execute(stmt)
            models = res.scalars().all()
            return [
                RunEvent(
                    id=m.id,
                    job_id=m.job_id,
                    tenant_id=m.tenant_id,
                    event_type=EventType(m.event_type),
                    payload=m.payload_json or {},
                    timestamp=m.timestamp,
                )
                for m in models
            ]

    async def subscribe_events(self, job_id: str) -> AsyncGenerator[RunEvent, None]:
        """Yield events already recorded, then listen for live events."""
        # Yield historical events first
        past_events = await self.get_events(job_id)
        for ev in past_events:
            yield ev

        # If job already completed, stop
        job = await self.get_job(job_id)
        if job and job.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
            return

        # Listen for real-time events
        q: asyncio.Queue[RunEvent] = asyncio.Queue(maxsize=100)
        async with self._lock:
            self._subscribers[job_id].append(q)

        try:
            while True:
                event = await q.get()
                yield event
                if event.event_type in [EventType.DONE, EventType.ERROR]:
                    break
        finally:
            async with self._lock:
                if q in self._subscribers[job_id]:
                    self._subscribers[job_id].remove(q)
                if not self._subscribers[job_id]:
                    self._subscribers.pop(job_id, None)

    # ---------------------------------------------------------
    # Progress & Task Status
    # ---------------------------------------------------------
    _task_lock = asyncio.Lock()

    async def update_task_status(self, job_id: str, task_id: str, status: TaskStatus):
        async with self._task_lock:
            job = await self.get_job(job_id)
            if not job or not job.plan:
                return
            for t in job.plan.tasks:
                if t.task_id == task_id:
                    t.status = status
                    break
            await self.update_job(job)

    # ---------------------------------------------------------
    # Budget Tracking
    # ---------------------------------------------------------
    async def check_budget(
        self,
        job_id: str,
        steps_delta: int = 0,
        tokens_delta: int = 0,
    ) -> BudgetState:
        job = await self.get_job(job_id)
        if not job:
            return BudgetState()

        warning_event = job.budget.check_and_update(steps_delta, tokens_delta)
        if warning_event:
            await self.emit_event(
                job_id=job_id,
                event_type=warning_event,
                payload={
                    "exhausted": job.budget.exhausted,
                    "used_steps": job.budget.used_steps,
                    "used_tokens": job.budget.used_tokens,
                },
            )
        await self.update_job(job)
        return job.budget

    # ---------------------------------------------------------
    # Shared Seen URLs Tracking (Per Job)
    # ---------------------------------------------------------
    _seen_urls: Dict[str, set[str]] = defaultdict(set)
    _seen_lock = asyncio.Lock()

    async def is_url_seen(self, job_id: str, canonical_url: str) -> bool:
        """Check if a canonical URL has already been fetched by any shard in this job."""
        async with self._seen_lock:
            return canonical_url in self._seen_urls[job_id]

    async def mark_url_seen(self, job_id: str, canonical_url: str) -> bool:
        """
        Atomically test-and-set a canonical URL for a job.
        Returns True if the URL was not previously seen (and is now marked),
        False if it was already seen.
        """
        async with self._seen_lock:
            if canonical_url in self._seen_urls[job_id]:
                return False
            self._seen_urls[job_id].add(canonical_url)
            return True
