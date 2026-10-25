from __future__ import annotations

import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, Float, DateTime, ForeignKey, Index, JSON, Boolean, Integer
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class JobModel(Base):
    __tablename__ = "jobs"

    id = Column(String(64), primary_key=True, default=lambda: f"job_{uuid.uuid4().hex[:12]}")
    tenant_id = Column(String(64), nullable=False, index=True)
    query = Column(Text, nullable=False)
    status = Column(String(32), nullable=False, default="pending", index=True)
    mode = Column(String(32), nullable=False, default="deep")
    confidence = Column(Float, default=1.0)
    brief = Column(JSON, nullable=True)
    plan = Column(JSON, nullable=True)
    report = Column(Text, nullable=True)
    budget = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    notes = relationship("ResearchNoteModel", back_populates="job", cascade="all, delete-orphan")
    artifacts = relationship("ArtifactModel", back_populates="job", cascade="all, delete-orphan")
    events = relationship("RunEventModel", back_populates="job", cascade="all, delete-orphan")


class ResearchNoteModel(Base):
    __tablename__ = "research_notes"

    id = Column(String(64), primary_key=True, default=lambda: f"note_{uuid.uuid4().hex[:8]}")
    job_id = Column(String(64), ForeignKey("jobs.id"), nullable=False, index=True)
    tenant_id = Column(String(64), nullable=False, index=True)
    claim = Column(Text, nullable=False)
    source_type = Column(String(32), nullable=False, default="web")
    source_url = Column(Text, nullable=True)
    document_id = Column(String(64), nullable=True)
    excerpt = Column(Text, nullable=False)
    confidence = Column(Float, default=0.9)
    task_id = Column(String(64), nullable=False, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Phase 3 Location Fields
    url = Column(Text, nullable=True)
    canonical_url = Column(Text, nullable=True)
    title = Column(Text, nullable=True)
    source_family = Column(String(64), nullable=True)
    provider = Column(String(64), nullable=True)
    retrieved_at = Column(DateTime, nullable=True)
    content_hash = Column(String(64), nullable=True)
    char_start = Column(Integer, nullable=True)
    char_end = Column(Integer, nullable=True)
    page_no = Column(Integer, nullable=True)
    heading_path = Column(JSON, default=list)
    text_fragment_url = Column(Text, nullable=True)
    video_timestamp_url = Column(Text, nullable=True)
    archive_url = Column(Text, nullable=True)
    is_verified = Column(Boolean, default=False)

    job = relationship("JobModel", back_populates="notes")


class ArtifactModel(Base):
    __tablename__ = "artifacts"

    id = Column(String(64), primary_key=True, default=lambda: f"art_{uuid.uuid4().hex[:8]}")
    job_id = Column(String(64), ForeignKey("jobs.id"), nullable=False, index=True)
    tenant_id = Column(String(64), nullable=False, index=True)
    artifact_type = Column(String(32), nullable=False)
    title = Column(String(255), nullable=False)
    file_path = Column(Text, nullable=True)
    content = Column(Text, nullable=True)
    metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    job = relationship("JobModel", back_populates="artifacts")


class RunEventModel(Base):
    __tablename__ = "run_events"

    id = Column(String(64), primary_key=True, default=lambda: f"evt_{uuid.uuid4().hex[:8]}")
    job_id = Column(String(64), ForeignKey("jobs.id"), nullable=False, index=True)
    tenant_id = Column(String(64), nullable=False, index=True)
    event_type = Column(String(64), nullable=False, index=True)
    payload_json = Column(JSON, default=dict)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    job = relationship("JobModel", back_populates="events")


class DocumentModel(Base):
    __tablename__ = "documents"

    id = Column(String(64), primary_key=True, default=lambda: f"doc_{uuid.uuid4().hex[:8]}")
    tenant_id = Column(String(64), nullable=True, index=True)  # nullable for global benchmarks
    filename = Column(String(255), nullable=False)
    file_type = Column(String(32), nullable=False)
    file_path = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    chunks = relationship("DocumentChunkModel", back_populates="document", cascade="all, delete-orphan")


class DocumentChunkModel(Base):
    __tablename__ = "document_chunks"

    id = Column(String(64), primary_key=True, default=lambda: f"chk_{uuid.uuid4().hex[:8]}")
    document_id = Column(String(64), ForeignKey("documents.id"), nullable=False, index=True)
    tenant_id = Column(String(64), nullable=True, index=True)  # nullable for global benchmarks
    chunk_index = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)
    embedding = Column(JSON, nullable=True)  # vector represented as JSON list or Vector type
    metadata_json = Column(JSON, default=dict)

    document = relationship("DocumentModel", back_populates="chunks")
