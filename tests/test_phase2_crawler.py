from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import os
from pathlib import Path
import pytest
from httpx import AsyncClient, ASGITransport

from apps.api.main import app
from core.crawl.engine import CrawlEngine
from core.crawl.schemas import (
    CrawlEvent,
    CrawlMode,
    CrawlRunConfig,
    FrontierItem,
    FrontierState,
)
from core.crawl.storage import RawDocumentStore
from core.crawl.store import CrawlStore
from core.fetch.base import FetchedDocument
from core.sources.policy import SourcePolicyEngine
from core.sources.registry import SourceRegistry


@pytest.mark.asyncio
async def test_crawl_frontier_idempotent_insert_and_claiming(tmp_path):
    """Test that frontier insertion is idempotent and items are claimed in priority order."""
    store = CrawlStore(db_url="sqlite+aiosqlite:///:memory:")
    await store.init_db()

    items = [
        FrontierItem(
            id="item_1",
            url="https://devpost.com/software/ai-doc-search",
            canonical_url="https://devpost.com/software/ai-doc-search",
            source="devpost",
            priority=10,
        ),
        FrontierItem(
            id="item_2",
            url="https://devpost.com/software/super-health",
            canonical_url="https://devpost.com/software/super-health",
            source="devpost",
            priority=25,  # Higher priority
        ),
    ]

    # Initial insertion
    added = await store.add_frontier_items(items)
    assert added == 2

    # Duplicate insertion: same (source, canonical_url) should not duplicate
    dup_added = await store.add_frontier_items(items)
    assert dup_added == 0

    # Claim items: item_2 has priority 25, should be first
    claimed = await store.claim_frontier_items(batch_size=1, source="devpost")
    assert len(claimed) == 1
    assert claimed[0].canonical_url == "https://devpost.com/software/super-health"
    assert claimed[0].state == FrontierState.RUNNING
    assert claimed[0].attempts == 1

    # Claim remaining item
    claimed_2 = await store.claim_frontier_items(batch_size=5, source="devpost")
    assert len(claimed_2) == 1
    assert claimed_2[0].canonical_url == "https://devpost.com/software/ai-doc-search"


@pytest.mark.asyncio
async def test_resumable_crawl_after_simulated_crash(tmp_path, monkeypatch):
    """Test that if a crawl is interrupted, a second run resumes pending frontier items."""
    db_file = tmp_path / "resume_crawl.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"

    store = CrawlStore(db_url=db_url)
    await store.init_db()

    # Pre-populate frontier with 3 items
    urls = [
        "https://devpost.com/software/proj-a",
        "https://devpost.com/software/proj-b",
        "https://devpost.com/software/proj-c",
    ]
    items = [
        FrontierItem(
            id=f"item_{i}",
            url=u,
            canonical_url=u,
            source="devpost",
            priority=10,
        )
        for i, u in enumerate(urls)
    ]
    await store.add_frontier_items(items)

    doc_store = RawDocumentStore(base_dir=str(tmp_path / "docs"))

    # Mock HTTP client to succeed on all requests
    class MockResponse:
        def __init__(self, url):
            self.status_code = 200
            self.url = url
            self.text = "<html><body><h1 id=\"app-title\">Test Project</h1><p class=\"large\">Description</p></body></html>"
            self.content = self.text.encode("utf-8")
            self.headers = {"content-type": "text/html", "etag": "etag-123"}

    class MockClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, url, headers=None, **kwargs):
            return MockResponse(url)

    monkeypatch.setattr("httpx.AsyncClient", MockClient)

    # First run: limit to 2 pages (simulating early termination / crash)
    engine = CrawlEngine(store=store, doc_store=doc_store)
    cfg1 = CrawlRunConfig(source="devpost", mode=CrawlMode.FETCH, limit_pages=2)
    run1 = await engine.run(cfg1)
    assert run1.pages_crawled == 2

    # Second run: resumes remaining pending item
    cfg2 = CrawlRunConfig(source="devpost", mode=CrawlMode.FETCH, limit_pages=5)
    run2 = await engine.run(cfg2)
    assert run2.pages_crawled == 1  # Processed the 3rd remaining item!


