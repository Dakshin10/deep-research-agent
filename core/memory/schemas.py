"""
Memory schemas for temporal knowledge graph, episodic memory, and vault notes.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid

from pydantic import BaseModel, Field


class EntityType(str, Enum):
    PERSON = "People"
    PROJECT = "Projects"
    ORG = "Orgs"
    TOOL = "Tools"
    IDEA = "Ideas"
    RESEARCH = "Research"
    SOURCES = "Sources"
    PREFERENCE = "Preferences"
    DECISION = "Decisions"
    DAILY = "Daily"


class Entity(BaseModel):
    id: str = Field(default_factory=lambda: f"ent_{uuid.uuid4().hex[:12]}")
    tenant_id: str = "default_tenant"
    name: str
    entity_type: EntityType = EntityType.PROJECT
    aliases: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    summary: str = ""
    salience: float = 0.8
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Relation(BaseModel):
    id: str = Field(default_factory=lambda: f"rel_{uuid.uuid4().hex[:12]}")
    tenant_id: str = "default_tenant"
    source_id: str
    target_id: str
    relation_type: str  # e.g. USES_TOOL, BUILT_ON, ORCHESTRATES, DECIDED, CONTRADICTS
    valid_from: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    valid_to: Optional[datetime] = None
    is_active: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Fact(BaseModel):
    id: str = Field(default_factory=lambda: f"fact_{uuid.uuid4().hex[:12]}")
    tenant_id: str = "default_tenant"
    entity_id: str
    statement: str
    valid_from: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    valid_to: Optional[datetime] = None
    is_active: bool = True
    episode_id: Optional[str] = None
    provenance_url: Optional[str] = None
    provenance_location: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Episode(BaseModel):
    id: str = Field(default_factory=lambda: f"ep_{uuid.uuid4().hex[:12]}")
    tenant_id: str = "default_tenant"
    conversation_id: str
    turn_id: str
    summary: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MemoryRecallItem(BaseModel):
    id: str
    entity_name: str
    entity_type: str
    fact: str
    valid_from: str
    valid_to: Optional[str] = None
    provenance: Optional[str] = None
    score: float = 1.0


class MemoryGraphSubgraph(BaseModel):
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]
