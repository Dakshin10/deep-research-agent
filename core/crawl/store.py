from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
import json
import os
from typing import Any, AsyncGenerator, Dict, List, Optional
import uuid

from sqlalchemy import (
    Column,
    String,
    Text,
    Integer,
    BigInteger,
    Boolean,
    DateTime,
    JSON,
    select,
    update,
    text,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from core.crawl.schemas import (
    CrawlEvent,
    CrawlMode,
    CrawlRunConfig,
    CrawlRunRecord,
    CrawlRunStatus,
    FrontierItem,
    FrontierState,
)

Base = declarative_base()


class CrawlSourceModel(Base):
    __tablename__ = "crawl_sources"

    source_id = Column(String(64), primary_key=True)
    domain = Column(String(255), nullable=False)
    name = Column(String(128), nullable=False)
    is_active = Column(Boolean, default=True)
    config_json = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class CrawlFrontierModel(Base):
    __tablename__ = "crawl_frontier"

    id = Column(String(64), primary_key=True)
    url = Column(Text, nullable=False)
    canonical_url = Column(Text, nullable=False)
    source = Column(String(64), nullable=False)
    state = Column(String(32), nullable=False, default=FrontierState.PENDING.value)
    priority = Column(Integer, nullable=False, default=10)
    attempts = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=3)
    next_attempt_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_etag = Column(String(128), nullable=True)
    last_modified = Column(String(128), nullable=True)
    content_hash = Column(String(64), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class CrawlRunModel(Base):
    __tablename__ = "crawl_runs"

    id = Column(String(64), primary_key=True)
    source = Column(String(64), nullable=False)
    mode = Column(String(32), nullable=False, default=CrawlMode.ALL.value)
    status = Column(String(32), nullable=False, default=CrawlRunStatus.RUNNING.value)
    since_date = Column(String(32), nullable=True)
    limit_pages = Column(Integer, default=1000)
    pages_discovered = Column(Integer, default=0)
    pages_crawled = Column(Integer, default=0)
    pages_skipped = Column(Integer, default=0)
    bytes_downloaded = Column(BigInteger, default=0)
    errors_count = Column(Integer, default=0)
    errors_by_domain = Column(JSON, default=dict)
    started_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    finished_at = Column(DateTime(timezone=True), nullable=True)
    config_override = Column(JSON, default=dict)


class CrawlStore:
    """
    Manages crawl sources, crawl frontier items, and crawl runs with ACID guarantees.
    Supports PostgreSQL 'SELECT ... FOR UPDATE SKIP LOCKED' and local SQLite testing.
    """

    def __init__(
        self,
        db_url: str = "sqlite+aiosqlite:///:memory:",
        session_factory: Optional[async_sessionmaker] = None,
    ):
        self.db_url = db_url
        self._session_factory = session_factory
        self._engine = None
        self._write_lock = asyncio.Lock()
        self._subscribers: Dict[str, List[asyncio.Queue]] = {}

    async def get_session(self) -> AsyncSession:
        if not self._session_factory:
            self._engine = create_async_engine(self.db_url, echo=False)
            self._session_factory = async_sessionmaker(
                self._engine, class_=AsyncSession, expire_on_commit=False
            )
        return self._session_factory()

    async def init_db(self) -> None:
        async with await self.get_session() as session:
            conn = await session.connection()
            await conn.run_sync(Base.metadata.create_all)
            await session.commit()

    async def add_frontier_items(self, items: List[FrontierItem]) -> int:
        """
        Idempotently inserts frontier items. Skips items where (source, canonical_url) already exists.
        Returns count of newly added items.
        """
        if not items:
            return 0

        added = 0
        async with self._write_lock:
            async with await self.get_session() as session:
                for item in items:
                    # Check if already exists
                    stmt = select(CrawlFrontierModel).where(
                        CrawlFrontierModel.source == item.source,
                        CrawlFrontierModel.canonical_url == item.canonical_url,
                    )
                    existing = (await session.execute(stmt)).scalars().first()
                    if not existing:
                        model = CrawlFrontierModel(
                            id=item.id or f"cf_{uuid.uuid4().hex[:12]}",
                            url=item.url,
                            canonical_url=item.canonical_url,
                            source=item.source,
                            state=item.state.value,
                            priority=item.priority,
                            attempts=item.attempts,
                            max_attempts=item.max_attempts,
                            next_attempt_at=item.next_attempt_at,
                            last_etag=item.last_etag,
                            last_modified=item.last_modified,
                            content_hash=item.content_hash,
                            created_at=item.created_at,
                            updated_at=item.updated_at,
                        )
                        session.add(model)
                        added += 1
                await session.commit()
        return added

    async def claim_frontier_items(
        self,
        batch_size: int = 10,
        source: Optional[str] = None,
    ) -> List[FrontierItem]:
        """
        Claims a batch of pending frontier items for worker execution.
        Uses SELECT ... FOR UPDATE SKIP LOCKED on Postgres, or transaction lock on SQLite.
        Marks claimed items as RUNNING.
        """
        now = datetime.now(timezone.utc)
        items: List[FrontierItem] = []

        async with self._write_lock:
            async with await self.get_session() as session:
                is_postgres = "postgresql" in self.db_url

                if is_postgres:
                    # Native SELECT ... FOR UPDATE SKIP LOCKED
                    query_str = (
                        "SELECT id, url, canonical_url, source, state, priority, attempts, max_attempts, "
                        "next_attempt_at, last_etag, last_modified, content_hash "
                        "FROM crawl_frontier "
                        "WHERE state = :pending_state AND next_attempt_at <= :now "
                    )
                    params: Dict[str, Any] = {"pending_state": FrontierState.PENDING.value, "now": now}
                    if source:
                        query_str += "AND source = :source "
                        params["source"] = source
                    query_str += "ORDER BY priority DESC, next_attempt_at ASC "
                    query_str += f"LIMIT {batch_size} FOR UPDATE SKIP LOCKED"

                    result = await session.execute(text(query_str), params)
                    rows = result.fetchall()
                    ids_to_update = [r[0] for r in rows]

                    if ids_to_update:
                        await session.execute(
                            update(CrawlFrontierModel)
                            .where(CrawlFrontierModel.id.in_(ids_to_update))
                            .values(
                                state=FrontierState.RUNNING.value,
                                attempts=CrawlFrontierModel.attempts + 1,
                                updated_at=now,
                            )
                        )
                        await session.commit()

                    for r in rows:
                        items.append(
                            FrontierItem(
                                id=r[0],
                                url=r[1],
                                canonical_url=r[2],
                                source=r[3],
                                state=FrontierState.RUNNING,
                                priority=r[5],
                                attempts=r[6] + 1,
                                max_attempts=r[7],
                                next_attempt_at=r[8],
                                last_etag=r[9],
                                last_modified=r[10],
                                content_hash=r[11],
                            )
                        )
                else:
                    # SQLite emulation with write lock
                    stmt = select(CrawlFrontierModel).where(
                        CrawlFrontierModel.state == FrontierState.PENDING.value,
                        CrawlFrontierModel.next_attempt_at <= now,
                    )
                    if source:
                        stmt = stmt.where(CrawlFrontierModel.source == source)
                    stmt = stmt.order_by(
                        CrawlFrontierModel.priority.desc(),
                        CrawlFrontierModel.next_attempt_at.asc(),
                    ).limit(batch_size)

                    models = (await session.execute(stmt)).scalars().all()
                    for m in models:
                        m.state = FrontierState.RUNNING.value
                        m.attempts += 1
                        m.updated_at = now
                        items.append(
                            FrontierItem(
                                id=m.id,
                                url=m.url,
                                canonical_url=m.canonical_url,
                                source=m.source,
                                state=FrontierState.RUNNING,
                                priority=m.priority,
                                attempts=m.attempts,
                                max_attempts=m.max_attempts,
                                next_attempt_at=m.next_attempt_at,
                                last_etag=m.last_etag,
                                last_modified=m.last_modified,
                                content_hash=m.content_hash,
                            )
                        )
                    await session.commit()

        return items

    async def mark_frontier_completed(
        self,
        item_id: str,
        content_hash: Optional[str] = None,
        last_etag: Optional[str] = None,
        last_modified: Optional[str] = None,
    ) -> None:
        now = datetime.now(timezone.utc)
        async with self._write_lock:
            async with await self.get_session() as session:
                stmt = (
                    update(CrawlFrontierModel)
                    .where(CrawlFrontierModel.id == item_id)
                    .values(
                        state=FrontierState.COMPLETED.value,
                        content_hash=content_hash,
                        last_etag=last_etag,
                        last_modified=last_modified,
                        error_message=None,
                        updated_at=now,
                    )
                )
                await session.execute(stmt)
                await session.commit()

    async def mark_frontier_skipped(self, item_id: str) -> None:
        now = datetime.now(timezone.utc)
        async with self._write_lock:
            async with await self.get_session() as session:
                stmt = (
                    update(CrawlFrontierModel)
                    .where(CrawlFrontierModel.id == item_id)
                    .values(
                        state=FrontierState.SKIPPED.value,
                        updated_at=now,
                    )
                )
                await session.execute(stmt)
                await session.commit()

    async def mark_frontier_failed(
        self,
        item_id: str,
        error: str,
        backoff_seconds: float = 60.0,
    ) -> None:
        now = datetime.now(timezone.utc)
        next_attempt = now + timedelta(seconds=backoff_seconds)
        async with self._write_lock:
            async with await self.get_session() as session:
                m = (
                    await session.execute(
                        select(CrawlFrontierModel).where(CrawlFrontierModel.id == item_id)
                    )
                ).scalars().first()
                if m:
                    m.error_message = str(error)
                    m.updated_at = now
                    if m.attempts >= m.max_attempts:
                        m.state = FrontierState.FAILED.value
                    else:
                        m.state = FrontierState.PENDING.value
                        m.next_attempt_at = next_attempt
                await session.commit()

    # --- Crawl Runs ---

    async def create_crawl_run(self, run: CrawlRunRecord) -> CrawlRunRecord:
        async with self._write_lock:
            async with await self.get_session() as session:
                model = CrawlRunModel(
                    id=run.id,
                    source=run.source,
                    mode=run.mode.value if isinstance(run.mode, CrawlMode) else run.mode,
                    status=run.status.value if isinstance(run.status, CrawlRunStatus) else run.status,
                    since_date=run.since_date,
                    limit_pages=run.limit_pages,
                    pages_discovered=run.pages_discovered,
                    pages_crawled=run.pages_crawled,
                    pages_skipped=run.pages_skipped,
                    bytes_downloaded=run.bytes_downloaded,
                    errors_count=run.errors_count,
                    errors_by_domain=run.errors_by_domain,
                    started_at=run.started_at,
                    finished_at=run.finished_at,
                    config_override=run.config_override,
                )
                session.add(model)
                await session.commit()
        return run

    async def update_crawl_run(
        self,
        run_id: str,
        *,
        status: Optional[CrawlRunStatus] = None,
        pages_discovered: Optional[int] = None,
        pages_crawled: Optional[int] = None,
        pages_skipped: Optional[int] = None,
        bytes_downloaded: Optional[int] = None,
        errors_count: Optional[int] = None,
        errors_by_domain: Optional[Dict[str, int]] = None,
        finished: bool = False,
    ) -> None:
        now = datetime.now(timezone.utc)
        values: Dict[str, Any] = {}
        if status:
            values["status"] = status.value
        if pages_discovered is not None:
            values["pages_discovered"] = pages_discovered
        if pages_crawled is not None:
            values["pages_crawled"] = pages_crawled
        if pages_skipped is not None:
            values["pages_skipped"] = pages_skipped
        if bytes_downloaded is not None:
            values["bytes_downloaded"] = bytes_downloaded
        if errors_count is not None:
            values["errors_count"] = errors_count
        if errors_by_domain is not None:
            values["errors_by_domain"] = errors_by_domain
        if finished:
            values["finished_at"] = now
            if not status:
                values["status"] = CrawlRunStatus.COMPLETED.value

        if not values:
            return

        async with self._write_lock:
            async with await self.get_session() as session:
                await session.execute(
                    update(CrawlRunModel).where(CrawlRunModel.id == run_id).values(**values)
                )
                await session.commit()

    async def get_crawl_run(self, run_id: str) -> Optional[CrawlRunRecord]:
        async with await self.get_session() as session:
            stmt = select(CrawlRunModel).where(CrawlRunModel.id == run_id)
            m = (await session.execute(stmt)).scalars().first()
            if not m:
                return None
            return CrawlRunRecord(
                id=m.id,
                source=m.source,
                mode=CrawlMode(m.mode),
                status=CrawlRunStatus(m.status),
                since_date=m.since_date,
                limit_pages=m.limit_pages,
                pages_discovered=m.pages_discovered,
                pages_crawled=m.pages_crawled,
                pages_skipped=m.pages_skipped,
                bytes_downloaded=m.bytes_downloaded,
                errors_count=m.errors_count,
                errors_by_domain=m.errors_by_domain or {},
                started_at=m.started_at,
                finished_at=m.finished_at,
                config_override=m.config_override or {},
            )

    async def list_crawl_runs(self, limit: int = 50) -> List[CrawlRunRecord]:
        async with await self.get_session() as session:
            stmt = select(CrawlRunModel).order_by(CrawlRunModel.started_at.desc()).limit(limit)
            models = (await session.execute(stmt)).scalars().all()
            return [
                CrawlRunRecord(
                    id=m.id,
                    source=m.source,
                    mode=CrawlMode(m.mode),
                    status=CrawlRunStatus(m.status),
                    since_date=m.since_date,
                    limit_pages=m.limit_pages,
                    pages_discovered=m.pages_discovered,
                    pages_crawled=m.pages_crawled,
                    pages_skipped=m.pages_skipped,
                    bytes_downloaded=m.bytes_downloaded,
                    errors_count=m.errors_count,
                    errors_by_domain=m.errors_by_domain or {},
                    started_at=m.started_at,
                    finished_at=m.finished_at,
                    config_override=m.config_override or {},
                )
                for m in models
            ]

    # --- Real-Time Crawl Events (SSE) ---

    async def emit_event(self, event: CrawlEvent) -> None:
        queues = self._subscribers.get(event.run_id, [])
        for q in list(queues):
            try:
                q.put_nowait(event)
            except Exception:
                pass

    async def subscribe_events(self, run_id: str) -> AsyncGenerator[CrawlEvent, None]:
        q: asyncio.Queue[CrawlEvent] = asyncio.Queue()
        if run_id not in self._subscribers:
            self._subscribers[run_id] = []
        self._subscribers[run_id].append(q)
        try:
            while True:
                evt = await q.get()
                yield evt
                if evt.event_type in ("crawl_completed", "crawl_failed"):
                    break
        finally:
            if run_id in self._subscribers and q in self._subscribers[run_id]:
                self._subscribers[run_id].remove(q)