@pytest.mark.asyncio
async def test_incremental_refresh_skips_unchanged_pages(tmp_path, monkeypatch):
    """Test that refresh mode skips pages that return 304 or matching content_hash."""
    store = CrawlStore(db_url="sqlite+aiosqlite:///:memory:")
    await store.init_db()
    doc_store = RawDocumentStore(base_dir=str(tmp_path / "docs"))

    # Pre-populate frontier with an item that has last_etag and content_hash
    test_content = "<html>Existing content</html>"
    import hashlib
    content_hash = hashlib.sha256(test_content.encode("utf-8")).hexdigest()

    item = FrontierItem(
        id="item_refresh_1",
        url="https://devpost.com/software/unchanged-app",
        canonical_url="https://devpost.com/software/unchanged-app",
        source="devpost",
        last_etag='"etag-xyz"',
        content_hash=content_hash,
    )
    await store.add_frontier_items([item])

    # Mock 304 response
    class Mock304Response:
        status_code = 304
        headers = {}
        content = b""
        text = ""

    class Mock304Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, url, headers=None, **kwargs):
            assert headers.get("If-None-Match") == '"etag-xyz"'
            return Mock304Response()

    monkeypatch.setattr("httpx.AsyncClient", Mock304Client)

    events_captured = []
    engine = CrawlEngine(store=store, doc_store=doc_store)

    async def capture():
        async for evt in store.subscribe_events("crawl_test_refresh"):
            events_captured.append(evt)

    cfg = CrawlRunConfig(source="devpost", mode=CrawlMode.REFRESH, limit_pages=5)
    run = await engine.run(cfg)

    assert run.pages_skipped == 1
    assert run.pages_crawled == 0


@pytest.mark.asyncio
async def test_source_policy_and_robots_compliance(tmp_path, monkeypatch):
    """Test that disallowed domains are blocked and robots.txt denials are respected."""
    store = CrawlStore(db_url="sqlite+aiosqlite:///:memory:")
    await store.init_db()
    doc_store = RawDocumentStore(base_dir=str(tmp_path / "docs"))

    # Insert one denied domain and one robots-denied URL
    items = [
        FrontierItem(
            id="item_denied",
            url="https://linkedin.com/in/startup-founder",
            canonical_url="https://linkedin.com/in/startup-founder",
            source="linkedin",
        ),
        FrontierItem(
            id="item_robots_blocked",
            url="https://devpost.com/private/secret-page",
            canonical_url="https://devpost.com/private/secret-page",
            source="devpost",
        ),
    ]
    await store.add_frontier_items(items)

    engine = CrawlEngine(store=store, doc_store=doc_store)

    # Mock robots cache to reject private/secret-page
    async def mock_is_allowed(url, client=None):
        if "secret-page" in url:
            return False
        return True

    monkeypatch.setattr(engine.robots, "is_allowed", mock_is_allowed)

    cfg = CrawlRunConfig(source="devpost", mode=CrawlMode.FETCH, limit_pages=5)
    run = await engine.run(cfg)

    # Secret page was blocked by robots.txt
    assert run.pages_crawled == 0


@pytest.mark.asyncio
async def test_raw_document_store_compression_and_retrieval(tmp_path):
    """Test storing raw document in gzip format and retrieving it verbatim."""
    doc_store = RawDocumentStore(base_dir=str(tmp_path / "raw_docs"))

    url = "https://devpost.com/software/smart-traffic"
    html_content = "<html><head><title>Smart Traffic</title></head><body><h1>Traffic AI</h1></body></html>"

    content_hash, path = doc_store.store_document(
        url=url,
        content=html_content,
        content_type="text/html",
        metadata={"hackathon": "CalHacks 2024"},
    )

    assert os.path.exists(path)
    assert doc_store.has_document(content_hash) is True

    # Retrieve and verify content
    raw_bytes, meta = doc_store.get_document(content_hash)
    assert raw_bytes.decode("utf-8") == html_content
    assert meta["url"] == url
    assert meta["metadata"]["hackathon"] == "CalHacks 2024"


@pytest.mark.asyncio
async def test_crawl_api_endpoints(tmp_path, monkeypatch):
    """Test POST /v1/crawl/runs and GET /v1/crawl/runs endpoints."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Mock background run so it doesn't do real external requests
        async def dummy_run(*args, **kwargs):
            return None

        monkeypatch.setattr(CrawlEngine, "run", dummy_run)

        payload = {
            "source": "devpost",
            "mode": "discover",
            "limit_pages": 50,
            "since_date": "2023",
        }

        # 1. Start crawl run
        post_resp = await client.post("/v1/crawl/runs", json=payload)
        assert post_resp.status_code == 200
        run_data = post_resp.json()
        run_id = run_data["id"]
        assert run_data["source"] == "devpost"
        assert run_data["limit_pages"] == 50

        # 2. Get crawl run status
        get_resp = await client.get(f"/v1/crawl/runs/{run_id}")
        assert get_resp.status_code == 200
        status_data = get_resp.json()
        assert status_data["id"] == run_id

        # 3. List crawl runs
        list_resp = await client.get("/v1/crawl/runs")
        assert list_resp.status_code == 200
        runs_list = list_resp.json()
        assert any(r["id"] == run_id for r in runs_list)
