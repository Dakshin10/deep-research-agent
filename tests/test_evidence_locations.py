from __future__ import annotations

import io
import pytest

from core.fetch.base import FetchedDocument, DocumentSection, DocumentPage
from core.fetch.location import (
    generate_text_fragment_url,
    verify_excerpt_in_document,
)
from core.guardrails.citation_gate import CitationGate
from core.state.schemas import ResearchNote, PlanTask, EventType
from core.state.store import StateStore
from core.agents.worker import ResearcherWorker
from core.agents.writer import WriterAgent
from core.tools.fetch import PageFetchService


def test_text_fragment_url_generation():
    url = "https://example.com/reports/ai-market"
    short_excerpt = "Global AI spend tripled"
    frag1 = generate_text_fragment_url(url, short_excerpt)
    assert frag1.startswith("https://example.com/reports/ai-market#:~:text=")
    assert "Global%20AI%20spend%20tripled" in frag1

    long_excerpt = "Enterprises are adopting open-weights generative models for data governance reasons while maintaining high benchmark accuracy."
    frag2 = generate_text_fragment_url(url, long_excerpt)
    assert "#:~:text=" in frag2
    assert "," in frag2  # uses start and end boundary phrases


def test_exact_and_fuzzy_excerpt_verification():
    raw_text = (
        "Market Research 2026\n"
        "### Enterprise Pricing\n"
        "The Enterprise plan costs $499 per seat per year and includes 24/7 dedicated support.\n"
    )
    section = DocumentSection(
        heading_path=["Enterprise Pricing"],
        char_start=21,
        char_end=len(raw_text),
        text="The Enterprise plan costs $499 per seat per year and includes 24/7 dedicated support.",
    )
    doc = FetchedDocument(
        url="https://saas-pricing.com/plans",
        final_url="https://saas-pricing.com/plans",
        status=200,
        content_type="text/html",
        title="SaaS Plans",
        raw_text=raw_text,
        sections=[section],
    )

    # 1. Exact match
    exact_excerpt = "The Enterprise plan costs $499 per seat per year"
    verified, start, end, page, headings, frag = verify_excerpt_in_document(exact_excerpt, doc)
    assert verified is True
    assert start is not None and end is not None
    assert raw_text[start:end] == exact_excerpt
    assert headings == ["Enterprise Pricing"]
    assert "#:~:text=" in frag

    # 2. Fuzzy match with multiple spaces and unicode variations
    fuzzy_excerpt = "The   Enterprise plan costs   $499 per seat"
    verified2, start2, end2, page2, headings2, frag2 = verify_excerpt_in_document(fuzzy_excerpt, doc)
    assert verified2 is True
    assert headings2 == ["Enterprise Pricing"]

    # 3. Fabricated excerpt (Hallucination)
    fake_excerpt = "Enterprise tier costs $10,000 per month and includes private helicopter rides."
    verified3, start3, end3, page3, headings3, frag3 = verify_excerpt_in_document(fake_excerpt, doc)
    assert verified3 is False
    assert start3 is None


def test_pdf_page_resolution_in_verification():
    raw_text = "[Page 1]\nIntro to system.\n\n[Page 2]\nCritical finding: Latency dropped by 45%.\n\n"
    page1 = DocumentPage(page_no=1, char_start=0, char_end=27, text="Intro to system.")
    page2 = DocumentPage(page_no=2, char_start=27, char_end=len(raw_text), text="Critical finding: Latency dropped by 45%.")

    doc = FetchedDocument(
        url="https://arxiv.org/pdf/2601.1234.pdf",
        final_url="https://arxiv.org/pdf/2601.1234.pdf",
        status=200,
        content_type="application/pdf",
        title="Research Paper",
        raw_text=raw_text,
        pages=[page1, page2],
    )

    excerpt = "Latency dropped by 45%"
    verified, start, end, page_no, headings, frag = verify_excerpt_in_document(excerpt, doc)
    assert verified is True
    assert page_no == 2


@pytest.mark.asyncio
async def test_worker_drops_unverified_note_and_emits_event():
    store = StateStore(tenant_id="tenant_loc_test")
    await store.init_db()

    job_id = "job_test_worker_verification"
    task = PlanTask(task_id="t1", entity="FakeCorp", objective="pricing")

    worker = ResearcherWorker(
        worker_id="w1",
        tenant_id="tenant_loc_test",
        state_store=store,
    )

    doc = FetchedDocument(
        url="https://fakecorp.com/about",
        final_url="https://fakecorp.com/about",
        status=200,
        content_type="text/html",
        raw_text="FakeCorp builds cloud widgets for developers.",
    )

    # Note with hallucinated excerpt
    bad_note = ResearchNote(
        job_id=job_id,
        tenant_id="tenant_loc_test",
        claim="FakeCorp pricing starts at $9999",
        source_type="web",
        source_url="https://fakecorp.com/about",
        excerpt="FakeCorp costs $9999 per month with infinite bandwidth.",
        task_id="t1",
    )

    saved = await worker._verify_and_save_note(bad_note, job_id, task, doc=doc)
    assert saved is None  # Dropped!

    notes = await store.get_notes(job_id)
    assert len(notes) == 0

    events = await store.get_events(job_id)
    rejected_events = [e for e in events if e.event_type == EventType.NOTE_REJECTED]
    assert len(rejected_events) == 1
    assert rejected_events[0].payload["url"] == "https://fakecorp.com/about"


def test_citation_gate_enforces_verified_locations():
    # Note with verified location
    note_verified = "note_ver1"
    # Note without verified location
    note_unverified = "note_unver2"

    locations = {
        note_verified: True,
        note_unverified: False,
    }
    gate = CitationGate(
        valid_note_ids={note_verified, note_unverified},
        note_locations=locations,
        strict=True,
    )

    # Valid quantitative claim with verified location note
    text_good = f"Market share increased by 35% in Q3 [{note_verified}]."
    res_good = gate.evaluate(text_good)
    assert res_good.passed is True
    assert len(res_good.flagged_issues) == 0

    # Quantitative claim with unverified note -> must be flagged
    text_bad = f"Market share increased by 35% in Q3 [{note_unverified}]."
    res_bad = gate.evaluate(text_bad)
    assert res_bad.passed is False
    assert len(res_bad.flagged_issues) == 1
    assert "verified document location" in res_bad.flagged_issues[0].reason


@pytest.mark.asyncio
async def test_writer_renders_human_readable_locations():
    store = StateStore(tenant_id="tenant_writer_test")
    await store.init_db()

    job_id = "job_writer_test_loc"
    note = ResearchNote(
        id="note_test123",
        job_id=job_id,
        tenant_id="tenant_writer_test",
        claim="CloudWidget delivers 99.99% SLA availability",
        source_type="web",
        source_url="https://cloudwidget.io/pricing",
        excerpt="We guarantee 99.99% SLA uptime for all enterprise instances.",
        task_id="task_1",
        heading_path=["Pricing", "Enterprise SLA"],
        page_no=None,
        char_start=120,
        char_end=180,
        text_fragment_url="https://cloudwidget.io/pricing#:~:text=We%20guarantee,enterprise%20instances",
        is_verified=True,
    )

    writer = WriterAgent(tenant_id="tenant_writer_test", state_store=store)
    report = await writer.write_report(
        job_id=job_id,
        query="CloudWidget availability",
        brief=None,
        notes=[note],
    )

    assert "Pricing > Enterprise SLA" in report
    assert "offsets 120-180" in report
    assert "[note_test123]" in report
    assert "#:~:text=" in report
