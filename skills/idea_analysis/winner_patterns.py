from __future__ import annotations

import collections
import statistics
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from core.ideas.schemas import IdeaRecord, ProjectPlacement


class WinnerFeatureComparison(BaseModel):
    feature_name: str
    winner_value: float
    non_winner_value: float
    percentage_difference: float
    statistical_observation: str
    caution_note: str = "Observational correlation only; does not imply causal relationship."


class WinnerPatternReport(BaseModel):
    n_winners: int
    n_non_winners: int
    total_sample_size: int
    feature_comparisons: List[WinnerFeatureComparison] = Field(default_factory=list)
    top_winning_tech_stacks: List[Dict[str, Any]] = Field(default_factory=list)
    top_winning_domains: List[Dict[str, Any]] = Field(default_factory=list)
    methodology_note: str = (
        "Analysis compares winners (winner, runner-up, track prize) vs non-winners "
        "on verifiable features in the crawled dataset. Sample sizes are explicitly reported. "
        "No causal claims are asserted."
    )


def analyze_winner_patterns(ideas: List[IdeaRecord]) -> WinnerPatternReport:
    """
    Compares winners vs non-winners across team size, demo presence, video presence,
    problem specificity (length), and tech stack frequency.
    Reports sample sizes and uses statistically defensible language without claiming causation.
    """
    winners = [
        i for i in ideas
        if i.placement in (
            ProjectPlacement.WINNER,
            ProjectPlacement.RUNNER_UP,
            ProjectPlacement.TRACK_PRIZE,
        )
    ]
    non_winners = [i for i in ideas if i not in winners]

    n_win = len(winners)
    n_non = len(non_winners)
    N = len(ideas)

    if n_win == 0 or n_non == 0:
        return WinnerPatternReport(
            n_winners=n_win,
            n_non_winners=n_non,
            total_sample_size=N,
        )

    # 1. Team size comparison
    win_teams = [w.team_size for w in winners if w.team_size is not None]
    non_teams = [nw.team_size for nw in non_winners if nw.team_size is not None]

    avg_win_team = round(statistics.mean(win_teams), 2) if win_teams else 0.0
    avg_non_team = round(statistics.mean(non_teams), 2) if non_teams else 0.0
    diff_team = round(((avg_win_team - avg_non_team) / max(0.1, avg_non_team)) * 100, 1) if avg_non_team > 0 else 0.0

    # 2. Demo presence rate
    win_demo = sum(1 for w in winners if w.links.get("demo")) / max(1, n_win)
    non_demo = sum(1 for nw in non_winners if nw.links.get("demo")) / max(1, n_non)
    diff_demo = round((win_demo - non_demo) * 100, 1)

    # 3. Video pitch presence rate
    win_video = sum(1 for w in winners if w.links.get("video")) / max(1, n_win)
    non_video = sum(1 for nw in non_winners if nw.links.get("video")) / max(1, n_non)
    diff_video = round((win_video - non_video) * 100, 1)

    # 4. Problem specificity (mean character length of verified problem statement)
    win_prob_lens = [len(w.problem) for w in winners if w.problem]
    non_prob_lens = [len(nw.problem) for nw in non_winners if nw.problem]
    avg_win_prob_len = round(statistics.mean(win_prob_lens), 1) if win_prob_lens else 0.0
    avg_non_prob_len = round(statistics.mean(non_prob_lens), 1) if non_prob_lens else 0.0
    diff_prob = round(((avg_win_prob_len - avg_non_prob_len) / max(1.0, avg_non_prob_len)) * 100, 1)

    comparisons = [
        WinnerFeatureComparison(
            feature_name="Working Demo URL Presence",
            winner_value=round(win_demo * 100, 1),
            non_winner_value=round(non_demo * 100, 1),
            percentage_difference=diff_demo,
            statistical_observation=f"Winning projects are associated with a {abs(diff_demo):.1f}% {'higher' if diff_demo >= 0 else 'lower'} rate of public demo links.",
        ),
        WinnerFeatureComparison(
            feature_name="Pitch Video URL Presence",
            winner_value=round(win_video * 100, 1),
            non_winner_value=round(non_video * 100, 1),
            percentage_difference=diff_video,
            statistical_observation=f"Winning projects demonstrate {abs(diff_video):.1f}% {'higher' if diff_video >= 0 else 'lower'} video presence.",
        ),
        WinnerFeatureComparison(
            feature_name="Average Team Size",
            winner_value=avg_win_team,
            non_winner_value=avg_non_team,
            percentage_difference=diff_team,
            statistical_observation=f"Mean team size is {avg_win_team} for winners versus {avg_non_team} for non-winners.",
        ),
        WinnerFeatureComparison(
            feature_name="Problem Statement Specificity (Char Length)",
            winner_value=avg_win_prob_len,
            non_winner_value=avg_non_prob_len,
            percentage_difference=diff_prob,
            statistical_observation=f"Winning problem descriptions averaged {avg_win_prob_len} chars versus {avg_non_prob_len} chars.",
        ),
    ]

    # Top winning tech stacks
    win_tech = collections.Counter(t for w in winners for t in w.tech_stack)
    top_tech = [
        {"tech": t, "winner_count": count, "frequency_pct": round((count / max(1, n_win)) * 100, 1)}
        for t, count in win_tech.most_common(5)
    ]

    # Top winning domains
    win_dom = collections.Counter(d for w in winners for d in w.domain_tags)
    top_dom = [
        {"domain": d, "winner_count": count, "frequency_pct": round((count / max(1, n_win)) * 100, 1)}
        for d, count in win_dom.most_common(5)
    ]

    return WinnerPatternReport(
        n_winners=n_win,
        n_non_winners=n_non,
        total_sample_size=N,
        feature_comparisons=comparisons,
        top_winning_tech_stacks=top_tech,
        top_winning_domains=top_dom,
    )
