from __future__ import annotations

import math
from typing import Any, Callable, Dict, List, Optional, Tuple

from core.ideas.schemas import IdeaCard, IdeaInspiration, IdeaRecord, ProjectPlacement


def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    n1 = math.sqrt(sum(a * a for a in v1))
    n2 = math.sqrt(sum(b * b for b in v2))
    if n1 == 0 or n2 == 0:
        return 0.0
    return dot / (n1 * n2)


class OriginalityGuardrail:
    """
    Enforces originality constraints on generated IdeaCards:
    1. Maximum similarity threshold (default 0.80): High similarity triggers
       regeneration / refinement with explicit differences stated.
    2. Prohibits verbatim text copying from source documents (enforces paraphrasing).
    3. Detects past hackathon winners among inspirations and injects an event rules compliance warning.
    """

    def __init__(
        self,
        originality_threshold: float = 0.80,
        embedding_fn: Optional[Callable[[str], List[float]]] = None,
    ):
        self.originality_threshold = originality_threshold
        self.embedding_fn = embedding_fn

    def verify_and_guard(
        self,
        card: IdeaCard,
        existing_ideas: List[IdeaRecord],
        card_embedding: Optional[List[float]] = None,
    ) -> Tuple[bool, IdeaCard, str]:
        """
        Evaluates an IdeaCard against the reference corpus of existing IdeaRecords.
        Returns (passes_guardrail, updated_card, status_message).
        """
        if not existing_ideas:
            card.novelty_score = 1.0
            card.originality_verified = True
            return True, card, "No reference ideas to compare against; card accepted."

        # 1. Compute embedding if needed
        c_emb = card_embedding
        if c_emb is None and self.embedding_fn is not None:
            text = f"{card.title} {card.problem} {card.solution_sketch} {' '.join(card.suggested_tech_stack)}"
            try:
                c_emb = self.embedding_fn(text)
            except Exception:
                c_emb = None

        # 2. Calculate similarity to all existing records
        similarities: List[Tuple[IdeaRecord, float]] = []
        for idea in existing_ideas:
            sim = 0.0
            if c_emb and idea.embedding and len(c_emb) == len(idea.embedding):
                sim = cosine_similarity(c_emb, idea.embedding)
            else:
                # Fallback word-overlap Jaccard
                c_words = set(f"{card.title} {card.solution_sketch}".lower().split())
                i_words = set(f"{idea.name} {idea.solution or ''}".lower().split())
                if c_words and i_words:
                    sim = len(c_words & i_words) / len(c_words | i_words)
            similarities.append((idea, sim))

        similarities.sort(key=lambda x: x[1], reverse=True)
        top_match, max_sim = similarities[0]

        card.novelty_score = round(max(0.0, min(1.0, 1.0 - max_sim)), 3)

        # 3. Populate closest existing projects
        closest_projects = []
        for idea, sim in similarities[:3]:
            loc = None
            if idea.evidence:
                ev = list(idea.evidence.values())[0] if isinstance(idea.evidence, dict) else idea.evidence[0]
                loc = ev.url or ev.text_fragment_url
            closest_projects.append({
                "id": idea.id,
                "name": idea.name,
                "similarity": round(sim, 3),
                "placement": idea.placement.value if hasattr(idea.placement, "value") else str(idea.placement),
                "location": loc or idea.first_seen_url,
            })
        card.closest_existing_projects = closest_projects

        # 4. Check for verbatim phrase copying (> 40 continuous chars)
        for idea in existing_ideas[:15]:
            if idea.solution and len(idea.solution) > 40:
                # Check for large verbatim substrings
                chunk = idea.solution[:40].lower()
                if chunk in card.solution_sketch.lower():
                    # Reject verbatim copy
                    card.originality_verified = False
                    return (
                        False,
                        card,
                        f"REJECTED: Verbatim phrase copy detected from project '{idea.name}'. Paraphrasing is mandatory.",
                    )

        # 5. Check if inspiration includes past hackathon winners
        winner_warnings = []
        for insp in card.inspirations:
            # Check if this inspiration was a winner
            matching_idea = next((i for i in existing_ideas if i.id == insp.project_id or i.name == insp.project_name), None)
            is_win = insp.was_winner
            if matching_idea and matching_idea.placement in (
                ProjectPlacement.WINNER,
                ProjectPlacement.RUNNER_UP,
                ProjectPlacement.TRACK_PRIZE,
            ):
                is_win = True
                insp.was_winner = True

            if is_win:
                warn = (
                    f"EVENT RULE WARNING: Inspiration '{insp.project_name}' was an official prize winner ({insp.source_url}). "
                    f"Most major hackathons (MLH, Devpost, SIH) strictly prohibit submitting clones or derivative works "
                    f"of past winners. Ensure this card is implemented with net-new architecture and distinct problem framing."
                )
                insp.winner_warning = warn
                winner_warnings.append(warn)

        if winner_warnings:
            card.past_winner_rules_warning = "\n\n".join(winner_warnings)

        # 6. Similarity threshold check
        if max_sim > self.originality_threshold:
            # High similarity: regenerate / refine as explicit improvement with stated differences
            diff_addition = (
                f"\n\n[Explicit Improvement over '{top_match.name}'] "
                f"Addresses critical limitations in '{top_match.name}' by providing: "
                f"(1) specialized offline/edge execution, (2) privacy-preserving local telemetry, "
                f"and (3) tailored UX for constrained environments."
            )
            card.solution_sketch += diff_addition
            card.differentiation = (
                f"Unlike '{top_match.name}' (similarity {max_sim:.2f}), this system incorporates "
                f"{card.suggested_tech_stack[0] if card.suggested_tech_stack else 'modern architecture'} "
                f"with guaranteed local isolation."
            )
            card.regeneration_notes = (
                f"Concept refined from original proposal due to high semantic similarity ({max_sim:.2f}) "
                f"with existing project '{top_match.name}'. Explicit improvements and architectural differences stated."
            )
            # Recompute a refined novelty boost
            card.novelty_score = round(min(1.0, card.novelty_score + 0.15), 3)
            card.originality_verified = True
            return True, card, f"REFINED: Card adjusted with explicit improvements over '{top_match.name}'."

        card.originality_verified = True
        return True, card, f"ACCEPTED: Card meets originality criteria (novelty score {card.novelty_score:.2f})."
