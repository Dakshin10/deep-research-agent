import io
import pytest
from pptx import Presentation

from core.ideas.schemas import (
    IdeaBrief,
    IdeaCard,
    IdeaInspiration,
    IdeaRecord,
    ProjectPlacement,
    ProjectStage,
    EvidenceEntry,
)
from core.ideas.guardrails import OriginalityGuardrail
from core.ideas.generator import IdeaGeneratorAgent
from core.ideas.export import (
    export_cards_to_markdown,
    export_cards_to_json,
    export_cards_to_csv,
    export_cards_to_pptx,
)


@pytest.fixture
def sample_reference_ideas():
    records = []
    projects = [
        ("ref-1", "HealthLens AI", "Computer vision model detecting skin anomalies", ProjectPlacement.WINNER, [0.9, 0.1, 0.0], "https://devpost.com/software/healthlens"),
        ("ref-2", "SolarFlow IoT", "Telemetry sensors optimizing solar panel angles", ProjectPlacement.TRACK_PRIZE, [0.1, 0.9, 0.0], "https://devpost.com/software/solarflow"),
        ("ref-3", "CodeBuddy CLI", "Terminal copilot for automated git commit drafting", ProjectPlacement.NONE, [0.0, 0.1, 0.9], "https://github.com/codebuddy/cli"),
        ("ref-4", "DeFi Hedger", "Automated liquidation protection for lending protocols", ProjectPlacement.RUNNER_UP, [0.8, 0.2, 0.0], "https://devpost.com/software/defi-hedger"),
        ("ref-5", "AgriDrone Fleet", "Multispectral aerial survey for crop hydration", ProjectPlacement.WINNER, [0.2, 0.8, 0.0], "https://devpost.com/software/agridrone"),
    ]

    for pid, name, sol, placement, emb, url in projects:
        ev = EvidenceEntry(
            field="placement",
            url=url,
            excerpt=f"Project {name} won prize" if placement != ProjectPlacement.NONE else "Project submitted",
            char_start=0,
            char_end=25,
            text_fragment_url=f"{url}#:~:text=Project",
        )
        records.append(
            IdeaRecord(
                id=pid,
                name=name,
                problem=f"Problem solved by {name}",
                solution=sol,
                domain_tags=["AI", "Engineering"],
                tech_stack=["Python", "FastAPI"],
                stage=ProjectStage.PROTOTYPE,
                placement=placement,
                first_seen_url=url,
                all_source_urls=[url],
                evidence={"placement": ev},
                embedding=emb,
            )
        )
    return records


def test_originality_guardrail_similarity_and_regeneration(sample_reference_ideas):
    guardrail = OriginalityGuardrail(originality_threshold=0.80)

    # A card that is semantically similar to ref-1 ([0.9, 0.1, 0.0]) without copying verbatim text
    card = IdeaCard(
        title="HealthLens Paraphrased Concept",
        problem="Problem for healthcare",
        target_users="Clinicians",
        solution_sketch="Autonomous edge neural vision evaluating dermatological conditions on handheld cameras",
        why_now="Edge devices are fast",
        suggested_tech_stack=["Python", "PyTorch"],
        architecture_sketch="Mobile -> API -> Model",
        mvp_scope="Basic app",
        differentiation="None yet",
        novelty_score=0.1,
    )

    # Supply an embedding nearly identical to ref-1
    passed, updated_card, msg = guardrail.verify_and_guard(
        card=card,
        existing_ideas=sample_reference_ideas,
        card_embedding=[0.89, 0.11, 0.0],
    )

    assert passed is True
    assert "REFINED" in msg or "Explicit Improvement" in updated_card.solution_sketch
    assert updated_card.regeneration_notes is not None
    assert "HealthLens AI" in updated_card.regeneration_notes
    assert len(updated_card.closest_existing_projects) > 0


def test_originality_guardrail_past_winner_warning(sample_reference_ideas):
    guardrail = OriginalityGuardrail(originality_threshold=0.80)

    card = IdeaCard(
        title="Autonomous Crop Hydration Robot",
        problem="Agricultural water optimization",
        target_users="Farmers",
        solution_sketch="Ground robot carrying soil moisture sensors",
        why_now="Water scarcity",
        suggested_tech_stack=["ROS", "FastAPI", "Flutter"],
        architecture_sketch="Rover -> Gateway -> Cloud",
        mvp_scope="24h prototype",
        differentiation="Ground-based rather than drone-based",
        inspirations=[
            IdeaInspiration(
                project_id="ref-5",  # AgriDrone Fleet is a WINNER
                project_name="AgriDrone Fleet",
                source_url="https://devpost.com/software/agridrone",
                verified_location="https://devpost.com/software/agridrone#:~:text=Project",
                key_takeaway="Adapted multispectral sensor design to ground rover",
                was_winner=True,
            ),
            IdeaInspiration(
                project_id="ref-3",
                project_name="CodeBuddy CLI",
                source_url="https://github.com/codebuddy/cli",
                key_takeaway="CLI setup",
                was_winner=False,
            ),
        ],
    )

    passed, updated_card, msg = guardrail.verify_and_guard(
        card=card,
        existing_ideas=sample_reference_ideas,
        card_embedding=[0.0, 0.0, 1.0],  # Novel embedding
    )

    assert passed is True
    assert updated_card.past_winner_rules_warning is not None
    assert "EVENT RULE WARNING" in updated_card.past_winner_rules_warning
    assert "AgriDrone Fleet" in updated_card.past_winner_rules_warning
    assert updated_card.inspirations[0].winner_warning is not None


