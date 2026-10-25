from __future__ import annotations

import io
from typing import Any, Callable, Dict, List, Optional
from pydantic import BaseModel, Field

from core.ideas.schemas import IdeaRecord
from skills.idea_analysis.clustering import ClusterResult, cluster_ideas
from skills.idea_analysis.trends import CategoryTrend, TrendAnalysisReport, analyze_trends
from skills.idea_analysis.winner_patterns import WinnerPatternReport, analyze_winner_patterns
from skills.idea_analysis.whitespace import WhitespaceAnalysisReport, detect_whitespace_gaps


class IdeaAnalysisSummary(BaseModel):
    total_ideas: int
    clusters: List[ClusterResult] = Field(default_factory=list)
    trends: TrendAnalysisReport
    winner_patterns: WinnerPatternReport
    whitespace_analysis: Optional[WhitespaceAnalysisReport] = None
    markdown_report: str = ""


class IdeaAnalysisEngine:
    """
    Unified sandboxed analysis engine for Idea Miner.
    Performs semantic clustering, temporal & categorical trend tracking,
    statistically defensible winner pattern comparison, and whitespace gap detection.
    All outputs cite sample sizes (N) and link to verified project evidence locations.
    """

    def __init__(self, embedding_fn: Optional[Callable[[str], List[float]]] = None):
        self.embedding_fn = embedding_fn

    def cluster(
        self, ideas: List[IdeaRecord], n_clusters: Optional[int] = None
    ) -> List[ClusterResult]:
        return cluster_ideas(ideas, n_clusters=n_clusters)

    def trends(self, ideas: List[IdeaRecord]) -> TrendAnalysisReport:
        return analyze_trends(ideas)

    def winner_patterns(self, ideas: List[IdeaRecord]) -> WinnerPatternReport:
        return analyze_winner_patterns(ideas)

    def whitespace(
        self,
        problem_statement: str,
        ideas: List[IdeaRecord],
        problem_embedding: Optional[List[float]] = None,
        target_domains: Optional[List[str]] = None,
        target_tech: Optional[List[str]] = None,
    ) -> WhitespaceAnalysisReport:
        return detect_whitespace_gaps(
            problem_statement=problem_statement,
            ideas=ideas,
            problem_embedding=problem_embedding,
            embedding_fn=self.embedding_fn,
            target_domains=target_domains,
            target_tech=target_tech,
        )

    def generate_full_analysis(
        self,
        ideas: List[IdeaRecord],
        problem_statement: Optional[str] = None,
        n_clusters: Optional[int] = None,
    ) -> IdeaAnalysisSummary:
        N = len(ideas)
        clusters = self.cluster(ideas, n_clusters=n_clusters)
        trends_rep = self.trends(ideas)
        winners_rep = self.winner_patterns(ideas)

        ws_rep = None
        if problem_statement:
            ws_rep = self.whitespace(problem_statement, ideas)

        md = self._format_markdown_report(N, clusters, trends_rep, winners_rep, ws_rep)

        return IdeaAnalysisSummary(
            total_ideas=N,
            clusters=clusters,
            trends=trends_rep,
            winner_patterns=winners_rep,
            whitespace_analysis=ws_rep,
            markdown_report=md,
        )

    def _format_markdown_report(
        self,
        N: int,
        clusters: List[ClusterResult],
        trends: TrendAnalysisReport,
        winners: WinnerPatternReport,
        whitespace: Optional[WhitespaceAnalysisReport],
    ) -> str:
        lines: List[str] = [
            f"# Idea Miner Analysis Report (Sample Size N={N})",
            "",
            "## 1. Semantic Clusters",
        ]
        if not clusters:
            lines.append("No clusters generated (insufficient embedded projects).")
        else:
            for c in clusters:
                lines.append(
                    f"- **{c.name}** (Size: {c.size}, Sample: {c.sample_size}): "
                    f"Top tech: {', '.join(c.top_tech) or 'None'}. "
                    f"Representative projects: {', '.join(c.representative_project_ids)}"
                )

        lines.extend([
            "",
            "## 2. Trend & Saturation Analysis",
            f"- **Analyzed Corpus**: {trends.total_ideas_analyzed} projects across {len(trends.top_domains)} domains.",
        ])

        if trends.saturated_categories:
            lines.append("### Saturated Categories (High Entries, Lower Relative Win Rate)")
            for s in trends.saturated_categories:
                lines.append(
                    f"- **{s.category}** ({s.category_type}): {s.total_entries} entries, "
                    f"{s.winners_count} winners ({s.win_rate * 100:.1f}% win rate, N={s.sample_size})"
                )

        if trends.underexplored_categories:
            lines.append("### Underexplored Opportunities (Low Entries, Higher Relative Win Rate)")
            for u in trends.underexplored_categories:
                lines.append(
                    f"- **{u.category}** ({u.category_type}): {u.total_entries} entries, "
                    f"{u.winners_count} winners ({u.win_rate * 100:.1f}% win rate, N={u.sample_size})"
                )

        lines.extend([
            "",
            "## 3. Winner vs Non-Winner Feature Patterns",
            f"> *Note: {winners.methodology_note}*",
            f"- Evaluated: {winners.n_winners} winners vs {winners.n_non_winners} non-winners (Total N={winners.total_sample_size}).",
        ])

        for fc in winners.feature_comparisons:
            lines.append(
                f"- **{fc.feature_name}**: Winners={fc.winner_value}, Non-Winners={fc.non_winner_value} "
                f"({fc.percentage_difference:+.1f}%). {fc.statistical_observation}"
            )

        if whitespace:
            lines.extend([
                "",
                f"## 4. Whitespace Gap Detection for: '{whitespace.problem_statement[:80]}'",
                f"- **Overall Novelty Score**: {whitespace.overall_novelty_score:.3f} (1.0 = completely unbuilt, 0.0 = identical to existing project).",
                f"- **Nearest Existing Reference Projects** (Sample size N={whitespace.sample_size_evaluated}):",
            ])
            for np in whitespace.nearest_existing_projects[:3]:
                loc_text = f"[[evidence]({np['verified_location']})]" if np.get("verified_location") else ""
                lines.append(
                    f"  - **{np['name']}** (Sim: {np['similarity']}, Placement: {np['placement']}): "
                    f"Stack: {', '.join(np['tech_stack'])} {loc_text}"
                )

            if whitespace.whitespace_opportunities:
                lines.append("### Recommended Whitespace Gaps to Build:")
                for opp in whitespace.whitespace_opportunities:
                    lines.append(
                        f"- **{opp.title}** (Novelty: {opp.novelty_score:.2f}): {opp.description}"
                    )

        return "\n".join(lines)

    def render_trends_chart_png(self, trends: TrendAnalysisReport) -> Optional[bytes]:
        """Optional helper rendering trend win rates to a PNG byte buffer using matplotlib."""
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt

            if not trends.top_domains:
                return None

            categories = [d.category for d in trends.top_domains[:8]]
            rates = [d.win_rate * 100 for d in trends.top_domains[:8]]

            fig, ax = plt.subplots(figsize=(8, 4))
            ax.barh(categories, rates, color="#2563eb")
            ax.set_xlabel("Win Rate (%)")
            ax.set_title(f"Domain Win Rates (Sample N={trends.total_ideas_analyzed})")
            plt.tight_layout()

            buf = io.BytesIO()
            plt.savefig(buf, format="png")
            plt.close(fig)
            buf.seek(0)
            return buf.getvalue()
        except Exception:
            return None
