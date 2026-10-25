from __future__ import annotations

import collections
import math
from typing import Any, Callable, Dict, List, Optional
from pydantic import BaseModel, Field

from core.ideas.schemas import IdeaRecord


def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    n1 = math.sqrt(sum(a * a for a in v1))
    n2 = math.sqrt(sum(b * b for b in v2))
    if n1 == 0 or n2 == 0:
        return 0.0
    return dot / (n1 * n2)


class WhitespaceOpportunity(BaseModel):
    title: str
    description: str
    suggested_domains: List[str] = Field(default_factory=list)
    suggested_tech_stack: List[str] = Field(default_factory=list)
    novelty_score: float  # 1.0 - max_similarity
    closest_project_id: Optional[str] = None
    closest_project_name: Optional[str] = None
    verified_evidence_location: Optional[str] = None


class WhitespaceAnalysisReport(BaseModel):
    problem_statement: str
    sample_size_evaluated: int
    overall_novelty_score: float
    nearest_existing_projects: List[Dict[str, Any]] = Field(default_factory=list)
    whitespace_opportunities: List[WhitespaceOpportunity] = Field(default_factory=list)
    methodology_note: str = (
        "Whitespace gap analysis computes cosine distances in embedding space "
        "and identifies low-density feature combinations (domains x tech stacks) "
        "relative to the existing crawled corpus. Sample sizes and nearest projects are cited."
    )


def detect_whitespace_gaps(
    problem_statement: str,
    ideas: List[IdeaRecord],
    problem_embedding: Optional[List[float]] = None,
    embedding_fn: Optional[Callable[[str], List[float]]] = None,
    target_domains: Optional[List[str]] = None,
    target_tech: Optional[List[str]] = None,
) -> WhitespaceAnalysisReport:
    """
    Identifies low-density regions in embedding space crossed with problem statements
    (e.g., hackathon problem statements or user briefs) to find combos nobody has built.
    Cites sample size and links to closest existing projects with verified locations.
    """
    N = len(ideas)
    if N == 0:
        return WhitespaceAnalysisReport(
            problem_statement=problem_statement,
            sample_size_evaluated=0,
            overall_novelty_score=1.0,
        )

    # Compute problem embedding if not provided
    p_emb = problem_embedding
    if p_emb is None and embedding_fn is not None:
        try:
            p_emb = embedding_fn(problem_statement)
        except Exception:
            p_emb = None

    # Calculate similarity to existing ideas
    similarities: List[tuple[IdeaRecord, float]] = []
    for idea in ideas:
        sim = 0.0
        if p_emb and idea.embedding and len(p_emb) == len(idea.embedding):
            sim = cosine_similarity(p_emb, idea.embedding)
        else:
            # Fallback keyword overlap (Jaccard)
            p_words = set(problem_statement.lower().split())
            i_text = f"{idea.name} {idea.problem} {idea.solution} {' '.join(idea.domain_tags)} {' '.join(idea.tech_stack)}".lower()
            i_words = set(i_text.split())
            if p_words and i_words:
                sim = len(p_words & i_words) / len(p_words | i_words)
        similarities.append((idea, sim))

    # Sort descending by similarity
    similarities.sort(key=lambda x: x[1], reverse=True)

    max_sim = similarities[0][1] if similarities else 0.0
    overall_novelty = round(max(0.0, min(1.0, 1.0 - max_sim)), 3)

    # Closest existing projects
    nearest = []
    for idea, sim in similarities[:5]:
        loc = None
        if idea.evidence:
            ev = list(idea.evidence.values())[0] if isinstance(idea.evidence, dict) else idea.evidence[0]
            loc = ev.url or ev.text_fragment_url
        nearest.append({
            "id": idea.id,
            "name": idea.name,
            "similarity": round(sim, 3),
            "domain_tags": idea.domain_tags,
            "tech_stack": idea.tech_stack,
            "placement": idea.placement.value if hasattr(idea.placement, "value") else str(idea.placement),
            "verified_location": loc or idea.first_seen_url,
        })

    # Find low-density domain x tech combinations
    existing_combos = collections.defaultdict(int)
    all_domains = collections.Counter()
    all_tech = collections.Counter()
    for idea in ideas:
        for d in idea.domain_tags:
            all_domains[d] += 1
            for t in idea.tech_stack:
                existing_combos[(d, t)] += 1
        for t in idea.tech_stack:
            all_tech[t] += 1

    candidate_domains = target_domains or [d for d, _ in all_domains.most_common(6)] or ["General"]
    candidate_tech = target_tech or [t for t, _ in all_tech.most_common(6)] or ["FastAPI", "Postgres"]

    opportunities: List[WhitespaceOpportunity] = []
    closest_top = similarities[0][0] if similarities else None
    closest_loc = None
    if closest_top and closest_top.evidence:
        ev_top = list(closest_top.evidence.values())[0] if isinstance(closest_top.evidence, dict) else closest_top.evidence[0]
        closest_loc = ev_top.url or ev_top.text_fragment_url

    # Check which (domain, tech) pairs have 0 or very low representation
    unbuilt_pairs = []
    for d in candidate_domains:
        for t in candidate_tech:
            count = existing_combos.get((d, t), 0)
            if count <= 1:
                unbuilt_pairs.append((d, t, count))

    # Take top 3-4 unbuilt pairs to formulate whitespace opportunities
    for d, t, count in unbuilt_pairs[:4]:
        opp_title = f"Unexplored Intersection: {d} with {t}"
        opp_desc = (
            f"Across {N} analyzed projects, only {count} project(s) combined '{d}' with '{t}'. "
            f"Addressing '{problem_statement[:80]}...' via this paradigm represents an open whitespace gap."
        )
        opp_novelty = round(min(1.0, overall_novelty + (0.1 if count == 0 else 0.05)), 3)
        opportunities.append(
            WhitespaceOpportunity(
                title=opp_title,
                description=opp_desc,
                suggested_domains=[d],
                suggested_tech_stack=[t],
                novelty_score=opp_novelty,
                closest_project_id=closest_top.id if closest_top else None,
                closest_project_name=closest_top.name if closest_top else None,
                verified_evidence_location=closest_loc or (closest_top.first_seen_url if closest_top else None),
            )
        )

    # If no pairs found, provide a general whitespace opportunity based on overall novelty
    if not opportunities and closest_top:
        opportunities.append(
            WhitespaceOpportunity(
                title=f"Novel Solution Gap for '{problem_statement[:50]}'",
                description=f"Problem statement presents {overall_novelty * 100:.1f}% novelty against closest project '{closest_top.name}'.",
                suggested_domains=candidate_domains[:2],
                suggested_tech_stack=candidate_tech[:2],
                novelty_score=overall_novelty,
                closest_project_id=closest_top.id,
                closest_project_name=closest_top.name,
                verified_evidence_location=closest_loc or closest_top.first_seen_url,
            )
        )

    return WhitespaceAnalysisReport(
        problem_statement=problem_statement,
        sample_size_evaluated=N,
        overall_novelty_score=overall_novelty,
        nearest_existing_projects=nearest,
        whitespace_opportunities=opportunities,
    )
