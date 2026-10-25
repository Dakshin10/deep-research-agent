from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import math
from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy import (
    Column,
    String,
    Text,
    Integer,
    Float,
    DateTime,
    JSON,
    select,
    update,
    or_,
    and_,
    text,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from core.ideas.schemas import IdeaRecord, ProjectPlacement, ProjectStage, EvidenceEntry
from core.knowledge.embedder import EmbeddingModel

Base = declarative_base()


class IdeaRecordModel(Base):
    __tablename__ = "idea_records"

    id = Column(String(64), primary_key=True)
    tenant_id = Column(String(64), nullable=True)
    name = Column(String(255), nullable=False)
    one_liner = Column(Text, nullable=True)
    problem = Column(Text, nullable=True)
    solution = Column(Text, nullable=True)
    target_users = Column(Text, nullable=True)
    domain_tags = Column(JSON, default=list)
    tech_stack = Column(JSON, default=list)
    business_model = Column(Text, nullable=True)
    stage = Column(String(32), default=ProjectStage.PROTOTYPE.value)
    traction = Column(Text, nullable=True)
    source_kind = Column(String(32), default="hackathon")
    event_name = Column(String(255), nullable=True)
    year = Column(Integer, nullable=True)
    placement = Column(String(32), default=ProjectPlacement.NONE.value)
    team_size = Column(Integer, nullable=True)
    links = Column(JSON, default=dict)
    first_seen_url = Column(Text, nullable=False)
    all_source_urls = Column(JSON, default=list)
    confidence = Column(Float, default=1.0)
    evidence = Column(JSON, default=dict)
    embedding = Column(JSON, nullable=True)  # JSON for SQLite, vector(384) in Postgres
    merged_into_id = Column(String(64), nullable=True)
    merge_history = Column(JSON, default=list)
    extracted_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class IdeaStore:
    """
    Persistent store for IdeaRecord entities with multi-tenant isolation,
    pgvector hybrid dense/sparse retrieval, and domain/placement/year filters.
    """

    def __init__(
        self,
        tenant_id: Optional[str] = None,
        db_url: str = "sqlite+aiosqlite:///:memory:",
        session_factory: Optional[async_sessionmaker] = None,
        embedder: Optional[EmbeddingModel] = None,
    ):
        self.tenant_id = tenant_id
        self.db_url = db_url
        self._session_factory = session_factory
        self._engine = None
        self._write_lock = asyncio.Lock()
        self.embedder = embedder or EmbeddingModel()

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

    def _to_record(self, m: IdeaRecordModel) -> IdeaRecord:
        ev_dict: Dict[str, EvidenceEntry] = {}
        if m.evidence:
            for k, v in m.evidence.items():
                if isinstance(v, dict):
                    ev_dict[k] = EvidenceEntry(**v)

        return IdeaRecord(
            id=m.id,
            tenant_id=m.tenant_id,
            name=m.name,
            one_liner=m.one_liner,
            problem=m.problem,
            solution=m.solution,
            target_users=m.target_users,
            domain_tags=m.domain_tags or [],
            tech_stack=m.tech_stack or [],
            business_model=m.business_model,
            stage=ProjectStage(m.stage) if m.stage else ProjectStage.PROTOTYPE,
            traction=m.traction,
            source_kind=m.source_kind or "hackathon",
            event_name=m.event_name,
            year=m.year,
            placement=ProjectPlacement(m.placement) if m.placement else ProjectPlacement.NONE,
            team_size=m.team_size,
            links=m.links or {},
            first_seen_url=m.first_seen_url,
            all_source_urls=m.all_source_urls or [],
            confidence=m.confidence or 1.0,
            evidence=ev_dict,
            embedding=m.embedding,
            merged_into_id=m.merged_into_id,
            merge_history=m.merge_history or [],
            extracted_at=m.extracted_at,
            created_at=m.created_at,
            updated_at=m.updated_at,
        )

    async def save_idea(self, record: IdeaRecord) -> IdeaRecord:
        """Saves or updates an IdeaRecord."""
        now = datetime.now(timezone.utc)
        record.updated_at = now
        ev_json = {k: v.model_dump() for k, v in record.evidence.items()}

        async with self._write_lock:
            async with await self.get_session() as session:
                stmt = select(IdeaRecordModel).where(IdeaRecordModel.id == record.id)
                m = (await session.execute(stmt)).scalars().first()
                if not m:
                    m = IdeaRecordModel(
                        id=record.id,
                        tenant_id=record.tenant_id,
                        name=record.name,
                        one_liner=record.one_liner,
                        problem=record.problem,
                        solution=record.solution,
                        target_users=record.target_users,
                        domain_tags=record.domain_tags,
                        tech_stack=record.tech_stack,
                        business_model=record.business_model,
                        stage=record.stage.value,
                        traction=record.traction,
                        source_kind=record.source_kind,
                        event_name=record.event_name,
                        year=record.year,
                        placement=record.placement.value,
                        team_size=record.team_size,
                        links=record.links,
                        first_seen_url=record.first_seen_url,
                        all_source_urls=record.all_source_urls,
                        confidence=record.confidence,
                        evidence=ev_json,
                        embedding=record.embedding,
                        merged_into_id=record.merged_into_id,
                        merge_history=record.merge_history,
                        extracted_at=record.extracted_at,
                        created_at=record.created_at,
                        updated_at=now,
                    )
                    session.add(m)
                else:
                    m.name = record.name
                    m.one_liner = record.one_liner
                    m.problem = record.problem
                    m.solution = record.solution
                    m.target_users = record.target_users
                    m.domain_tags = record.domain_tags
                    m.tech_stack = record.tech_stack
                    m.business_model = record.business_model
                    m.stage = record.stage.value
                    m.traction = record.traction
                    m.source_kind = record.source_kind
                    m.event_name = record.event_name
                    m.year = record.year
                    m.placement = record.placement.value
                    m.team_size = record.team_size
                    m.links = record.links
                    m.all_source_urls = record.all_source_urls
                    m.confidence = record.confidence
                    m.evidence = ev_json
                    m.embedding = record.embedding
                    m.merged_into_id = record.merged_into_id
                    m.merge_history = record.merge_history
                    m.updated_at = now

                await session.commit()
        return record

    upsert_idea = save_idea

    async def get_idea(self, idea_id: str, tenant_id: Optional[str] = None) -> Optional[IdeaRecord]:
        t_id = tenant_id or self.tenant_id
        async with await self.get_session() as session:
            stmt = select(IdeaRecordModel).where(IdeaRecordModel.id == idea_id)
            if t_id:
                stmt = stmt.where(
                    or_(
                        IdeaRecordModel.tenant_id == t_id,
                        IdeaRecordModel.tenant_id.is_(None),
                    )
                )
            m = (await session.execute(stmt)).scalars().first()
            if not m:
                return None
            return self._to_record(m)

    async def search_ideas(
        self,
        query: Optional[str] = None,
        *,
        limit: int = 20,
        filters: Optional[Dict[str, Any]] = None,
        min_similarity: float = 0.3,
        tenant_id: Optional[str] = None,
        year: Optional[int] = None,
        event_name: Optional[str] = None,
        placement: Optional[str] = None,
        tech_stack: Optional[List[str]] = None,
        domain_tags: Optional[List[str]] = None,
        source_kind: Optional[str] = None,
    ) -> List[IdeaRecord]:
        """
        Hybrid semantic + keyword search with domain/tech/placement/year filters.
        Excludes records that have been merged into another record.
        """
        effective_filters = dict(filters or {})
        if year is not None:
            effective_filters["year"] = year
        if event_name is not None:
            effective_filters["event_name"] = event_name
        if placement is not None:
            effective_filters["placement"] = placement
        if tech_stack is not None:
            effective_filters["tech_stack"] = tech_stack
        if domain_tags is not None:
            effective_filters["domain_tags"] = domain_tags
        if source_kind is not None:
            effective_filters["source_kind"] = source_kind

        query_str = query or ""
        query_vec = self.embedder.embed_text(query_str) if query_str else None
        keywords = [k.lower() for k in query_str.split() if len(k) >= 2]

        t_id = tenant_id or self.tenant_id

        async with await self.get_session() as session:
            stmt = select(IdeaRecordModel).where(IdeaRecordModel.merged_into_id.is_(None))

            # Multi-tenancy isolation
            if t_id:
                stmt = stmt.where(
                    or_(
                        IdeaRecordModel.tenant_id == t_id,
                        IdeaRecordModel.tenant_id.is_(None),
                    )
                )

            # Apply filters
            if effective_filters:
                filters = effective_filters
                if "year" in filters and filters["year"]:
                    stmt = stmt.where(IdeaRecordModel.year == int(filters["year"]))
                if "event_name" in filters and filters["event_name"]:
                    stmt = stmt.where(IdeaRecordModel.event_name.ilike(f"%{filters['event_name']}%"))
                if "placement" in filters and filters["placement"]:
                    stmt = stmt.where(IdeaRecordModel.placement == str(filters["placement"]).lower())
                if "source_kind" in filters and filters["source_kind"]:
                    stmt = stmt.where(IdeaRecordModel.source_kind == str(filters["source_kind"]).lower())

            models = (await session.execute(stmt)).scalars().all()

            # Rank items by hybrid dense cosine + keyword overlap
            scored_records: List[tuple[float, IdeaRecord]] = []

            for m in models:
                # Tech stack / domain tag filters (checked in-memory for JSON arrays)
                if filters:
                    if "tech" in filters and filters["tech"]:
                        t_target = str(filters["tech"]).lower()
                        if not any(t_target in str(t).lower() for t in (m.tech_stack or [])):
                            continue
                    if "domain" in filters and filters["domain"]:
                        d_target = str(filters["domain"]).lower()
                        if not any(d_target in str(d).lower() for d in (m.domain_tags or [])):
                            continue

                record = self._to_record(m)

                # Dense cosine similarity
                cos_sim = 0.0
                if record.embedding and query_vec:
                    dot = sum(a * b for a, b in zip(record.embedding, query_vec))
                    norm1 = math.sqrt(sum(a * a for a in record.embedding))
                    norm2 = math.sqrt(sum(b * b for b in query_vec))
                    if norm1 > 0 and norm2 > 0:
                        cos_sim = dot / (norm1 * norm2)

                # Keyword score
                text_blob = f"{record.name} {record.one_liner or ''} {record.problem or ''} {record.solution or ''} {' '.join(record.tech_stack)}".lower()
                kw_matches = sum(1 for kw in keywords if kw in text_blob)
                kw_score = min(1.0, kw_matches / max(1, len(keywords)))

                score = (0.65 * cos_sim) + (0.35 * kw_score)
                if (not query_str and not bool(filters)) or score >= min_similarity or kw_score > 0.0 or bool(filters):
                    scored_records.append((score, record))

            scored_records.sort(key=lambda x: x[0], reverse=True)
            return [r for _, r in scored_records[:limit]]

    async def list_ideas(self, limit: int = 100) -> List[IdeaRecord]:
        async with await self.get_session() as session:
            stmt = (
                select(IdeaRecordModel)
                .where(IdeaRecordModel.merged_into_id.is_(None))
                .order_by(IdeaRecordModel.created_at.desc())
                .limit(limit)
            )
            if self.tenant_id:
                stmt = stmt.where(
                    or_(
                        IdeaRecordModel.tenant_id == self.tenant_id,
                        IdeaRecordModel.tenant_id.is_(None),
                    )
                )
            models = (await session.execute(stmt)).scalars().all()
            return [self._to_record(m) for m in models]
