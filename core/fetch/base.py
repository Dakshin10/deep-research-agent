from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from typing import List, Optional
from pydantic import BaseModel, Field

from core.guardrails.injection import PromptInjectionDefense


class DocumentSection(BaseModel):
    """Represents a hierarchical section within a fetched document."""
    heading_path: List[str] = Field(default_factory=list)
    char_start: int = 0
    char_end: int = 0
    text: str = ""


class DocumentPage(BaseModel):
    """Represents a discrete page within a paginated document (e.g. PDF)."""
    page_no: int
    char_start: int = 0
    char_end: int = 0
    text: str = ""


class DocumentTimestamp(BaseModel):
    """Represents a timed segment (e.g. for audio/video transcripts)."""
    start_seconds: float
    end_seconds: float
    text: str = ""


class FetchedDocument(BaseModel):
    """Standardized representation of content fetched from any web or document source."""
    url: str
    final_url: str
    status: int = 200
    content_type: str = "text/html"
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    content_hash: str = ""
    title: str = ""
    raw_text: str = ""
    sections: List[DocumentSection] = Field(default_factory=list)
    pages: List[DocumentPage] = Field(default_factory=list)
    timestamps: List[DocumentTimestamp] = Field(default_factory=list)
    is_blocked: bool = False
    block_reason: Optional[str] = None

    def model_post_init(self, __context) -> None:
        if not self.content_hash and self.raw_text:
            self.content_hash = hashlib.sha256(self.raw_text.encode("utf-8", errors="replace")).hexdigest()

    def to_clean_markdown(self, max_chars: int = 15000) -> str:
        """Convert extracted sections and text to human-readable markdown."""
        if not self.sections:
            content = self.raw_text
        else:
            chunks = []
            for s in self.sections:
                heading = " > ".join(s.heading_path) if s.heading_path else ""
                if heading:
                    chunks.append(f"\n### {heading}\n{s.text}")
                else:
                    chunks.append(s.text)
            content = "\n\n".join(chunks)

        if len(content) > max_chars:
            content = content[:max_chars] + "\n...[truncated]"
        return content.strip()

    def fenced_markdown(self, max_chars: int = 15000) -> str:
        """Return clean markdown fenced with prompt injection defenses."""
        clean = self.to_clean_markdown(max_chars=max_chars)
        return PromptInjectionDefense.fence(
            content=clean,
            source_type=self.content_type,
            source_url_or_id=self.final_url or self.url,
        )
