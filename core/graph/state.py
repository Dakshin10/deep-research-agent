from __future__ import annotations

from typing import Any, Dict, List, Optional
from typing_extensions import Annotated, TypedDict


def merge_notes(existing: Optional[List[Dict[str, Any]]], new_items: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    existing = existing or []
    new_items = new_items or []
    seen = set()
    merged = []
    for item in existing + new_items:
        item_id = item.get("id")
        if item_id:
            if item_id not in seen:
                seen.add(item_id)
                merged.append(item)
        else:
            merged.append(item)
    return merged


def merge_artifacts(existing: Optional[List[Dict[str, Any]]], new_items: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    existing = existing or []
    new_items = new_items or []
    seen = set()
    merged = []
    for item in existing + new_items:
        item_id = item.get("id") or item.get("file_path") or item.get("title")
        if item_id:
            if item_id not in seen:
                seen.add(item_id)
                merged.append(item)
        else:
            merged.append(item)
    return merged


class ResearchGraphState(TypedDict, total=False):
    job_id: str
    tenant_id: str
    query: str
    mode: str  # "shallow", "deep", "clarify", "chit_chat"
    confidence: float
    stage: str
    brief: Optional[Dict[str, Any]]
    selected_sources: List[str]
    plan: Optional[Dict[str, Any]]
    notes: Annotated[List[Dict[str, Any]], merge_notes]
    artifacts: Annotated[List[Dict[str, Any]], merge_artifacts]
    input_files: Dict[str, bytes]
    report: Optional[str]
    citations: List[str]
    clarification_needed: bool
    clarification_questions: List[str]
    clarification_response: Optional[str]
    followup_query: Optional[str]
    followup_response: Optional[str]
    budget: Dict[str, Any]
    budget_warning: bool
    budget_exhausted: bool
    extra_research_rounds: int
    extra_research_done: bool
    gate_passed: bool
    gate_issues: List[Dict[str, Any]]
    compliance_passed: bool
    compliance_issues: List[str]
    delivered_artifacts: List[Dict[str, Any]]
    done: bool
    error: Optional[str]
