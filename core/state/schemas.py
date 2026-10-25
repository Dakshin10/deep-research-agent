from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    NEEDS_CLARIFICATION = "needs_clarification"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobMode(str, Enum):
    SHALLOW = "shallow"
    DEEP = "deep"
    CLARIFY = "clarify"
    CHIT_CHAT = "chit_chat"


class Brief(BaseModel):
    audience: Optional[str] = None
    geography: Optional[str] = None
    goal_kpi: Optional[str] = None
    budget: Optional[str] = None
    brand_voice: Optional[str] = None
    named_competitors: List[str] = Field(default_factory=list)
    missing_fields: List[str] = Field(default_factory=list)
    clarification_round: int = 0
    extra_context: Optional[str] = None


class ExpectedOutput(str, Enum):
    NOTES = "notes"
    NOTES_AND_TABLE = "notes+table"
    NOTES_AND_CHART = "notes+chart"


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class PlanTask(BaseModel):
    task_id: str
    objective: str
    entity: str
    source_hints: List[str] = Field(default_factory=list)
    expected_output: ExpectedOutput = ExpectedOutput.NOTES
    depends_on: List[str] = Field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    assigned_worker: Optional[str] = None


class Plan(BaseModel):
    tasks: List[PlanTask] = Field(default_factory=list)
    round: int = 1


class ResearchNote(BaseModel):
    id: str = Field(default_factory=lambda: f"note_{uuid.uuid4().hex[:8]}")
    job_id: str
    tenant_id: str
    claim: str
    source_type: Literal["web", "kb", "mcp", "reddit", "computed", "fallback"] = "web"
    source_url: Optional[str] = None
    document_id: Optional[str] = None
    excerpt: str
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)
    task_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Artifact(BaseModel):
    id: str = Field(default_factory=lambda: f"art_{uuid.uuid4().hex[:8]}")
    job_id: str
    tenant_id: str
    artifact_type: str  # "report", "chart", "table", "pptx", "script", "csv"
    title: str
    file_path: Optional[str] = None
    content: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class EventType(str, Enum):
    STAGE_STARTED = "stage_started"
    TOOL_CALL = "tool_call"
    NOTE_ADDED = "note_added"
    CLARIFICATION_NEEDED = "clarification_needed"
    ARTIFACT_READY = "artifact_ready"
    BUDGET_WARNING = "budget_warning"
    GATE_FLAGGED = "gate_flagged"
    PROVIDER_FALLBACK = "provider_fallback"
    DONE = "done"
    ERROR = "error"


class RunEvent(BaseModel):
    id: str = Field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:8]}")
    job_id: str
    tenant_id: str
    event_type: EventType
    payload: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class BudgetState(BaseModel):
    max_steps: int = 50
    used_steps: int = 0
    max_tokens: int = 100000
    used_tokens: int = 0
    max_seconds: float = 600.0
    start_time: float = Field(default_factory=time.time)
    warning_emitted: bool = False
    exhausted: bool = False

    def check_and_update(self, steps_delta: int = 0, tokens_delta: int = 0) -> Optional[EventType]:
        self.used_steps += steps_delta
        self.used_tokens += tokens_delta
        elapsed = time.time() - self.start_time

        step_ratio = self.used_steps / self.max_steps if self.max_steps > 0 else 0
        token_ratio = self.used_tokens / self.max_tokens if self.max_tokens > 0 else 0
        time_ratio = elapsed / self.max_seconds if self.max_seconds > 0 else 0
        max_ratio = max(step_ratio, token_ratio, time_ratio)

        if max_ratio >= 1.0:
            self.exhausted = True
            return EventType.BUDGET_WARNING
        elif max_ratio >= 0.8 and not self.warning_emitted:
            self.warning_emitted = True
            return EventType.BUDGET_WARNING
        return None


class Job(BaseModel):
    id: str = Field(default_factory=lambda: f"job_{uuid.uuid4().hex[:12]}")
    tenant_id: str
    query: str
    status: JobStatus = JobStatus.PENDING
    mode: JobMode = JobMode.DEEP
    confidence: float = 1.0
    brief: Optional[Brief] = None
    plan: Optional[Plan] = None
    report: Optional[str] = None
    budget: BudgetState = Field(default_factory=BudgetState)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
