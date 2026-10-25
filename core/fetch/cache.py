from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from core.fetch.base import DocumentPage, DocumentSection, DocumentTimestamp, FetchedDocument
from core.state.models import Base
from sqlalchemy import Column, String, Text as SAText, Integer, DateTime, JSON


class FetchedDocumentCacheModel(Base):
    __tablename__ = "fetched_documents_cache"

    id = Column(String(64), primary_key=True, default=lambda: f"fd_{uuid.uuid4().hex[:12]}")
    tenant_id = Column(String(64), nullable=False, index=True)
    canonical_url = Column(SAText, nullable=False, index=True)
    content_hash = Column(String(64), nullable=False)
    final_url = Column(SAText, nullable=False)
    status = Column(Integer, nullable=False)
    content_type = Column(String(128), nullable=False)
    title = Column(SAText, nullable=True)
    raw_text = Column(SAText, nullable=False)
    sections_json = Column(JSON, default=list)
    pages_json = Column(JSON, default=list)
    timestamps_json = Column(JSON, default=list)
    fetched_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime, nullable=False, index=True)


class FetchedDocumentCache:
    """Tenant-scoped fetched document cache with database persistence and memory fallback."""

    def __init__(self, session_factory: Optional[Any] = None, default_ttl_seconds: float = 604800.0):
        self.session_factory = session_factory
        self.default_ttl_seconds = default_ttl_seconds
        # In-memory fallback: (tenant_id, canonical_url) -> (FetchedDocument, expires_at_timestamp)
        self._mem_cache: Dict[tuple[str, str], tuple[FetchedDocument, float]] = {}
        self._lock = asyncio.Lock()

    async def get(
        self,
        canonical_url: str,
        content_hash: Optional[str] = None,
        tenant_id: str = "default_tenant",
    ) -> Optional[FetchedDocument]:
        """Retrieve a cached document if not expired."""
        now = datetime.now(timezone.utc)
        now_ts = now.timestamp()

        # Check DB if session_factory is present
        if self.session_factory:
            try:
                async with self.session_factory() as session:
                    # Apply tenant filter
                    stmt = select(FetchedDocumentCacheModel).where(
                        FetchedDocumentCacheModel.tenant_id == tenant_id,
                        FetchedDocumentCacheModel.canonical_url == canonical_url,
                        FetchedDocumentCacheModel.expires_at > now,
                    )
                    if content_hash:
                        stmt = stmt.where(FetchedDocumentCacheModel.content_hash == content_hash)
                    res = await session.execute(stmt)
                    model = res.scalars().first()
                    if model:
                        return FetchedDocument(
                            url=model.canonical_url,
                            final_url=model.final_url,
                            status=model.status,
                            content_type=model.content_type,
                            fetched_at=model.fetched_at,
                            content_hash=model.content_hash,
                            title=model.title or "",
                            raw_text=model.raw_text,
                            sections=[DocumentSection(**s) for s in (model.sections_json or [])],
                            pages=[DocumentPage(**p) for p in (model.pages_json or [])],
                            timestamps=[DocumentTimestamp(**t) for t in (model.timestamps_json or [])],
                        )
            except Exception:
                pass

        # Check in-memory cache
        async with self._lock:
            cached = self._mem_cache.get((tenant_id, canonical_url))
            if cached:
                doc, exp = cached
                if exp > now_ts:
                    if content_hash is None or doc.content_hash == content_hash:
                        return doc
                else:
                    self._mem_cache.pop((tenant_id, canonical_url), None)

        return None

    async def put(
        self,
        doc: FetchedDocument,
        tenant_id: str = "default_tenant",
        ttl_seconds: Optional[float] = None,
    ) -> None:
        """Cache a fetched document with expiration TTL."""
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl_seconds
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=ttl)

        # Store in DB if available
        if self.session_factory:
            try:
                async with self.session_factory() as session:
                    model = FetchedDocumentCacheModel(
                        tenant_id=tenant_id,
                        canonical_url=doc.url,
                        content_hash=doc.content_hash,
                        final_url=doc.final_url or doc.url,
                        status=doc.status,
                        content_type=doc.content_type,
                        title=doc.title,
                        raw_text=doc.raw_text,
                        sections_json=[s.model_dump() for s in doc.sections],
                        pages_json=[p.model_dump() for p in doc.pages],
                        timestamps_json=[t.model_dump() for t in doc.timestamps],
                        fetched_at=doc.fetched_at,
                        expires_at=expires_at,
                    )
                    session.add(model)
                    await session.commit()
            except Exception:
                pass

        # Store in in-memory cache
        async with self._lock:
            self._mem_cache[(tenant_id, doc.url)] = (doc, expires_at.timestamp())
