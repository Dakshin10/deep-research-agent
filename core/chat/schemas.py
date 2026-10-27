from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union
import uuid
from pydantic import BaseModel, Field


class ChatRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class PartType(str, Enum):
    TEXT = "text"
    TOOL_CALL = "tool_call"
    CODE_EXECUTION = "code_execution"
    CITATION = "citation"
    ARTIFACT = "artifact"
    REASONING = "reasoning"


class BaseChatEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:12]}")
    turn_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    type: str


class TextDeltaEvent(BaseChatEvent):
    type: Literal["text_delta"] = "text_delta"
    content: str


class ReasoningSummaryEvent(BaseChatEvent):
    type: Literal["reasoning_summary"] = "reasoning_summary"
    summary: str


class ToolCallStartedEvent(BaseChatEvent):
    type: Literal["tool_call_started"] = "tool_call_started"
    call_id: str
    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)


class ToolCallFinishedEvent(BaseChatEvent):
    type: Literal["tool_call_finished"] = "tool_call_finished"
    call_id: str
    tool_name: str
    success: bool = True
    duration_seconds: float = 0.0
    summary: Optional[str] = None
    result: Optional[Any] = None


class CodeExecutionEvent(BaseChatEvent):
    type: Literal["code_execution"] = "code_execution"
    execution_id: str
    code: str
    result: str
    duration_ms: int = 0
    sandboxed: bool = True


class ResearchProgressEvent(BaseChatEvent):
    type: Literal["research_progress"] = "research_progress"
    job_id: str
    stage: str
    active_shards: int = 0
    completed_shards: int = 0
    sources_found: Dict[str, int] = Field(default_factory=dict)
    budget_used_pct: float = 0.0


class CitationEvent(BaseChatEvent):
    type: Literal["citation"] = "citation"
    note_id: str
    url: str
    title: str
    excerpt: str
    location: str
    text_fragment_url: Optional[str] = None
    verified: bool = True


class ArtifactEvent(BaseChatEvent):
    type: Literal["artifact"] = "artifact"
    artifact_id: str
    title: str
    artifact_type: str  # report, chart, deck, table, idea-cards
    mime_type: str = "text/markdown"
    download_url: Optional[str] = None
    preview_content: Optional[str] = None


class ClarificationRequestEvent(BaseChatEvent):
    type: Literal["clarification_request"] = "clarification_request"
    question: str
    suggested_answers: List[str] = Field(default_factory=list)


class ApprovalRequestEvent(BaseChatEvent):
    type: Literal["approval_request"] = "approval_request"
    action_id: str
    description: str
    payload: Dict[str, Any] = Field(default_factory=dict)


class MemoryUsedEvent(BaseChatEvent):
    type: Literal["memory_used"] = "memory_used"
    memories: List[Dict[str, Any]] = Field(default_factory=list)


class MemoryWriteProposedEvent(BaseChatEvent):
    type: Literal["memory_write_proposed"] = "memory_write_proposed"
    entity: str
    fact: str
    confidence: float = 1.0


class UIActionEvent(BaseChatEvent):
    type: Literal["ui_action"] = "ui_action"
    action: str  # e.g., ui.open_memory_graph, ui.open_sources, ui.open_artifact, ui.open_settings, ui.set_private_mode, ui.export_vault
    payload: Dict[str, Any] = Field(default_factory=dict)


class JobUpdateEvent(BaseChatEvent):
    type: Literal["job_update"] = "job_update"
    job_id: str
    status: str
    progress_pct: float = 0.0
    summary: Optional[str] = None
    artifact_id: Optional[str] = None


class ErrorEvent(BaseChatEvent):
    type: Literal["error"] = "error"
    message: str
    code: str = "INTERNAL_ERROR"


class DoneEvent(BaseChatEvent):
    type: Literal["done"] = "done"
    finish_reason: str = "stop"
    total_tokens: int = 0
    duration_seconds: float = 0.0


ChatEvent = Union[
    TextDeltaEvent,
    ReasoningSummaryEvent,
    ToolCallStartedEvent,
    ToolCallFinishedEvent,
    CodeExecutionEvent,
    ResearchProgressEvent,
    CitationEvent,
    ArtifactEvent,
    ClarificationRequestEvent,
    ApprovalRequestEvent,
    MemoryUsedEvent,
    MemoryWriteProposedEvent,
    UIActionEvent,
    JobUpdateEvent,
    ErrorEvent,
    DoneEvent,
]


# -------------------------------------------------------------
# Message & Conversation Persistence Models
# -------------------------------------------------------------
class MessagePart(BaseModel):
    id: str = Field(default_factory=lambda: f"part_{uuid.uuid4().hex[:12]}")
    part_type: PartType
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ChatMessage(BaseModel):
    id: str = Field(default_factory=lambda: f"msg_{uuid.uuid4().hex[:12]}")
    conversation_id: str
    parent_id: Optional[str] = None
    role: ChatRole
    content: str
    parts: List[MessagePart] = Field(default_factory=list)
    citations: List[CitationEvent] = Field(default_factory=list)
    artifacts: List[ArtifactEvent] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Conversation(BaseModel):
    id: str = Field(default_factory=lambda: f"conv_{uuid.uuid4().hex[:12]}")
    tenant_id: str = "default_tenant"
    title: str = "New Research Chat"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = Field(default_factory=dict)
    active_branch_leaf_id: Optional[str] = None


class ChatTurnRequest(BaseModel):
    conversation_id: Optional[str] = None
    message: str
    parent_message_id: Optional[str] = None
    model_role: Optional[str] = None  # fast, strong, code
    incognito: bool = False           # if True, disable memory read/write
    approval_token: Optional[str] = None
    last_event_id: Optional[str] = None
