from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import pytest

from core.fetch.base import FetchedDocument
from core.ideas.extractor import IdeaExtractor, RawIdeaExtraction
from core.ideas.privacy import PrivacyScrubber
from core.ideas.resolver import EntityResolver
from core.ideas.schemas import (
    EvidenceEntry,
    IdeaRecord,
    ProjectPlacement,
    ProjectStage,
)
from core.ideas.store import IdeaStore
from core.sources.schemas import ProjectPlacement as SourcePlacement, RawProject, SourceKind


@pytest.mark.asyncio
async def test_verbatim_evidence_verification_and_field_rejection():
    """
    HARD RULE Test:
    Verifies that claims backed by verbatim document text are accepted with exact offsets,
    while fabricated claims (like fake prizes or placements) are dropped to null/none
    and emit a 'field_rejected' event.
    """
    raw_html_text = (
        "Project NeuroFlow is an AI-powered EEG analysis platform for clinical diagnostics. "
        "The problem is that neurologists spend 4 hours analyzing 24-hour ambulatory EEG recordings. "
        "Our solution uses deep convolutional networks to detect focal epileptiform discharges in seconds. "
        "Built with PyTorch, FastAPI, and Next.js. Team size: 4 engineers."
    )

    doc = FetchedDocument(
        url="https://devpost.com/software/neuroflow",
        final_url="https://devpost.com/software/neuroflow",
        status=200,
        content_type="text/html",
        raw_text=raw_html_text,
    )

    raw_project = RawProject(
        source_id="devpost",
        source_domain="devpost.com",
        source_url="https://devpost.com/software/neuroflow",
        name="NeuroFlow",
        tagline="AI-powered EEG analysis platform",
        description_raw="The problem is that neurologists spend 4 hours analyzing 24-hour ambulatory EEG recordings.\n\nOur solution uses deep convolutional networks to detect focal epileptiform discharges in seconds.",
        authors=["Alice", "Bob", "Charlie", "Dave"],
        tags=["PyTorch", "FastAPI", "Next.js", "Healthcare", "AI"],
        placement=SourcePlacement.WINNER,
        prize_name="Grand Prize Winner - $100,000",  # FABRICATED: NOT in raw_html_text!
        links={"demo": "https://neuroflow.ai", "repo": "https://github.com/neuroflow/neuroflow"},
    )

    rejected_events = []

    def on_event(event_type: str, payload: dict):
        if event_type == "field_rejected":
            rejected_events.append(payload)

    extractor = IdeaExtractor()
    record = await extractor.extract(
        doc=doc,
        raw_project=raw_project,
        on_event=on_event,
    )

    # 1. Valid fields are verified with exact offsets
    assert record.name == "NeuroFlow"
    assert "problem" in record.evidence
    ev_prob = record.evidence["problem"]
    assert ev_prob.verified is True
    assert ev_prob.char_start is not None
    assert ev_prob.char_end is not None
    assert "neurologists spend 4 hours" in raw_html_text[ev_prob.char_start:ev_prob.char_end]

    # 2. Fabricated prize was NOT in raw_text -> dropped and rejected!
    assert record.placement == ProjectPlacement.NONE
    rejected_fields = [e["field"] for e in rejected_events]
    assert "placement" in rejected_fields


@pytest.mark.asyncio
async def test_privacy_scrubbing():
    """Test that emails, phone numbers, and private handles are scrubbed."""
    scrubber = PrivacyScrubber()

    raw_text = "Contact founder at alex.dev@startup.io or call +1-415-555-0199 for investment."
    scrubbed = scrubber.scrub_text(raw_text)
    assert "alex.dev@startup.io" not in scrubbed
    assert "+1-415-555-0199" not in scrubbed
    assert "[REDACTED_EMAIL]" in scrubbed
    assert "[REDACTED_PHONE]" in scrubbed

    # Test link scrubbing (strip private social handles)
    links = {
        "demo": "https://demo.app.io",
        "repo": "https://github.com/org/repo",
        "facebook": "https://facebook.com/personal_profile_123",
        "linkedin": "https://linkedin.com/in/secret-founder",
    }
    clean_links = scrubber.scrub_links(links)
    assert "demo" in clean_links
    assert "repo" in clean_links
    assert "facebook" not in clean_links
    assert "linkedin" not in clean_links


