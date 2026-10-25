import pytest
from core.ideas.schemas import IdeaRecord, ProjectPlacement, ProjectStage, EvidenceEntry
from skills.idea_analysis.clustering import cluster_ideas
from skills.idea_analysis.trends import analyze_trends
from skills.idea_analysis.winner_patterns import analyze_winner_patterns
from skills.idea_analysis.whitespace import detect_whitespace_gaps
from skills.idea_analysis.engine import IdeaAnalysisEngine


@pytest.fixture
def sample_ideas():
    records = []
    # 4 winners, 6 non-winners
    data = [
        # Winners
        ("proj-1", "AI Clinical Diagnosis", ["Healthcare", "AI"], ["Python", "PyTorch", "FastAPI"], ProjectPlacement.WINNER, 3, "https://demo1.com", "https://youtube.com/v1", "Complex diagnostic workflow for emergency departments", [0.9, 0.1, 0.0]),
        ("proj-2", "DeFi Yield Optimizer", ["Finance", "Crypto"], ["Solidity", "React", "Rust"], ProjectPlacement.RUNNER_UP, 4, "https://demo2.com", "https://youtube.com/v2", "Automated smart contract portfolio rebalancer", [0.1, 0.9, 0.0]),
        ("proj-3", "Eco Tracker Drone", ["Climate", "Robotics"], ["Python", "ROS", "C++"], ProjectPlacement.TRACK_PRIZE, 2, "https://demo3.com", None, "Drone fleet telemetry for forest fire perimeter tracking", [0.0, 0.1, 0.9]),
        ("proj-4", "Edge AI Camera", ["AI", "Hardware"], ["Python", "TensorRT", "C++"], ProjectPlacement.WINNER, 4, "https://demo4.com", "https://youtube.com/v4", "Low latency computer vision at the network edge", [0.85, 0.15, 0.0]),
        # Non-winners
        ("proj-5", "Simple Healthcare Form", ["Healthcare"], ["HTML", "JavaScript"], ProjectPlacement.NONE, 1, None, None, "A basic web form for patient intake", [0.7, 0.1, 0.0]),
        ("proj-6", "Generic Crypto Wallet", ["Finance", "Crypto"], ["React", "JavaScript"], ProjectPlacement.NONE, 2, None, None, "Wallet interface", [0.1, 0.8, 0.0]),
        ("proj-7", "Todo App with AI", ["Productivity", "AI"], ["React", "Python"], ProjectPlacement.NONE, 1, "https://demo7.com", None, "Yet another todo list with LLM summarization", [0.5, 0.5, 0.0]),
        ("proj-8", "Social Feed Aggregator", ["Social"], ["Vue", "Node"], ProjectPlacement.NONE, 2, None, None, "Combines RSS feeds", [0.0, 0.0, 0.5]),
        ("proj-9", "Habit Tracker", ["Productivity"], ["Flutter", "Dart"], ProjectPlacement.NONE, 1, None, None, "Mobile app for tracking daily water habits", [0.0, 0.2, 0.3]),
        ("proj-10", "AI Chat Widget", ["AI"], ["Python", "FastAPI"], ProjectPlacement.NONE, 2, None, None, "Website chatbot popup", [0.8, 0.2, 0.0]),
    ]

    for pid, name, domains, tech, placement, team_size, demo, video, prob, emb in data:
        links = {}
        if demo:
            links["demo"] = demo
        if video:
            links["video"] = video

        ev = EvidenceEntry(
            field="placement",
            url=f"https://devpost.com/software/{pid}",
            excerpt="Won 1st Place overall" if placement == ProjectPlacement.WINNER else "Submitted to hackathon",
            char_start=0,
            char_end=20,
            text_fragment_url=f"https://devpost.com/software/{pid}#:~:text=overall",
        )

        records.append(
            IdeaRecord(
                id=pid,
                name=name,
                one_liner=f"One liner for {name}",
                problem=prob,
                solution=f"Solution for {name}",
                target_users="Developers, Engineers",
                domain_tags=domains,
                tech_stack=tech,
                stage=ProjectStage.PROTOTYPE,
                placement=placement,
                team_size=team_size,
                links=links,
                first_seen_url=f"https://devpost.com/software/{pid}",
                all_source_urls=[f"https://devpost.com/software/{pid}"],
                confidence=0.95,
                evidence={"placement": ev},
                embedding=emb,
            )
        )
    return records


