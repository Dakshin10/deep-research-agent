from __future__ import annotations

import csv
import io
import json
from typing import Dict, List, Optional

from core.ideas.schemas import IdeaBrief, IdeaCard
from core.tools.pptx_generator import PPTXGenerator


def export_cards_to_markdown(
    cards: List[IdeaCard],
    brief: Optional[IdeaBrief] = None,
) -> str:
    """Exports IdeaCards as a formatted Markdown report with verified evidence locations."""
    lines: List[str] = [
        "# Idea Miner: Evidence-Grounded Idea Portfolio",
        "",
    ]
    if brief:
        lines.extend([
            f"**Problem Statement / Brief**: {brief.problem_statement}",
            f"**Domain Focus**: {brief.domain or 'Cross-disciplinary'}",
            f"**Constraints**: {', '.join(f'{k}: {v}' for k, v in (brief.constraints or {}).items()) or 'None specified'}",
            "",
            "---",
            "",
        ])

    lines.append(f"Generated **{len(cards)} Idea Cards** grounded in real-world hackathons and startups.\n")

    for idx, card in enumerate(cards, 1):
        lines.extend([
            f"## {idx}. {card.title}",
            "",
            f"- **Target Users**: {card.target_users}",
            f"- **Novelty Score**: `{card.novelty_score:.3f}` (1.0 = highly original, 0.0 = clone)",
            f"- **Suggested Tech Stack**: `{', '.join(card.suggested_tech_stack)}`",
            "",
            f"### Problem & Solution",
            f"**Problem**: {card.problem}",
            "",
            f"**Solution Sketch**: {card.solution_sketch}",
            "",
            f"**Why Now?**: {card.why_now}",
            "",
            f"### Architecture & MVP Scope",
            f"**Architecture Sketch**:\n```\n{card.architecture_sketch}\n```",
            "",
            f"**MVP Scope**: {card.mvp_scope}",
            "",
            f"**Key Differentiation**: {card.differentiation}",
            "",
            f"**Identified Risks**:",
        ])
        for r in card.risks:
            lines.append(f"  - {r}")

        if card.past_winner_rules_warning:
            lines.extend([
                "",
                f"> [!WARNING]",
                f"> **Event Rules Compliance Notice**:",
                f"> {card.past_winner_rules_warning}",
            ])

        if card.regeneration_notes:
            lines.extend([
                "",
                f"> [!NOTE]",
                f"> **Originality Refinement Note**: {card.regeneration_notes}",
            ])

        lines.extend([
            "",
            f"### Verified Inspirations ({len(card.inspirations)} projects)",
        ])
        for insp in card.inspirations:
            loc_md = f"[[evidence location]({insp.verified_location})]" if insp.verified_location else f"[[source]({insp.source_url})]"
            win_tag = " `[PAST WINNER]`" if insp.was_winner else ""
            lines.append(
                f"- **{insp.project_name}**{win_tag}: {insp.key_takeaway} {loc_md}"
            )

        if card.closest_existing_projects:
            lines.extend([
                "",
                f"**Closest Existing Reference Projects**:",
            ])
            for cp in card.closest_existing_projects[:3]:
                lines.append(
                    f"  - {cp['name']} (Similarity: {cp.get('similarity', 0.0):.2f}, Placement: {cp.get('placement', 'none')})"
                )

        lines.extend(["", "---", ""])

    return "\n".join(lines)


def export_cards_to_json(cards: List[IdeaCard], indent: int = 2) -> str:
    """Exports IdeaCards as a JSON string."""
    return json.dumps([c.model_dump(mode="json") for c in cards], indent=indent)


def export_cards_to_csv(cards: List[IdeaCard]) -> str:
    """Exports IdeaCards into CSV format for tabular evaluation."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "id",
        "title",
        "target_users",
        "novelty_score",
        "tech_stack",
        "solution_sketch",
        "mvp_scope",
        "inspirations_count",
        "has_winner_warning",
    ])

    for c in cards:
        writer.writerow([
            c.id,
            c.title,
            c.target_users,
            c.novelty_score,
            ", ".join(c.suggested_tech_stack),
            c.solution_sketch.replace("\n", " "),
            c.mvp_scope.replace("\n", " "),
            len(c.inspirations),
            bool(c.past_winner_rules_warning),
        ])

    return output.getvalue()


def export_cards_to_pptx(
    cards: List[IdeaCard],
    title: str = "Idea Miner: Grounded Concept Deck",
) -> bytes:
    """
    Exports IdeaCards as an editable PowerPoint presentation deck.
    Adheres strictly to the 5-bullet ceiling per slide and zero empty shapes rule.
    """
    sections: Dict[str, List[str]] = {}

    for card in cards:
        slide_title = card.title[:55]
        bullets = [
            f"Problem: {card.problem[:140]}",
            f"Solution: {card.solution_sketch[:140]}",
            f"Stack: {', '.join(card.suggested_tech_stack)[:140]}",
            f"MVP Scope: {card.mvp_scope[:140]}",
            f"Novelty: {card.novelty_score:.2f} ({len(card.inspirations)} verified inspirations)",
        ]
        sections[slide_title] = bullets

    return PPTXGenerator.generate_deck(
        title=title,
        sections=sections,
        subtitle="Autonomous Hackathon & Startup Ideation Portfolio",
    )
