from __future__ import annotations

from datetime import datetime, timezone, timedelta
import math
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple
import uuid
import yaml
from pydantic import BaseModel, Field
from sqlalchemy import select, or_, and_, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.fetch.base import FetchedDocument
from core.fetch.location import generate_text_fragment_url
from core.knowledge.embedder import EmbeddingModel
from core.search.base import SearchHit
from core.search.canonical import normalize_canonical_url
from core.state.models import Base, WebIndexChunkModel
from core.state.schemas import ResearchNote


class WebIndexHit(BaseModel):
    id: str
    url: str
    canonical_url: str
    title: str = ""
    passage_text: str
    source_family: str = "web_general"
    char_start: Optional[int] = None
    char_end: Optional[int] = None
    page_no: Optional[int] = None
    heading_path: List[str] = Field(default_factory=list)
    text_fragment_url: Optional[str] = None
    score: float = 1.0
    is_stale: bool = False
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class WebIndexStore:
    """
    Tenant-scoped persistent web index of fetched, verified passages.
    Provides hybrid retrieval (vector cosine similarity + full-text/keyword search)
    and automated TTL-based re-crawl lifecycle tracking per source family.
    """

    DEFAULT_TTL_DAYS: Dict[str, int] = {
        "news": 1,
        "social": 2,
        "forums": 7,
        "web_general": 14,
        "app_stores": 14,
        "code": 30,
        "academic": 90,
        "archives": 180,
    }

    def __init__(
        self,
        tenant_id: str,
        db_url: str = "sqlite+aiosqlite:///:memory:",
        session_factory: Optional[Any] = None,
        vector_weight: float = 0.65,
        keyword_weight: float = 0.35,
        config_path: Optional[str] = None,
    ):
        self.tenant_id = tenant_id
        self.db_url = db_url
        self._session_factory = session_factory
        self.vector_weight = vector_weight
        self.keyword_weight = keyword_weight
        self.embedder = EmbeddingModel()
        self._engine = None

        # Load TTL configs if available
        self.ttl_days = dict(self.DEFAULT_TTL_DAYS)
        cfg_file = Path(config_path or os.path.join("config", "search.yaml"))
        if cfg_file.exists():
            try:
                with open(cfg_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                    w_cfg = data.get("web_index", {})
                    self.vector_weight = w_cfg.get("vector_weight", self.vector_weight)
                    self.keyword_weight = w_cfg.get("keyword_weight", self.keyword_weight)
                    if "ttl_days" in w_cfg:
                        self.ttl_days.update(w_cfg["ttl_days"])
            except Exception:
                pass

    async def init_db(self):
        if self._session_factory is None:
            self._engine = create_async_engine(self.db_url, echo=False)
            async with self._engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)

    async def get_session(self) -> AsyncSession:
        if self._session_factory is None:
            await self.init_db()
        session: AsyncSession = self._session_factory()
        if "postgresql" in self.db_url:
            if self.tenant_id:
                await session.execute(
                    text("SET LOCAL app.tenant_id = :tenant_id"),
                    {"tenant_id": self.tenant_id},
                )
            else:
                await session.execute(text("SET LOCAL app.tenant_id = ''"))
        return session

    # -------------------------------------------------------------------------
    # Ingestion & Indexing
    # -------------------------------------------------------------------------

    async def index_note_passage(self, note: ResearchNote, doc: Optional[FetchedDocument] = None) -> str:
        """Stores a verified research note passage into the tenant's web index."""
        if not note.excerpt:
            return ""

        passage_text = note.excerpt
        vec = self.embedder.embed_text(passage_text)
        canonical = note.canonical_url or normalize_canonical_url(note.url or note.source_url or "https://example.com")
        frag_url = note.text_fragment_url or (generate_text_fragment_url(note.url or "", passage_text) if note.url else None)

        chunk_id = f"widx_{uuid.uuid4().hex[:8]}"
        now = datetime.now(timezone.utc)

        async with await self.get_session() as session:
            model = WebIndexChunkModel(
                id=chunk_id,
                tenant_id=self.tenant_id,
                url=note.url or note.source_url or canonical,
                canonical_url=canonical,
                title=note.title or (doc.title if doc else ""),
                source_family=note.source_family or "web_general",
                passage_text=passage_text,
                char_start=note.char_start,
                char_end=note.char_end,
                page_no=note.page_no,
                heading_path=note.heading_path or [],
                text_fragment_url=frag_url,
                embedding=vec,
                created_at=now,
                updated_at=now,
                is_stale=False,
            )
            session.add(model)
            await session.commit()

        return chunk_id

    async def index_document(
        self,
        doc: FetchedDocument,
        source_family: str = "web_general",
        chunk_size: int = 500,
    ) -> List[str]:
        """Indexes sections or raw text chunks from a FetchedDocument into the tenant's web index."""
        if not doc.raw_text:
            return []

        canonical = normalize_canonical_url(doc.final_url or doc.url)
        chunk_ids: List[str] = []
        now = datetime.now(timezone.utc)

        # 1. Index sections if present
        if doc.sections:
            async with await self.get_session() as session:
                for sec in doc.sections:
                    if len(sec.text.strip()) < 30:
                        continue
                    vec = self.embedder.embed_text(sec.text)
                    frag_url = generate_text_fragment_url(doc.final_url or doc.url, sec.text[:120])
                    cid = f"widx_{uuid.uuid4().hex[:8]}"
                    model = WebIndexChunkModel(
                        id=cid,
                        tenant_id=self.tenant_id,
                        url=doc.final_url or doc.url,
                        canonical_url=canonical,
                        title=doc.title or "",
                        source_family=source_family,
                        passage_text=sec.text,
                        char_start=sec.char_start,
                        char_end=sec.char_end,
                        heading_path=sec.heading_path or [],
                        text_fragment_url=frag_url,
                        embedding=vec,
                        created_at=now,
                        updated_at=now,
                        is_stale=False,
                    )
                    session.add(model)
                    chunk_ids.append(cid)
                await session.commit()
            return chunk_ids

        # 2. Linear chunk fallback
        raw = doc.raw_text
        step = chunk_size - 80
        passages: List[Tuple[str, int, int]] = []
        for i in range(0, len(raw), step):
            sub = raw[i : i + chunk_size].strip()
            if len(sub) >= 40:
                passages.append((sub, i, min(len(raw), i + chunk_size)))

        async with await self.get_session() as session:
            for text_chunk, c_start, c_end in passages:
                vec = self.embedder.embed_text(text_chunk)
                frag_url = generate_text_fragment_url(doc.final_url or doc.url, text_chunk[:100])
                cid = f"widx_{uuid.uuid4().hex[:8]}"
                model = WebIndexChunkModel(
                    id=cid,
                    tenant_id=self.tenant_id,
                    url=doc.final_url or doc.url,
                    canonical_url=canonical,
                    title=doc.title or "",
                    source_family=source_family,
                    passage_text=text_chunk,
                    char_start=c_start,
                    char_end=c_end,
                    heading_path=[],
                    text_fragment_url=frag_url,
                    embedding=vec,
                    created_at=now,
                    updated_at=now,
                    is_stale=False,
                )
                session.add(model)
                chunk_ids.append(cid)
            await session.commit()

        return chunk_ids

    # -------------------------------------------------------------------------
    # Hybrid Retrieval (Vector + Keyword BM25)
    # -------------------------------------------------------------------------

    async def hybrid_search(
        self,
        query: str,
        limit: int = 5,
        source_family: Optional[str] = None,
        include_stale: bool = False,
    ) -> List[WebIndexHit]:
        """
        Executes tenant-scoped hybrid retrieval:
        score = (vector_weight * vector_sim) + (keyword_weight * keyword_sim)
        """
        query_vec = self.embedder.embed_text(query)
        query_words = set(re.findall(r"\w+", query.lower()))

        async with await self.get_session() as session:
            conditions = [WebIndexChunkModel.tenant_id == self.tenant_id]
            if not include_stale:
                conditions.append(WebIndexChunkModel.is_stale == False)
            if source_family:
                conditions.append(WebIndexChunkModel.source_family == source_family)

            stmt = select(WebIndexChunkModel).where(and_(*conditions))
            res = await session.execute(stmt)
            models = res.scalars().all()

        scored: List[Tuple[WebIndexHit, float]] = []
        for m in models:
            # 1. Cosine similarity
            vec_sim = self.embedder.cosine_similarity(query_vec, m.embedding or [])

            # 2. Keyword overlap / lexical match
            passage_words = set(re.findall(r"\w+", m.passage_text.lower()))
            overlap = len(query_words.intersection(passage_words))
            kw_score = overlap / max(1, len(query_words))

            # 3. Hybrid score
            h_score = (self.vector_weight * vec_sim) + (self.keyword_weight * kw_score)

            hit = WebIndexHit(
                id=m.id,
                url=m.url,
                canonical_url=m.canonical_url,
                title=m.title or "",
                passage_text=m.passage_text,
                source_family=m.source_family,
                char_start=m.char_start,
                char_end=m.char_end,
                page_no=m.page_no,
                heading_path=m.heading_path or [],
                text_fragment_url=m.text_fragment_url,
                score=round(h_score, 4),
                is_stale=m.is_stale,
                updated_at=m.updated_at or datetime.now(timezone.utc),
            )
            scored.append((hit, h_score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [item[0] for item in scored[:limit]]

    # -------------------------------------------------------------------------
    # Stale Lifecycle & Re-crawl
    # -------------------------------------------------------------------------

    async def mark_stale_entries(self, ttl_days_by_family: Optional[Dict[str, int]] = None) -> int:
        """
        Audits all index entries for this tenant and marks records older than their
        source_family TTL as is_stale=True.
        """
        ttls = ttl_days_by_family or self.ttl_days
        now = datetime.now(timezone.utc)
        marked_count = 0

        async with await self.get_session() as session:
            stmt = select(WebIndexChunkModel).where(
                WebIndexChunkModel.tenant_id == self.tenant_id,
                WebIndexChunkModel.is_stale == False,
            )
            res = await session.execute(stmt)
            records = res.scalars().all()

            for rec in records:
                fam = rec.source_family or "web_general"
                ttl_days = ttls.get(fam, ttls.get("web_general", 14))
                threshold = rec.updated_at or rec.created_at or now
                # Ensure timezone awareness for offset calculation
                if threshold.tzinfo is None:
                    threshold = threshold.replace(tzinfo=timezone.utc)
                if now - threshold > timedelta(days=ttl_days):
                    rec.is_stale = True
                    marked_count += 1

            if marked_count > 0:
                await session.commit()

        return marked_count

    async def get_stale_urls(self, limit: int = 50) -> List[Tuple[str, str]]:
        """Returns list of unique (canonical_url, source_family) pairs that are marked stale."""
        async with await self.get_session() as session:
            stmt = (
                select(WebIndexChunkModel.canonical_url, WebIndexChunkModel.source_family)
                .where(
                    WebIndexChunkModel.tenant_id == self.tenant_id,
                    WebIndexChunkModel.is_stale == True,
                )
                .distinct()
                .limit(limit)
            )
            res = await session.execute(stmt)
            return [(row[0], row[1]) for row in res.all()]

    async def recrawl_stale_entries(
        self,
        fetch_service: Any,
        limit: int = 5,
    ) -> int:
        """
        Re-crawls stale canonical URLs using fetch_service, updates index passages,
        refreshes timestamps, and resets is_stale=False.
        """
        stale_targets = await self.get_stale_urls(limit=limit)
        if not stale_targets:
            return 0

        refreshed_count = 0
        now = datetime.now(timezone.utc)

        for canonical_url, family in stale_targets:
            try:
                doc = await fetch_service.fetch_document(canonical_url)
                if doc and not doc.is_blocked and doc.raw_text:
                    # Remove old stale entries for this canonical URL
                    async with await self.get_session() as session:
                        stmt = select(WebIndexChunkModel).where(
                            WebIndexChunkModel.tenant_id == self.tenant_id,
                            WebIndexChunkModel.canonical_url == canonical_url,
                        )
                        res = await session.execute(stmt)
                        old_records = res.scalars().all()
                        for r in old_records:
                            await session.delete(r)
                        await session.commit()

                    # Re-index fresh content
                    await self.index_document(doc, source_family=family)
                    refreshed_count += 1
            except Exception:
                pass

        return refreshed_count


class WebIndexProvider:
    """SearchProvider adapter wrapping the tenant-scoped WebIndexStore."""

    def __init__(self, web_index_store: WebIndexStore):
        self.store = web_index_store

    async def search(
        self,
        query: str,
        *,
        limit: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[SearchHit]:
        family = filters.get("source_family") if filters else None
        hits = await self.store.hybrid_search(query, limit=limit, source_family=family)

        results: List[SearchHit] = []
        for rank, h in enumerate(hits, start=1):
            results.append(
                SearchHit(
                    url=h.url,
                    canonical_url=h.canonical_url,
                    title=f"[Local Index] {h.title or h.url}",
                    snippet=h.passage_text[:350],
                    source_family=h.source_family,
                    provider="web_index",
                    published_at=h.updated_at,
                    rank=rank,
                    raw_score=h.score,
                    raw={
                        "char_start": h.char_start,
                        "char_end": h.char_end,
                        "page_no": h.page_no,
                        "heading_path": h.heading_path,
                        "text_fragment_url": h.text_fragment_url,
                        "is_stale": h.is_stale,
                    },
                )
            )
        return results
