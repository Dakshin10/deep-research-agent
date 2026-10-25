import json
import pytest
from httpx import AsyncClient, ASGITransport

from apps.api.main import app
from core.ideas.schemas import IdeaRecord, ProjectPlacement, ProjectStage, EvidenceEntry
from core.ideas.store import IdeaStore
from core.observability.tracing import record_crawl_span, record_extraction_batch_span


@pytest.fixture
async def setup_test_ideas():
    store = IdeaStore(db_url="sqlite+aiosqlite:///:memory:")
    await store.init_db()

    # Seed 3 test records
    ev = EvidenceEntry(
        field="placement",
        url="https://devpost.com/software/neuro-lens",
        excerpt="1st Place Medical Innovation",
        char_start=0,
        char_end=30,
        text_fragment_url="https://devpost.com/software/neuro-lens#:~:text=1st",
    )
    r1 = IdeaRecord(
        id="idea-api-1",
        name="NeuroLens Vision",
        problem="Glaucoma progression detection in rural clinics",
        solution="Edge camera with embedded PyTorch classification",
        domain_tags=["Healthcare", "AI"],
        tech_stack=["Python", "PyTorch", "FastAPI"],
        stage=ProjectStage.PROTOTYPE,
        placement=ProjectPlacement.WINNER,
        first_seen_url="https://devpost.com/software/neuro-lens",
        evidence={"placement": ev},
        embedding=[0.9, 0.1, 0.0],
    )
    r2 = IdeaRecord(
        id="idea-api-2",
        name="GridDefend Cyber",
        problem="SCADA network anomaly defense",
        solution="Rust packet inspector with eBPF hooks",
        domain_tags=["Security", "Infrastructure"],
        tech_stack=["Rust", "eBPF", "Linux"],
        stage=ProjectStage.LAUNCHED,
        placement=ProjectPlacement.RUNNER_UP,
        first_seen_url="https://github.com/griddefend/core",
        embedding=[0.1, 0.9, 0.0],
    )
    r3 = IdeaRecord(
        id="idea-api-3",
        name="Simple Habit Bot",
        problem="Habit reminder ping",
        solution="Telegram chatbot script",
        domain_tags=["Productivity"],
        tech_stack=["Python"],
        stage=ProjectStage.IDEA,
        placement=ProjectPlacement.NONE,
        first_seen_url="https://github.com/habit/bot",
        embedding=[0.0, 0.0, 0.9],
    )

    await store.upsert_idea(r1)
    await store.upsert_idea(r2)
    await store.upsert_idea(r3)
    return store