def test_cluster_ideas(sample_ideas):
    clusters = cluster_ideas(sample_ideas, n_clusters=3)
    assert len(clusters) > 0
    total_assigned = sum(c.size for c in clusters)
    assert total_assigned == len(sample_ideas)

    for c in clusters:
        assert c.sample_size == len(sample_ideas)
        assert len(c.representative_project_ids) > 0
        assert isinstance(c.name, str)


def test_analyze_trends(sample_ideas):
    report = analyze_trends(sample_ideas)
    assert report.total_ideas_analyzed == 10
    assert len(report.top_domains) > 0
    assert len(report.top_tech_stacks) > 0

    # Verify sample sizes are cited
    for td in report.top_domains:
        assert td.sample_size == 10
        assert 0.0 <= td.win_rate <= 1.0
        assert td.status in ("saturated", "underexplored", "balanced")
        assert len(td.example_project_ids) > 0


def test_analyze_winner_patterns(sample_ideas):
    report = analyze_winner_patterns(sample_ideas)
    assert report.n_winners == 4
    assert report.n_non_winners == 6
    assert report.total_sample_size == 10

    # Check defensive feature comparisons
    feature_map = {fc.feature_name: fc for fc in report.feature_comparisons}
    assert "Working Demo URL Presence" in feature_map
    assert "Pitch Video URL Presence" in feature_map
    assert "Average Team Size" in feature_map

    demo_comp = feature_map["Working Demo URL Presence"]
    # 4/4 winners had demo (100%), 1/6 non-winners had demo (16.7%)
    assert demo_comp.winner_value == 100.0
    assert demo_comp.non_winner_value == round((1 / 6) * 100, 1)
    assert "correlation only" in demo_comp.caution_note.lower()

    # Team size: winners had mean team size (3+4+2+4)/4 = 3.25; non-winners: (1+2+1+2+1+2)/6 = 1.5
    team_comp = feature_map["Average Team Size"]
    assert team_comp.winner_value == 3.25
    assert team_comp.non_winner_value == 1.5


def test_detect_whitespace_gaps(sample_ideas):
    problem = "Smart agricultural irrigation system using satellite telemetry and edge LoRaWAN devices"
    # Target problem has novelty compared to existing healthcare/crypto/software
    report = detect_whitespace_gaps(
        problem_statement=problem,
        ideas=sample_ideas,
        target_domains=["Agriculture", "IoT", "Satellite"],
        target_tech=["LoRaWAN", "Rust", "Embedded C"],
    )

    assert report.sample_size_evaluated == 10
    assert report.overall_novelty_score >= 0.5  # Distinct from existing software
    assert len(report.nearest_existing_projects) > 0
    assert "verified_location" in report.nearest_existing_projects[0]

    # Opportunities should identify unbuilt combinations
    assert len(report.whitespace_opportunities) > 0
    for opp in report.whitespace_opportunities:
        assert opp.novelty_score > 0.0
        assert len(opp.suggested_domains) > 0
        assert len(opp.suggested_tech_stack) > 0


def test_idea_analysis_engine_full_report(sample_ideas):
    engine = IdeaAnalysisEngine()
    summary = engine.generate_full_analysis(
        ideas=sample_ideas,
        problem_statement="Autonomous robotic weed detection for organic farming",
        n_clusters=3,
    )

    assert summary.total_ideas == 10
    assert len(summary.clusters) > 0
    assert summary.trends.total_ideas_analyzed == 10
    assert summary.winner_patterns.n_winners == 4
    assert summary.whitespace_analysis is not None
    assert summary.whitespace_analysis.overall_novelty_score > 0.0

    # Check markdown report citations
    md = summary.markdown_report
    assert "Sample Size N=10" in md
    assert "Winner vs Non-Winner Feature Patterns" in md
    assert "Observational correlation" in md or "methodology" in md.lower() or "No causal claims" in md

    # Check optional chart generation
    chart_png = engine.render_trends_chart_png(summary.trends)
    if chart_png is not None:
        assert isinstance(chart_png, bytes)
        assert len(chart_png) > 100
