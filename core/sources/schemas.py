from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class SourceKind(str, Enum):
    HACKATHON = "hackathon"
    STARTUP = "startup"
    LAUNCH = "launch"
    BLOG = "blog"
    VIDEO = "video"
    PAPER = "paper"


class ProjectPlacement(str, Enum):
    WINNER = "winner"
    RUNNER_UP = "runner-up"
    TRACK_PRIZE = "track prize"
    FINALIST = "finalist"
    NONE = "none"


class RawProject(BaseModel):
    """
    Raw project payload produced by source adapters.
    Serves as input to the structured IdeaRecord extraction agent.
    """
    source_id: str
    source_domain: str
    source_kind: SourceKind = SourceKind.HACKATHON
    source_url: str
    all_source_urls: List[str] = Field(default_factory=list)

    name: str
    tagline: Optional[str] = None
    description_raw: str

    authors: List[str] = Field(default_factory=list)
    team_size: Optional[int] = None
    event_name: Optional[str] = None
    year: Optional[int] = None
    placement: ProjectPlacement = ProjectPlacement.NONE
    prize_name: Optional[str] = None

    links: Dict[str, str] = Field(default_factory=dict)  # demo, repo, video, website, deck
    tags: List[str] = Field(default_factory=list)
    tech_stack: List[str] = Field(default_factory=list)

    raw_html: Optional[str] = None
    raw_json: Optional[Dict[str, Any]] = None
    extracted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
