from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
import re
from typing import Any, Callable, Dict, List, Optional
import uuid

from pydantic import BaseModel

from core.fetch.base import FetchedDocument
from core.fetch.location import generate_text_fragment_url, verify_excerpt_in_document
from core.ideas.privacy import PrivacyScrubber
from core.ideas.schemas import (
    EvidenceEntry,
    IdeaRecord,
    ProjectPlacement,
    ProjectStage,
)
from core.knowledge.embedder import EmbeddingModel
from core.models.router import ModelRouter
from core.sources.schemas import RawProject, ProjectPlacement as SourcePlacement


class RawIdeaExtraction(BaseModel):
    name: str
    one_liner: Optional[str] = None
    problem: Optional[str] = None
    solution: Optional[str] = None
    target_users: Optional[str] = None
    domain_tags: List[str] = []
    tech_stack: List[str] = []
    business_model: Optional[str] = None
    stage: str = "prototype"
    traction: Optional[str] = None
    event_name: Optional[str] = None
    year: Optional[int] = None
    placement: str = "none"
    team_size: Optional[int] = None
    links: Dict[str, str] = {}
    evidence: Dict[str, str] = {}  # field_name -> verbatim excerpt from page


class IdeaExtractor:
    """
    Extracts structured IdeaRecord from fetched documents with verbatim evidence verification.
    HARD RULE: If an evidence excerpt is not found verbatim (or fuzzy >=0.90) in doc.raw_text,
    that field is DROPPED (set to null) and a 'field_rejected' event is emitted.
    Fabricated prizes, placements, or traction claims are never persisted.
    """

    def __init__(
        self,
        router: Optional[ModelRouter] = None,
        embedder: Optional[EmbeddingModel] = None,
        privacy: Optional[PrivacyScrubber] = None,
    ):
        self.router = router or ModelRouter()
        self.embedder = embedder or EmbeddingModel()
        self.privacy = privacy or PrivacyScrubber()

    async def extract(
        self,
        doc: FetchedDocument,
        raw_project: Optional[RawProject] = None,
        tenant_id: Optional[str] = None,
        on_event: Optional[Callable[[str, Dict[str, Any]], Any]] = None,
    ) -> IdeaRecord:
        """Extracts and verifies an IdeaRecord from a FetchedDocument."""
        url = doc.final_url or doc.url
        raw_text = doc.raw_text or ""

        # 1. First-pass extraction
        candidate = await self._extract_candidate(doc, raw_project)

        # 2. Privacy Scrubber pass (redact PII, phones, emails, private profiles)
        candidate.name = self.privacy.scrub_text(candidate.name) or "Untitled Idea"
        candidate.one_liner = self.privacy.scrub_text(candidate.one_liner)
        candidate.problem = self.privacy.scrub_text(candidate.problem)
        candidate.solution = self.privacy.scrub_text(candidate.solution)
        candidate.target_users = self.privacy.scrub_text(candidate.target_users)
        candidate.business_model = self.privacy.scrub_text(candidate.business_model)
        candidate.traction = self.privacy.scrub_text(candidate.traction)
        candidate.links = self.privacy.scrub_links(candidate.links)

        # 3. VERBATIM EVIDENCE VERIFICATION (HARD RULE)
        verified_evidence: Dict[str, EvidenceEntry] = {}

        fields_to_verify = [
            ("name", candidate.name),
            ("one_liner", candidate.one_liner),
            ("problem", candidate.problem),
            ("solution", candidate.solution),
            ("target_users", candidate.target_users),
            ("business_model", candidate.business_model),
            ("traction", candidate.traction),
            ("placement", candidate.placement),
            ("team_size", str(candidate.team_size) if candidate.team_size is not None else None),
        ]

        for field_name, val in fields_to_verify:
            if not val:
                continue

            excerpt = candidate.evidence.get(field_name, "")

            # If no excerpt provided or excerpt cannot be verified in raw text:
            # Drop the field!
            is_valid = False
            if excerpt and raw_text:
                match, c_start, c_end, page_no, headings, frag_url = verify_excerpt_in_document(
                    excerpt=excerpt, doc=doc
                )
                if match:
                    is_valid = True
                    verified_evidence[field_name] = EvidenceEntry(
                        field=field_name,
                        url=url,
                        excerpt=excerpt,
                        char_start=c_start,
                        char_end=c_end,
                        page_no=page_no,
                        text_fragment_url=frag_url,
                        verified=True,
                    )

            if not is_valid:
                # FIELD REJECTED!
                # Drop claim to null and emit event
                if field_name == "name":
                    pass  # Keep title if possible from URL/header
                elif field_name == "placement":
                    candidate.placement = "none"
                elif field_name == "team_size":
                    candidate.team_size = None
                else:
                    setattr(candidate, field_name, None)

                if on_event:
                    res = on_event(
                        "field_rejected",
                        {
                            "field": field_name,
                            "url": url,
                            "claimed_value": val,
                            "excerpt": excerpt,
                            "reason": "verbatim_excerpt_verification_failed",
                        },
                    )
                    if asyncio.iscoroutine(res):
                        await res

        # 4. Canonical placement and stage
        try:
            placement = ProjectPlacement(candidate.placement.lower().replace(" ", "_"))
        except Exception:
            placement = ProjectPlacement.NONE

        try:
            stage = ProjectStage(candidate.stage.lower().replace(" ", "_"))
        except Exception:
            stage = ProjectStage.PROTOTYPE

        record_id = f"idea_{hashlib.sha256(f'{url}:{candidate.name}'.encode()).hexdigest()[:16]}"
        now = datetime.now(timezone.utc)

        record = IdeaRecord(
            id=record_id,
            tenant_id=tenant_id,
            name=candidate.name,
            one_liner=candidate.one_liner,
            problem=candidate.problem,
            solution=candidate.solution,
            target_users=candidate.target_users,
            domain_tags=candidate.domain_tags or [],
            tech_stack=candidate.tech_stack or [],
            business_model=candidate.business_model,
            stage=stage,
            traction=candidate.traction,
            source_kind=raw_project.source_kind.value if raw_project else "hackathon",
            event_name=candidate.event_name or (raw_project.event_name if raw_project else None),
            year=candidate.year or (raw_project.year if raw_project else None),
            placement=placement,
            team_size=candidate.team_size,
            links=candidate.links,
            first_seen_url=url,
            all_source_urls=[url],
            confidence=1.0 if len(verified_evidence) >= 3 else 0.75,
            evidence=verified_evidence,
            extracted_at=now,
            created_at=now,
            updated_at=now,
        )

        # 5. Compute embedding over canonical text
        record.embedding = self.embedder.embed_text(record.canonical_text())

        return record

    async def _extract_candidate(
        self,
        doc: FetchedDocument,
        raw_project: Optional[RawProject] = None,
    ) -> RawIdeaExtraction:
        """Extracts raw candidate fields using structured LLM or adapter hints."""
        # If RawProject is already populated with high fidelity:
        if raw_project and raw_project.name and raw_project.description_raw:
            # Build evidence from raw text excerpts directly where matched
            evidence: Dict[str, str] = {}
            raw_text = doc.raw_text or ""

            # Name evidence
            if raw_project.name in raw_text:
                evidence["name"] = raw_project.name

            # One-liner
            if raw_project.tagline and raw_project.tagline in raw_text:
                evidence["one_liner"] = raw_project.tagline

            # Placement evidence
            placement_str = raw_project.placement.value if raw_project.placement else "none"
            if raw_project.prize_name and raw_project.prize_name in raw_text:
                evidence["placement"] = raw_project.prize_name
            elif raw_project.placement and raw_project.placement != SourcePlacement.NONE:
                if raw_project.placement.value in raw_text:
                    evidence["placement"] = raw_project.placement.value

            # Problem / Solution heuristics from description paragraphs
            paragraphs = [p.strip() for p in raw_project.description_raw.split("\n\n") if len(p.strip()) > 30]
            prob = paragraphs[0] if len(paragraphs) > 0 else None
            sol = paragraphs[1] if len(paragraphs) > 1 else (paragraphs[0] if len(paragraphs) > 0 else None)

            if prob and prob[:80] in raw_text:
                evidence["problem"] = prob[:200]
            if sol and sol[:80] in raw_text:
                evidence["solution"] = sol[:200]

            return RawIdeaExtraction(
                name=raw_project.name,
                one_liner=raw_project.tagline,
                problem=prob,
                solution=sol,
                target_users="Developers and end-users",
                domain_tags=raw_project.tags[:5] if raw_project.tags else ["AI / Software"],
                tech_stack=raw_project.tech_stack if raw_project.tech_stack else raw_project.tags,
                business_model="Open Source / SaaS",
                stage="prototype",
                event_name=raw_project.event_name,
                year=raw_project.year,
                placement=placement_str,
                team_size=raw_project.team_size or (len(raw_project.authors) if raw_project.authors else 1),
                links=raw_project.links,
                evidence=evidence,
            )

        # LLM Structured Extraction pass for unstructured text
        prompt = (
            "You are an expert idea miner. Extract structured startup/hackathon project facts from this page.\n"
            "CRITICAL: For every field you extract, you MUST supply an exact verbatim excerpt of <= 200 characters "
            "copied directly from the text below under 'evidence'. If a field (like placement or prize) is not mentioned, "
            "set it to null/none. DO NOT FABRICATE OR GUESS.\n\n"
            f"Page Text:\n{doc.raw_text[:4000]}\n\n"
            "Return valid JSON adhering to RawIdeaExtraction schema."
        )

        try:
            model = self.router.get_model("worker")
            resp = await model.ainvoke(prompt)
            content = resp.content if hasattr(resp, "content") else str(resp)
            # Parse JSON
            match = re.search(r"\{.*\}", content, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                return RawIdeaExtraction(**data)
        except Exception:
            pass

        # Fallback minimal candidate
        title = doc.title or "Untitled Idea"
        return RawIdeaExtraction(
            name=title,
            problem=doc.raw_text[:200] if doc.raw_text else None,
            solution=doc.raw_text[200:400] if len(doc.raw_text or "") > 200 else None,
            evidence={"problem": doc.raw_text[:150]} if doc.raw_text else {},
        )
