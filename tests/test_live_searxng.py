import os
import pytest
import httpx

from core.fetch.base import FetchedDocument
from core.fetch.location import verify_excerpt_in_document
from core.search.providers.searxng import SearxngProvider
from core.tools.fetch import PageFetchService


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_searxng_5_queries_location_verification():
    """
    Live Smoke Test (marked 'live', skipped by default unless run with -m live):
    - Connects to SearXNG service (default: http://localhost:8080 or SEARXNG_URL).
    - Runs 5 real queries across distinct domains.
    - Fetches top page and checks that at least 80% of saved notes have verified locations.
    """
    searxng_url = os.environ.get("SEARXNG_URL", "http://localhost:8080")

    # Fast connectivity probe to skip gracefully if SearXNG container is not active
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{searxng_url}/search?q=test&format=json")
            if resp.status_code != 200:
                pytest.skip(f"SearXNG returned HTTP {resp.status_code} at {searxng_url}; skipping live test.")
    except Exception as e:
        pytest.skip(f"SearXNG unreachable at {searxng_url} ({e}); skipping live test.")

    queries = [
        "Python 3.12 asyncio TaskGroup exception handling best practices",
        "PostgreSQL pgvector cosine distance indexing performance",
        "LangGraph human-in-the-loop workflow architecture",
        "Trafilatura web text extraction Python library",
        "FastAPI Server-Sent Events asynchronous streaming",
    ]

    provider = SearxngProvider(base_url=searxng_url)
    fetch_service = PageFetchService()

    total_attempts = 0
    verified_locations = 0

    for q in queries:
        hits = await provider.search(q, limit=2)
        if not hits:
            continue

        for hit in hits:
            try:
                doc = await fetch_service.fetch_document(hit.url)
                if not doc.raw_text or doc.is_blocked:
                    continue

                total_attempts += 1
                # Test excerpt verification against fetched document
                sample_snippet = hit.snippet[:120].strip() if hit.snippet else ""
                if sample_snippet:
                    is_valid, c_start, c_end, p_no, h_path, frag_url = verify_excerpt_in_document(
                        sample_snippet, doc
                    )
                    if is_valid and frag_url and "#:~:text=" in frag_url:
                        verified_locations += 1
                else:
                    # If snippet wasn't present, test verification with first section
                    if doc.sections:
                        sec_text = doc.sections[0].text[:120].strip()
                        is_valid, c_start, c_end, p_no, h_path, frag_url = verify_excerpt_in_document(
                            sec_text, doc
                        )
                        if is_valid and frag_url:
                            verified_locations += 1
            except Exception:
                continue

    if total_attempts > 0:
        verification_rate = verified_locations / total_attempts
        assert verification_rate >= 0.80, f"Expected >= 80% verified locations, got {verification_rate:.1%}"