@pytest.mark.asyncio
async def test_entity_resolution_and_lossless_unmerge():
    """Test duplicate detection, merging, and lossless unmerge with audit trail."""
    resolver = EntityResolver()

    # Record A from Devpost
    rec_a = IdeaRecord(
        id="idea_devpost_1",
        name="AgentBench",
        one_liner="Benchmarking autonomous coding agents",
        problem="Evaluating LLM agents lacks standardized benchmarks",
        tech_stack=["Python", "LangGraph"],
        domain_tags=["AI", "Developer Tools"],
        links={"repo": "https://github.com/benchmark-org/agentbench", "demo": "https://agentbench.ai"},
        first_seen_url="https://devpost.com/software/agentbench",
        all_source_urls=["https://devpost.com/software/agentbench"],
    )

    # Record B from GitHub
    rec_b = IdeaRecord(
        id="idea_github_1",
        name="AgentBench Official",
        one_liner="Official repo for AgentBench framework",
        solution="A benchmark harness measuring SWE-bench task completion",
        tech_stack=["Python", "Docker", "Pytest"],
        domain_tags=["AI", "Evaluation"],
        links={"repo": "https://github.com/benchmark-org/agentbench"},
        first_seen_url="https://github.com/benchmark-org/agentbench",
        all_source_urls=["https://github.com/benchmark-org/agentbench"],
    )

    # 1. Evaluate merge candidate: shared repo URL
    should_merge, reason, confidence = resolver.evaluate_merge_candidate(rec_a, rec_b)
    assert should_merge is True
    assert reason == "shared_repository_url"
    assert confidence == 1.0

    # 2. Merge B into A
    merged = resolver.merge(rec_a, rec_b, reason=reason)
    assert len(merged.all_source_urls) == 2
    assert "https://github.com/benchmark-org/agentbench" in merged.all_source_urls
    assert "https://devpost.com/software/agentbench" in merged.all_source_urls
    assert "Docker" in merged.tech_stack
    assert "LangGraph" in merged.tech_stack
    assert len(merged.merge_history) == 1
    assert rec_b.merged_into_id == rec_a.id

    # 3. Un-merge B from A
    surviving, restored = resolver.unmerge(merged, merged_id=rec_b.id)
    assert restored is not None
    assert restored.id == rec_b.id
    assert restored.merged_into_id is None
    assert len(surviving.merge_history) == 0


@pytest.mark.asyncio
async def test_hybrid_idea_search_and_filtering():
    """Test pgvector hybrid search and metadata filtering in IdeaStore."""
    store = IdeaStore(db_url="sqlite+aiosqlite:///:memory:")
    await store.init_db()

    # Create 3 records
    r1 = IdeaRecord(
        id="idea_med_1",
        name="CardioScan AI",
        one_liner="Ultrasound cardiac anomaly detection",
        problem="Rural clinics lack specialized cardiologists to read echocardiograms",
        solution="Mobile edge AI detects valve disease from handheld probes",
        tech_stack=["TensorFlow", "Flutter", "FastAPI"],
        domain_tags=["Healthcare", "Cardiology"],
        year=2024,
        placement=ProjectPlacement.WINNER,
        first_seen_url="https://devpost.com/software/cardioscan",
        all_source_urls=["https://devpost.com/software/cardioscan"],
    )
    r1.embedding = store.embedder.embed_text(r1.canonical_text())
    await store.save_idea(r1)

    r2 = IdeaRecord(
        id="idea_fin_1",
        name="FraudSentinel",
        one_liner="Real-time transaction anomaly radar",
        problem="Fintechs lose billions to synthetic identity fraud",
        solution="Graph neural networks analyze cross-account money flows",
        tech_stack=["Neo4j", "PyTorch", "Kafka"],
        domain_tags=["Fintech", "Security"],
        year=2023,
        placement=ProjectPlacement.FINALIST,
        first_seen_url="https://devpost.com/software/fraudsentinel",
        all_source_urls=["https://devpost.com/software/fraudsentinel"],
    )
    r2.embedding = store.embedder.embed_text(r2.canonical_text())
    await store.save_idea(r2)

    # Semantic search for cardiac medical solution
    hits = await store.search_ideas("echocardiogram ultrasound cardiac analysis")
    assert len(hits) >= 1
    assert hits[0].name == "CardioScan AI"

    # Filtered search: year=2024, placement=winner
    winner_hits = await store.search_ideas("AI", filters={"year": 2024, "placement": "winner"})
    assert len(winner_hits) == 1
    assert winner_hits[0].id == "idea_med_1"


@pytest.mark.asyncio
async def test_tenant_isolation_on_private_ideas():
    """Test multi-tenant RLS isolation on private idea records."""
    store_a = IdeaStore(tenant_id="tenant_alpha", db_url="sqlite+aiosqlite:///:memory:")
    await store_a.init_db()

    # Public record (tenant_id = None)
    pub = IdeaRecord(
        id="idea_public_1",
        tenant_id=None,
        name="Public Open Project",
        first_seen_url="https://github.com/public/project",
    )
    await store_a.save_idea(pub)

    # Private record for Tenant Alpha
    priv_a = IdeaRecord(
        id="idea_private_alpha",
        tenant_id="tenant_alpha",
        name="Confidential Internal Spin-off",
        first_seen_url="https://internal.alpha.corp/project",
    )
    await store_a.save_idea(priv_a)

    # Store for Tenant Beta sharing same db engine
    store_b = IdeaStore(tenant_id="tenant_beta", session_factory=store_a._session_factory)

    # Tenant Beta can see public record
    hit_pub = await store_b.get_idea("idea_public_1")
    assert hit_pub is not None

    # Tenant Beta CANNOT see Tenant Alpha's private record (zero leakage)
    hit_priv = await store_b.get_idea("idea_private_alpha")
    assert hit_priv is None
