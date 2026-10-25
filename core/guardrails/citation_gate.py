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
    """Verifies that every numeric, comparative, or superlative claim links to a valid research note ID with verified location."""

    NUMERIC_PATTERN = re.compile(r"(\b\d+(?:\.\d+)?%|\$\d+(?:\.\d+)?|\b\d+(?:x|\s*fold)\b|\b\d{2,}\b)")
    SUPERLATIVE_COMPARATIVE_PATTERN = re.compile(
        r"(?i)\b(#1|highest|lowest|fastest|slowest|largest|smallest|outperformed|superior|dominant|industry-leading|top-tier|market leader)\b"
    )
    NOTE_CITATION_PATTERN = re.compile(r"\[(note_[a-zA-Z0-9_-]+)\]")

    def __init__(
        self,
        valid_note_ids: Optional[Set[str]] = None,
        note_locations: Optional[Dict[str, bool]] = None,
        strict: bool = False,
    ):
        self.valid_note_ids = valid_note_ids or set()
        self.note_locations = note_locations or {}
        self.strict = strict

    def evaluate(self, text: str) -> CitationGateResult:
        if not text:
            return CitationGateResult(passed=True, cleaned_text="")

        # Separate main body from sources/bibliography section so source listings aren't evaluated as factual claims
        sources_match = re.search(r"(?i)\n(?:---|###? (?:Verified )?Sources(?:\s*&|\s*Index)?)", text)
        if sources_match:
            body_text = text[: sources_match.start()]
            sources_suffix = text[sources_match.start() :]
        else:
            body_text = text
            sources_suffix = ""

        sentences = re.split(r"(?<=[.!?])\s+", body_text)
        flagged: List[CitationIssue] = []
        valid_found: List[str] = []
        cleaned_sentences: List[str] = []

        for sent in sentences:
            stripped = sent.strip()
            if not stripped or stripped.startswith("- **[note_") or stripped.startswith("### "):
                cleaned_sentences.append(stripped)
                continue

            # Check for note citations in this sentence
            citations = self.NOTE_CITATION_PATTERN.findall(stripped)
            # Verify if cited note IDs exist in valid_note_ids and have verified locations
            has_valid_citation = False
            has_verified_location = False
            for cite in citations:
                if not self.valid_note_ids or cite in self.valid_note_ids:
                    has_valid_citation = True
                    valid_found.append(cite)
                    # If note_locations mapping is provided, check if location is verified
                    if not self.note_locations or self.note_locations.get(cite, False):
                        has_verified_location = True

            # Check if sentence makes numeric or superlative/comparative claim
            is_numeric = bool(self.NUMERIC_PATTERN.search(stripped))
            is_superlative = bool(self.SUPERLATIVE_COMPARATIVE_PATTERN.search(stripped))

            if (is_numeric or is_superlative) and (not has_valid_citation or not has_verified_location):
                issue_type = "numeric" if is_numeric else "superlative/comparative"
                reason = (
                    "Claim contains quantitative assertion but cited note lacks a verified document location."
                    if has_valid_citation and not has_verified_location
                    else "Claim contains quantitative or comparative assertion without a verified note ID citation."
                )
                flagged.append(
                    CitationIssue(
                        sentence=stripped,
                        issue_type=issue_type,
                        reason=reason,
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
        cleaned_text = " ".join(cleaned_sentences) + sources_suffix

        return CitationGateResult(
            passed=passed,
            flagged_issues=flagged,
            valid_citations_found=list(set(valid_found)),
            cleaned_text=cleaned_text,
        )
