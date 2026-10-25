from __future__ import annotations

import re
from typing import List, Set, Tuple
from pydantic import BaseModel, Field


class CitationIssue(BaseModel):
    sentence: str
    issue_type: str  # "numeric", "superlative", "comparative"
    reason: str


class CitationGateResult(BaseModel):
    passed: bool
    flagged_issues: List[CitationIssue] = Field(default_factory=list)
    valid_citations_found: List[str] = Field(default_factory=list)
    cleaned_text: str


class CitationGate:
    """Verifies that every numeric, comparative, or superlative claim links to a valid research note ID."""

    NUMERIC_PATTERN = re.compile(r"(\b\d+(?:\.\d+)?%|\$\d+(?:\.\d+)?|\b\d+(?:x|\s*fold)\b|\b\d{2,}\b)")
    SUPERLATIVE_COMPARATIVE_PATTERN = re.compile(
        r"(?i)\b(#1|highest|lowest|fastest|slowest|largest|smallest|outperformed|superior|dominant|industry-leading|top-tier|market leader)\b"
    )
    NOTE_CITATION_PATTERN = re.compile(r"\[(note_[a-zA-Z0-9_-]+)\]")

    def __init__(self, valid_note_ids: Set[str] = None, strict: bool = False):
        self.valid_note_ids = valid_note_ids or set()
        self.strict = strict

    def evaluate(self, text: str) -> CitationGateResult:
        if not text:
            return CitationGateResult(passed=True, cleaned_text="")

        sentences = re.split(r"(?<=[.!?])\s+", text)
        flagged: List[CitationIssue] = []
        valid_found: List[str] = []
        cleaned_sentences: List[str] = []

        for sent in sentences:
            stripped = sent.strip()
            if not stripped:
                continue

            # Check for note citations in this sentence
            citations = self.NOTE_CITATION_PATTERN.findall(stripped)
            # Verify if cited note IDs exist in valid_note_ids
            has_valid_citation = False
            for cite in citations:
                if not self.valid_note_ids or cite in self.valid_note_ids:
                    has_valid_citation = True
                    valid_found.append(cite)

            # Check if sentence makes numeric or superlative/comparative claim
            is_numeric = bool(self.NUMERIC_PATTERN.search(stripped))
            is_superlative = bool(self.SUPERLATIVE_COMPARATIVE_PATTERN.search(stripped))

            if (is_numeric or is_superlative) and not has_valid_citation:
                issue_type = "numeric" if is_numeric else "superlative/comparative"
                flagged.append(
                    CitationIssue(
                        sentence=stripped,
                        issue_type=issue_type,
                        reason="Claim contains quantitative or comparative assertion without a verified note ID citation.",
                    )
                )
                if self.strict:
                    # Strip or flag sentence in strict mode
                    cleaned_sentences.append(f"{stripped} [citation needed: flagged]")
                else:
                    cleaned_sentences.append(stripped)
            else:
                cleaned_sentences.append(stripped)

        passed = len(flagged) == 0
        cleaned_text = " ".join(cleaned_sentences)

        return CitationGateResult(
            passed=passed,
            flagged_issues=flagged,
            valid_citations_found=list(set(valid_found)),
            cleaned_text=cleaned_text,
        )