def test_originality_guardrail_verbatim_phrase_rejection(sample_reference_ideas):
    guardrail = OriginalityGuardrail()

    # Create a card copying exact >40 character verbatim solution from ref-1
    # ref-1 solution: "Computer vision model detecting skin anomalies" (46 chars)
    verbatim_text = "Computer vision model detecting skin anomalies"
    card = IdeaCard(
        title="Plagiarized Skin App",
        problem="Skin issues",
        target_users="Patients",
        solution_sketch=f"We built a {verbatim_text} without changing anything.",
        why_now="Now",
        suggested_tech_stack=["Python"],
        architecture_sketch="App -> Server",
        mvp_scope="Demo",
        differentiation="None",
    )

    passed, _, msg = guardrail.verify_and_guard(
        card=card,
        existing_ideas=sample_reference_ideas,
    )

    assert passed is False
    assert "REJECTED: Verbatim phrase copy detected" in msg


@pytest.mark.asyncio
async def test_idea_generator_agent_synthesis(sample_reference_ideas):
    generator = IdeaGeneratorAgent()
    brief = IdeaBrief(
        problem_statement="Automated defect detection on solar farm infrastructure",
        domain="Clean Energy / Robotics",
        constraints={
            "stack": ["FastAPI", "Flutter", "LangGraph"],
            "team_size": 3,
            "time_limit": "24-hour hackathon",
            "target_event": "HackCleanTech 2026",
        },
        num_cards=5,
    )

    cards = await generator.generate_cards(
        brief=brief,
        reference_ideas=sample_reference_ideas,
    )

    assert len(cards) == 5
    for card in cards:
        assert isinstance(card.title, str)
        assert len(card.title) > 0
        assert card.novelty_score > 0.0
        assert card.originality_verified is True
        assert len(card.risks) >= 1
        assert "FastAPI" in card.suggested_tech_stack
        assert "24-hour" in card.mvp_scope or "24h" in card.mvp_scope or "MVP Scope" in card.mvp_scope

        # Verify inspirations constraint: 3 to 8 inspirations with locations
        assert 3 <= len(card.inspirations) <= 8
        for insp in card.inspirations:
            assert insp.source_url.startswith("http")
            assert insp.verified_location is not None
            assert len(insp.key_takeaway) > 0


def test_multi_format_exports(sample_reference_ideas):
    generator = IdeaGeneratorAgent()
    brief = IdeaBrief(
        problem_statement="Decentralized emergency dispatch coordination",
        domain="Public Safety",
        constraints={"stack": ["FastAPI", "React"], "time_limit": "36 hours"},
        num_cards=3,
    )

    # Create 3 cards
    import asyncio
    cards = asyncio.run(generator.generate_cards(brief, sample_reference_ideas))

    # 1. Markdown Export
    md = export_cards_to_markdown(cards, brief)
    assert "# Idea Miner: Evidence-Grounded Idea Portfolio" in md
    assert "Decentralized emergency dispatch coordination" in md
    assert "Verified Inspirations" in md
    assert "Novelty Score" in md

    # 2. JSON Export
    json_str = export_cards_to_json(cards)
    assert '"title":' in json_str
    assert '"novelty_score":' in json_str

    # 3. CSV Export
    csv_str = export_cards_to_csv(cards)
    assert "title,target_users,novelty_score" in csv_str
    assert len(csv_str.strip().split("\n")) == 4  # Header + 3 cards

    # 4. PPTX Export
    pptx_bytes = export_cards_to_pptx(cards, title="Emergency Dispatch Pitch Deck")
    assert isinstance(pptx_bytes, bytes)
    assert len(pptx_bytes) > 1000

    # Parse with python-pptx to verify strict layout checks
    prs = Presentation(io.BytesIO(pptx_bytes))
    # Title slide + 3 cards = 4 slides
    assert len(prs.slides) == 4

    # Verify max 5 bullets and no empty placeholders on content slides
    for slide in list(prs.slides)[1:]:
        assert slide.shapes.title.text.strip() != ""
        # Check text shapes
        for shape in slide.shapes:
            if shape.has_text_frame:
                paragraphs = [p.text.strip() for p in shape.text_frame.paragraphs if p.text.strip()]
                assert len(paragraphs) <= 5
                # Verify zero empty shapes
                assert shape.text_frame.text.strip() != ""