@pytest.mark.asyncio
async def test_ideas_search_and_get_api(setup_test_ideas):
    from apps.api.main import get_idea_store
    app.dependency_overrides[get_idea_store] = lambda: setup_test_ideas

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Search with filter
        resp = await client.post(
            "/v1/ideas/search",
            json={"query": "NeuroLens", "limit": 10},
            headers={"X-Tenant-ID": "test-tenant"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert data[0]["name"] == "NeuroLens Vision"
        assert "evidence" in data[0]

        # 2. Get by ID
        resp2 = await client.get(
            "/v1/ideas/idea-api-1",
            headers={"X-Tenant-ID": "test-tenant"},
        )
        assert resp2.status_code == 200
        assert resp2.json()["id"] == "idea-api-1"
        assert resp2.json()["placement"] == "winner"

        # 3. 404 for missing
        resp3 = await client.get(
            "/v1/ideas/non-existent-id",
            headers={"X-Tenant-ID": "test-tenant"},
        )
        assert resp3.status_code == 404

    app.dependency_overrides.pop(get_idea_store, None)


@pytest.mark.asyncio
async def test_ideas_clusters_and_trends_api(setup_test_ideas):
    from apps.api.main import get_idea_store
    app.dependency_overrides[get_idea_store] = lambda: setup_test_ideas

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Clusters
        c_resp = await client.get("/v1/ideas/clusters", headers={"X-Tenant-ID": "test-tenant"})
        assert c_resp.status_code == 200
        c_data = c_resp.json()
        assert "clusters" in c_data
        assert c_data["sample_size"] == 3

        # Trends
        t_resp = await client.get("/v1/ideas/trends", headers={"X-Tenant-ID": "test-tenant"})
        assert t_resp.status_code == 200
        t_data = t_resp.json()
        assert "trends" in t_data
        assert "winner_patterns" in t_data
        assert t_data["trends"]["total_ideas_analyzed"] == 3

    app.dependency_overrides.pop(get_idea_store, None)


@pytest.mark.asyncio
async def test_ideas_generate_api(setup_test_ideas):
    from apps.api.main import get_idea_store
    app.dependency_overrides[get_idea_store] = lambda: setup_test_ideas

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/v1/ideas/generate",
            json={
                "problem_statement": "Autonomous wildfire detection using thermal cameras on towers",
                "domain": "Climate & Safety",
                "constraints": {"stack": ["FastAPI", "Flutter"], "time_limit": "24h"},
                "num_cards": 3,
            },
            headers={"X-Tenant-ID": "test-tenant"},
        )
        assert resp.status_code == 200
        cards = resp.json()
        assert len(cards) == 3
        for card in cards:
            assert "title" in card
            assert card["novelty_score"] > 0.0
            assert len(card["inspirations"]) >= 1

    app.dependency_overrides.pop(get_idea_store, None)


@pytest.mark.asyncio
async def test_ideas_import_json_and_csv_api(setup_test_ideas):
    from apps.api.main import get_idea_store
    app.dependency_overrides[get_idea_store] = lambda: setup_test_ideas

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. JSON Import (denied site: LinkedIn startup post)
        json_payload = json.dumps([
            {
                "id": "imported-li-1",
                "name": "LinkedIn Stealth Startup",
                "problem": "Sales outreach optimization",
                "solution": "Agentic email personalizer",
                "tech_stack": ["Python", "FastAPI"],
                "domain_tags": ["SaaS"],
                "first_seen_url": "manual://linkedin-import",
            }
        ])
        resp1 = await client.post(
            "/v1/ideas/import",
            json={"format": "json", "data": json_payload},
            headers={"X-Tenant-ID": "test-tenant"},
        )
        assert resp1.status_code == 200
        assert resp1.json()["imported_count"] == 1

        # 2. CSV Import (denied site: Crunchbase company export)
        csv_payload = "id,name,problem,solution,tech_stack,domain_tags,first_seen_url\nimported-cb-1,Crunchbase FinTech,Payment rails,Instant ACH,Go,Finance,manual://crunchbase"
        resp2 = await client.post(
            "/v1/ideas/import",
            json={"format": "csv", "data": csv_payload},
            headers={"X-Tenant-ID": "test-tenant"},
        )
        assert resp2.status_code == 200
        assert resp2.json()["imported_count"] == 1

    app.dependency_overrides.pop(get_idea_store, None)


@pytest.mark.asyncio
async def test_sources_coverage_api():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/v1/sources/coverage")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_sources_configured"] >= 20
        assert data["allowed_sources"] > 10
        assert data["denied_sources"] >= 5  # linkedin, twitter, crunchbase, facebook, instagram

        domains = [s["domain"] for s in data["sources"]]
        assert "linkedin.com" in domains
        assert "x.com" in domains or "twitter.com" in domains
        assert "devpost.com" in domains


def test_langfuse_spans_crawl_and_extraction():
    # Crawl span
    crawl_span = record_crawl_span(
        source="devpost",
        run_id="crawl_test_123",
        pages_crawled=150,
        duration=45.0,
    )
    assert crawl_span.name == "crawl_devpost"
    assert int(crawl_span.outputs["pages_crawled"]) == 150
    assert float(crawl_span.outputs["pages_per_sec"]) > 0

    # Extraction batch span with cost per 1,000 pages
    ext_span = record_extraction_batch_span(
        source="devpost",
        batch_size=500,
        ideas_extracted=48,
        duration=12.5,
    )
    assert ext_span.name == "extract_devpost"
    assert int(ext_span.outputs["ideas_extracted"]) == 48
    assert "cost_usd" in ext_span.outputs
    assert "cost_per_1000_pages_usd" in ext_span.outputs
    # Cost per 1k pages should be reasonable (~$0.15)
    assert 0.05 <= float(ext_span.outputs["cost_per_1000_pages_usd"]) <= 0.50
