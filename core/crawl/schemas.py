from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class CrawlMode(str, Enum):
    DISCOVER = "discover"
    FETCH = "fetch"
    REFRESH = "refresh"
    ALL = "all"


class FrontierState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class FrontierItem(BaseModel):
    id: str
    url: str
    canonical_url: str
    source: str
    state: FrontierState = FrontierState.PENDING
    priority: int = 10
    attempts: int = 0
    max_attempts: int = 3
    next_attempt_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_etag: Optional[str] = None
    last_modified: Optional[str] = None
    content_hash: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CrawlRunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CrawlRunConfig(BaseModel):
    source: str
    mode: CrawlMode = CrawlMode.ALL
    since_date: Optional[str] = None
    limit_pages: int = 1000
    max_bytes: int = 500_000_000  # 500 MB
    max_duration_seconds: int = 3600
    global_concurrency: int = 8
    domain_concurrency: int = 2
    honesty_user_agent: Optional[str] = None


class CrawlRunRecord(BaseModel):
    id: str
    source: str
    mode: CrawlMode = CrawlMode.ALL
    status: CrawlRunStatus = CrawlRunStatus.RUNNING
    since_date: Optional[str] = None
    limit_pages: int = 1000
    pages_discovered: int = 0
    pages_crawled: int = 0
    pages_skipped: int = 0
    bytes_downloaded: int = 0
    errors_count: int = 0
    errors_by_domain: Dict[str, int] = Field(default_factory=dict)
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: Optional[datetime] = None
    config_override: Dict[str, Any] = Field(default_factory=dict)


class CrawlEvent(BaseModel):
    run_id: str
    event_type: str  # crawl_started, page_fetched, page_blocked, page_skipped, crawl_completed, adapter_broken
    payload: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
