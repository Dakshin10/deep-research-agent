from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ProjectStage(str, Enum):
    IDEA = "idea"
    PROTOTYPE = "prototype"
    LAUNCHED = "launched"
    FUNDED = "funded"


class ProjectPlacement(str, Enum):
    WINNER = "winner"
    RUNNER_UP = "runner_up"
    TRACK_PRIZE = "track_prize"
    FINALIST = "finalist"
    NONE = "none"


class EvidenceEntry(BaseModel):
    field: str
    url: str
    excerpt: str
    char_start: Optional[int] = None
    char_end: Optional[int] = None
    page_no: Optional[int] = None
    video_timestamp_url: Optional[str] = None
    text_fragment_url: Optional[str] = None
    verified: bool = False


class IdeaRecord(BaseModel):
    id: str
    tenant_id: Optional[str] = None  # None = public shared, or tenant UUID
    name: str
    one_liner: Optional[str] = None
    problem: Optional[str] = None
    solution: Optional[str] = None
    target_users: Optional[str] = None
    domain_tags: List[str] = Field(default_factory=list)
    tech_stack: List[str] = Field(default_factory=list)
    business_model: Optional[str] = None
    stage: ProjectStage = ProjectStage.PROTOTYPE
    traction: Optional[str] = None
    source_kind: str = "hackathon"  # hackathon | startup | launch | blog | video | paper
    event_name: Optional[str] = None
    year: Optional[int] = None
    placement: ProjectPlacement = ProjectPlacement.NONE
    team_size: Optional[int] = None  # Number only!
    links: Dict[str, str] = Field(default_factory=dict)  # demo, repo, video, website, deck
    first_seen_url: str
    all_source_urls: List[str] = Field(default_factory=list)
    confidence: float = 1.0
    evidence: Dict[str, EvidenceEntry] = Field(default_factory=dict)
    embedding: Optional[List[float]] = None
    merged_into_id: Optional[str] = None
    merge_history: List[Dict[str, Any]] = Field(default_factory=list)
    extracted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def canonical_text(self) -> str:
        """Constructs canonical text for dense vector embedding."""
        parts = [
            f"Project: {self.name}",
            f"Problem: {self.problem or ''}",
            f"Solution: {self.solution or ''}",
            f"Target Users: {self.target_users or ''}",
            f"Tech Stack: {', '.join(self.tech_stack)}",
            f"Domain: {', '.join(self.domain_tags)}",
        ]
        return "\n".join(p for p in parts if p.strip())
