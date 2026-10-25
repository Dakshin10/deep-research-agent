from __future__ import annotations

import collections
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from core.ideas.schemas import IdeaRecord, ProjectPlacement


class CategoryTrend(BaseModel):
    category: str
    category_type: str  # "domain" | "tech_stack" | "year"
    total_entries: int
    winners_count: int
    win_rate: float
    status: str  # "saturated" | "underexplored" | "balanced"
    sample_size: int
    example_project_ids: List[str] = Field(default_factory=list)


class TrendAnalysisReport(BaseModel):
    total_ideas_analyzed: int
    by_year: Dict[str, int] = Field(default_factory=dict)
    top_domains: List[CategoryTrend] = Field(default_factory=list)
    top_tech_stacks: List[CategoryTrend] = Field(default_factory=list)
    saturated_categories: List[CategoryTrend] = Field(default_factory=list)
    underexplored_categories: List[CategoryTrend] = Field(default_factory=list)


def analyze_trends(ideas: List[IdeaRecord]) -> TrendAnalysisReport:
    """
    Analyzes trends across domains and tech stacks over time.
    Calculates statistical win rate per category.
    Identifies:
      - Saturated: above-median entries, below-median win rate.
      - Underexplored: below-median entries, above-median win rate.
    States sample size N on all outputs.
    """
    N = len(ideas)
    if N == 0:
        return TrendAnalysisReport(total_ideas_analyzed=0)

    # 1. By Year
    year_counts: Dict[str, int] = collections.defaultdict(int)
    for i in ideas:
        yr = str(i.year) if i.year else "Unknown"
        year_counts[yr] += 1

    # 2. Domain trends
    domain_stats: Dict[str, Dict[str, Any]] = collections.defaultdict(
        lambda: {"total": 0, "winners": 0, "examples": []}
    )
    for i in ideas:
        is_winner = i.placement in (
            ProjectPlacement.WINNER,
            ProjectPlacement.RUNNER_UP,
            ProjectPlacement.TRACK_PRIZE,
        )
        for d in (i.domain_tags or ["General"]):
            domain_stats[d]["total"] += 1
            if is_winner:
                domain_stats[d]["winners"] += 1
            if len(domain_stats[d]["examples"]) < 3:
                domain_stats[d]["examples"].append(i.id)

    # 3. Tech stack trends
    tech_stats: Dict[str, Dict[str, Any]] = collections.defaultdict(
        lambda: {"total": 0, "winners": 0, "examples": []}
    )
    for i in ideas:
        is_winner = i.placement in (
            ProjectPlacement.WINNER,
            ProjectPlacement.RUNNER_UP,
            ProjectPlacement.TRACK_PRIZE,
        )
        for t in (i.tech_stack or ["Standard"]):
            tech_stats[t]["total"] += 1
            if is_winner:
                tech_stats[t]["winners"] += 1
            if len(tech_stats[t]["examples"]) < 3:
                tech_stats[t]["examples"].append(i.id)

    # Compute medians for saturation / underexplored classification
    all_totals = [s["total"] for s in domain_stats.values()] or [1]
    all_win_rates = [
        s["winners"] / max(1, s["total"]) for s in domain_stats.values()
    ] or [0.0]

    median_entries = sorted(all_totals)[len(all_totals) // 2]
    median_win_rate = sorted(all_win_rates)[len(all_win_rates) // 2]

    domain_trends: List[CategoryTrend] = []
    saturated: List[CategoryTrend] = []
    underexplored: List[CategoryTrend] = []

    for dom, s in sorted(domain_stats.items(), key=lambda x: x[1]["total"], reverse=True):
        win_rate = round(s["winners"] / max(1, s["total"]), 3)
        if s["total"] >= median_entries and win_rate < median_win_rate:
            status = "saturated"
        elif s["total"] <= median_entries and win_rate > median_win_rate:
            status = "underexplored"
        else:
            status = "balanced"

        ct = CategoryTrend(
            category=dom,
            category_type="domain",
            total_entries=s["total"],
            winners_count=s["winners"],
            win_rate=win_rate,
            status=status,
            sample_size=N,
            example_project_ids=s["examples"],
        )
        domain_trends.append(ct)
        if status == "saturated":
            saturated.append(ct)
        elif status == "underexplored":
            underexplored.append(ct)

    tech_trends: List[CategoryTrend] = []
    for tech, s in sorted(tech_stats.items(), key=lambda x: x[1]["total"], reverse=True):
        win_rate = round(s["winners"] / max(1, s["total"]), 3)
        status = "balanced"
        if s["total"] >= median_entries and win_rate < median_win_rate:
            status = "saturated"
        elif s["total"] <= median_entries and win_rate > median_win_rate:
            status = "underexplored"

        tech_trends.append(
            CategoryTrend(
                category=tech,
                category_type="tech_stack",
                total_entries=s["total"],
                winners_count=s["winners"],
                win_rate=win_rate,
                status=status,
                sample_size=N,
                example_project_ids=s["examples"],
            )
        )

    return TrendAnalysisReport(
        total_ideas_analyzed=N,
        by_year=dict(year_counts),
        top_domains=domain_trends[:10],
        top_tech_stacks=tech_trends[:10],
        saturated_categories=saturated[:5],
        underexplored_categories=underexplored[:5],
    )
