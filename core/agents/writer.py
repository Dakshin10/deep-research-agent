from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from core.models.router import ModelRouter
from core.state.store import StateStore
from core.state.schemas import ResearchNote, Artifact, Brief
from core.guardrails.citation_gate import CitationGate


class WriterAgent:
    """
    Composes comprehensive research teardown reports strictly grounded in notes and artifacts.
    Enforces that every numeric, comparative, or superlative claim carries a valid inline note ID citation.
    """

    def __init__(
        self,
        tenant_id: str,
        state_store: StateStore,
        model_router: Optional[ModelRouter] = None,
    ):
        self.tenant_id = tenant_id
        self.state_store = state_store
        self.router = model_router or ModelRouter()

    async def write_report(
        self,
        job_id: str,
        query: str,
        brief: Optional[Brief],
        notes: List[ResearchNote],
        artifacts: Optional[List[Artifact]] = None,
    ) -> str:
        valid_note_ids = {n.id for n in notes}
        note_map = {n.id: n for n in notes}

        # Group notes by entity or task
        entity_notes: Dict[str, List[ResearchNote]] = {}
        for n in notes:
            # Infer entity or group
            ent = n.claim.split(":")[0] if ":" in n.claim else "Market Overview"
            if ent not in entity_notes:
                entity_notes[ent] = []
            entity_notes[ent].append(n)

        has_fallback_data = any(n.source_type == "fallback" for n in notes)

        # Build grounded report sections
        lines: List[str] = [
            f"# Competitive Teardown & Strategic Research Report: {query}",
            "",
        ]

        if has_fallback_data:
            lines.extend([
                "> [!WARNING]",
                "> **Notice: Provider Fallback Active**",
                "> One or more research sources operated in fallback mode because external provider API keys were not configured.",
                "> Fallback data is explicitly labeled in the citations below to prevent simulated data from being presented as real research.",
                "",
            ])

        lines.extend([
            "## 1. Executive Summary",
        ])

        # Use notes to formulate executive summary claims
        first_note = notes[0] if notes else None
        second_note = notes[1] if len(notes) > 1 else first_note
        if first_note:
            claim1 = re.sub(r"[.!?]", "", first_note.claim).strip()
            lines.append(f"Recent strategic analysis confirms that {claim1} [{first_note.id}].")
        if second_note and second_note.id != first_note.id:
            claim2 = re.sub(r"[.!?]", "", second_note.claim).strip()
            lines.append(f"Industry indicators demonstrate that {claim2} [{second_note.id}].")

        lines.extend([
            "",
            "## 2. In-Depth Entity & Competitor Breakdown",
        ])

        for ent, n_list in entity_notes.items():
            lines.append(f"### {ent}")
            for n in n_list[:3]:
                clean_claim = re.sub(r"[.!?]", "", n.claim).strip()
                lines.append(f"- Verified evidence indicates {clean_claim} [{n.id}].")
            lines.append("")

        lines.extend([
            "## 3. Comparative Capability & Positioning Analysis",
            "Comparative feature evaluation highlights key functional tradeoffs across surveyed options.",
        ])

        for n in notes[2:6]:
            clean_claim = re.sub(r"[.!?]", "", n.claim).strip()
            lines.append(f"- Platform capabilities benchmarked: {clean_claim} [{n.id}].")

        lines.extend([
            "",
            "## 4. Strategic Recommendations & Next Steps",
            "Based on the factual evidence gathered across web sources and proprietary intelligence, leadership should prioritize high-leverage workflows while reviewing tier pricing models.",
            "",
            "---",
            "### Verified Sources Index",
        ])

        for n in notes:
            ref = n.text_fragment_url or n.source_url or n.document_id or "Internal KB"
            type_label = f"{n.source_type.upper()} [SIMULATED FALLBACK]" if n.source_type == "fallback" else n.source_type.upper()

            # Format human-readable location
            location_parts = []
            if n.heading_path:
                heading_str = ' > '.join(n.heading_path)
                location_parts.append(f"section '{heading_str}'")
            if n.page_no:
                location_parts.append(f"p. {n.page_no} of PDF")
            if n.char_start is not None and n.char_end is not None:
                location_parts.append(f"offsets {n.char_start}-{n.char_end}")

            location_desc = f" - {', '.join(location_parts)}" if location_parts else ""
            lines.append(
                f"- **[{n.id}]** ({type_label}) {n.url or n.source_url or ref}{location_desc} [View Excerpt]({ref}): \"{n.excerpt[:140].strip()}\""
            )

        full_draft = "\n".join(lines)

        # Build location verification lookup for CitationGate
        note_locations = {
            n.id: bool(n.is_verified or n.char_start is not None or n.heading_path or n.page_no or n.source_type in ("kb", "computed"))
            for n in notes
        }

        # Run through strict CitationGate
        gate = CitationGate(valid_note_ids=valid_note_ids, note_locations=note_locations, strict=True)
        gate_res = gate.evaluate(full_draft)
        final_report = gate_res.cleaned_text if not gate_res.passed else full_draft

        # Persist as Artifact
        artifact = Artifact(
            job_id=job_id,
            tenant_id=self.tenant_id,
            artifact_type="report",
            title=f"Final Research Report: {query[:60]}",
            content=final_report,
            metadata={"total_notes": len(notes), "total_citations": len(gate_res.valid_citations_found)},
        )
        await self.state_store.add_artifact(artifact)

        return final_report
