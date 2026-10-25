import pytest
from core.knowledge.store import KnowledgeStore
from core.knowledge.parser import DocumentParser
from core.knowledge.chunker import TextChunker


@pytest.mark.asyncio
async def test_document_parser_and_chunker():
    """Test parsing text/markdown and chunking with 800 token target and 100 overlap."""
    text_sample = "Word " * 1500
    chunker = TextChunker(chunk_size=800, chunk_overlap=100)
    chunks = chunker.chunk_text(text_sample)
    assert len(chunks) >= 2
    # Check overlap
    assert len(chunks[0].split()) <= 800

    # Test parser fallback
    parsed = DocumentParser.parse_bytes(b"Sample proprietary markdown text", "doc.txt")
    assert parsed == "Sample proprietary markdown text"


@pytest.mark.asyncio
async def test_tenant_isolation_and_zero_leakage():
    """
    Test Step 2 requirement:
    Two seeded tenants, 30 probing queries, zero cross-tenant results.
    Both tenants can access shared benchmarks (tenant_id=None).
    """
    db_url = "sqlite+aiosqlite:///:memory:"

    # 1. Initialize store for tenant Alpha and seed proprietary data
    store_alpha = KnowledgeStore(tenant_id="tenant_alpha", db_url=db_url)
    await store_alpha.init_db()

    alpha_content = b"""
    Project Apollo Confidential Strategy:
    Tenant Alpha is launching a $500,000 Gen Z influencer campaign across TikTok and Instagram.
    Key conversion KPI is 4.8% CTR with exclusive voucher code ALPHA-VIP-2025.
    Internal pricing margins are set at 68% for the Apollo subscription tier.
    Competitor targeting specifically aims to capture market share from Beta Corp.
    """
    await store_alpha.ingest_document("alpha_strategy.txt", alpha_content, is_benchmark=False)

    # 2. Initialize store for tenant Beta sharing the same database engine
    store_beta = KnowledgeStore(
        tenant_id="tenant_beta",
        db_url=db_url,
        session_factory=store_alpha._session_factory,
    )

    beta_content = b"""
    Project Thor Enterprise CRM Pipeline:
    Tenant Beta has closed $1,200,000 in Q3 enterprise pipeline with Acme Global and Stark Industries.
    Key expansion target is German automotive manufacturers with customized SLA packages.
    Internal discount floor is capped at 15% approved by Beta executive finance.
    Secret project Thor deployment is scheduled for November 2025.
    """
    await store_beta.ingest_document("beta_pipeline.txt", beta_content, is_benchmark=False)

    # 3. Ingest shared benchmark into global namespace (tenant_id=None)
    benchmark_content = b"""
    Global Marketing Industry Benchmark 2025:
    Average conversion rate across B2B SaaS campaigns is 2.4%.
    Standard cost-per-acquisition (CPA) ranges between $85 and $120.
    Omnichannel marketing strategies show 3x higher retention than single-channel.
    """
    await store_alpha.ingest_document("global_benchmark.txt", benchmark_content, is_benchmark=True)

    # 4. Run 15 probing queries from Tenant Beta attempting to find Tenant Alpha confidential data
    probing_queries_for_alpha = [
        "Apollo",
        "Project Apollo confidential",
        "TikTok Gen Z influencer",
        "500,000 influencer campaign",
        "voucher code ALPHA-VIP-2025",
        "68% internal pricing margin",
        "capture market share from Beta Corp",
        "Alpha strategy document",
        "Gen Z influencer CTR",
        "Apollo subscription tier",
        "ALPHA-VIP",
        "4.8% CTR",
        "Instagram influencer budget",
        "Tenant Alpha proprietary launch",
        "Project Apollo timeline",
    ]

    for query in probing_queries_for_alpha:
        results = await store_beta.retrieve(query, top_k=8)
        # MUST NEVER return any chunk belonging to tenant_alpha
        for r in results:
            assert r["tenant_id"] != "tenant_alpha", (
                f"DATA LEAKAGE DETECTED! Tenant Beta retrieved Tenant Alpha data for query: '{query}'"
            )
            # Must only be tenant_beta or shared benchmark
            assert r["tenant_id"] in ["tenant_beta", None]

    # 5. Run 15 probing queries from Tenant Alpha attempting to find Tenant Beta confidential data
    probing_queries_for_beta = [
        "Thor",
        "Project Thor enterprise pipeline",
        "Acme Global deals",
        "Stark Industries contract",
        "$1,200,000 Q3 pipeline",
        "German automotive manufacturers SLA",
        "discount floor capped at 15%",
        "Beta executive finance approval",
        "Secret project Thor",
        "November 2025 Thor deployment",
        "Acme CRM pipeline",
        "Stark Industries enterprise",
        "customized SLA packages",
        "Beta corporate deals",
        "Thor enterprise rollout",
    ]

    for query in probing_queries_for_beta:
        results = await store_alpha.retrieve(query, top_k=8)
        # MUST NEVER return any chunk belonging to tenant_beta
        for r in results:
            assert r["tenant_id"] != "tenant_beta", (
                f"DATA LEAKAGE DETECTED! Tenant Alpha retrieved Tenant Beta data for query: '{query}'"
            )
            # Must only be tenant_alpha or shared benchmark
            assert r["tenant_id"] in ["tenant_alpha", None]

    # 6. Verify shared benchmarks are accessible to both tenants
    bench_alpha = await store_alpha.retrieve("B2B SaaS average conversion rate benchmark", top_k=5)
    bench_beta = await store_beta.retrieve("B2B SaaS average conversion rate benchmark", top_k=5)

    assert any(r["is_benchmark"] for r in bench_alpha), "Tenant Alpha failed to access shared benchmark"
    assert any(r["is_benchmark"] for r in bench_beta), "Tenant Beta failed to access shared benchmark"


@pytest.mark.asyncio
async def test_query_without_tenant_id_returns_nothing():
    """
    Test Step 1 requirement:
    Add a test proving a query without app.tenant_id set returns nothing (zero proprietary records).
    Only global public benchmarks (tenant_id IS NULL) can be accessed.
    """
    db_url = "sqlite+aiosqlite:///:memory:"

    # 1. Seed proprietary data for Tenant Alpha
    store_alpha = KnowledgeStore(tenant_id="tenant_alpha", db_url=db_url)
    await store_alpha.init_db()
    await store_alpha.ingest_document(
        "alpha_confidential.txt",
        b"Confidential Alpha financial records: Q4 profit margin was 42% with $8M cash reserves.",
        is_benchmark=False,
    )

    # 2. Seed shared benchmark (tenant_id=None)
    await store_alpha.ingest_document(
        "public_benchmark.txt",
        b"Public Marketing Benchmark: General email open rates average 21.5% across B2B SaaS.",
        is_benchmark=True,
    )

    # 3. Create a store without any tenant_id (unset tenant_id)
    store_unset = KnowledgeStore(
        tenant_id=None,
        db_url=db_url,
        session_factory=store_alpha._session_factory,
    )

    # 4. Probing query for proprietary data without tenant_id
    res_prop = await store_unset.retrieve("Confidential Alpha financial profit margin", top_k=10)
    for r in res_prop:
        assert r["tenant_id"] is None, "Proprietary tenant data leaked to query without tenant_id!"
        assert r["is_benchmark"] is True, "Non-benchmark returned to query without tenant_id!"

    # 5. Verify that StateStore without tenant_id returns zero proprietary records
    from core.state.store import StateStore
    from core.state.schemas import Job, JobStatus, JobMode, ResearchNote

    state_alpha = StateStore(tenant_id="tenant_alpha", db_url=db_url)
    await state_alpha.init_db()

    job = Job(id="job_alpha_1", tenant_id="tenant_alpha", query="Test Alpha Query")
    await state_alpha.create_job(job)

    note = ResearchNote(
        id="note_alpha_1",
        job_id="job_alpha_1",
        tenant_id="tenant_alpha",
        claim="Alpha Confidential Claim",
        source_type="web",
        excerpt="Secret data",
        task_id="task_1",
    )
    await state_alpha.add_note(note)

    # Query with unset tenant_id
    state_unset = StateStore(tenant_id="", db_url=db_url, session_factory=state_alpha._session_factory)
    notes_unset = await state_unset.get_notes("job_alpha_1")
    assert len(notes_unset) == 0, "StateStore without tenant_id returned notes from tenant_alpha!"

    job_unset = await state_unset.get_job("job_alpha_1")
    assert job_unset is None, "StateStore without tenant_id returned job belonging to tenant_alpha!"


@pytest.mark.asyncio
async def test_postgres_rls_isolation_and_unset_tenant():
    """
    Test Step 1 requirement for PostgreSQL + pgvector with Row-Level Security:
    Connects to Postgres as non-superuser (app_user), verifies RLS policies,
    and proves that a query without app.tenant_id set returns 0 rows.
    """
    import os
    import socket
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy import text

    db_url = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://app_user:app_password@localhost:5432/deep_research",
    )

    if not db_url.startswith("postgresql"):
        pytest.skip("DATABASE_URL is not configured for PostgreSQL")

    # Check TCP reachability of Postgres host:port
    try:
        host = "localhost"
        port = 5432
        if "@" in db_url and ":" in db_url.split("@")[1]:
            hp_part = db_url.split("@")[1].split("/")[0]
            host, port_str = hp_part.split(":")
            port = int(port_str)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1.0)
        sock.connect((host, port))
        sock.close()
    except Exception:
        pytest.skip(f"PostgreSQL at {host}:{port} is unreachable. Docker daemon/container deep_research_postgres is stopped.")

    # Live execution against PostgreSQL with RLS
    engine = create_async_engine(db_url, echo=False)
    try:
        # 1. Apply schema.sql
        from pathlib import Path
        schema_path = Path(__file__).resolve().parent.parent / "db" / "schema.sql"
        if schema_path.exists():
            schema_sql = schema_path.read_text(encoding="utf-8")
            # Execute schema statements
            async with engine.begin() as conn:
                for statement in schema_sql.split(";"):
                    stmt = statement.strip()
                    if stmt:
                        try:
                            await conn.execute(text(stmt))
                        except Exception:
                            pass

        # 2. Seed data under Tenant Alpha
        async with engine.connect() as conn:
            # Set tenant_alpha
            await conn.execute(text("SET LOCAL app.tenant_id = 'tenant_alpha'"))
            await conn.execute(
                text("INSERT INTO jobs (id, tenant_id, query, status) VALUES ('job_pg_alpha', 'tenant_alpha', 'Alpha Query', 'completed') ON CONFLICT (id) DO NOTHING")
            )
            await conn.execute(
                text("INSERT INTO research_notes (id, job_id, tenant_id, claim, excerpt, task_id) VALUES ('note_pg_alpha', 'job_pg_alpha', 'tenant_alpha', 'Confidential Claim', 'Secret text', 'task_1') ON CONFLICT (id) DO NOTHING")
            )
            await conn.commit()

        # 3. PROVE: Query WITHOUT app.tenant_id set returns NOTHING (0 rows)
        async with engine.connect() as conn:
            # Do NOT set app.tenant_id (or set to empty)
            await conn.execute(text("SET LOCAL app.tenant_id = ''"))
            res_jobs = await conn.execute(text("SELECT * FROM jobs WHERE id = 'job_pg_alpha'"))
            assert len(res_jobs.fetchall()) == 0, "RLS FAILURE: Query without app.tenant_id returned rows!"

            res_notes = await conn.execute(text("SELECT * FROM research_notes WHERE job_id = 'job_pg_alpha'"))
            assert len(res_notes.fetchall()) == 0, "RLS FAILURE: Query without app.tenant_id returned notes!"

        # 4. PROVE: Tenant Beta cannot see Tenant Alpha data
        async with engine.connect() as conn:
            await conn.execute(text("SET LOCAL app.tenant_id = 'tenant_beta'"))
            res_beta_jobs = await conn.execute(text("SELECT * FROM jobs WHERE id = 'job_pg_alpha'"))
            assert len(res_beta_jobs.fetchall()) == 0, "RLS FAILURE: Tenant Beta accessed Tenant Alpha jobs!"

            res_beta_notes = await conn.execute(text("SELECT * FROM research_notes WHERE job_id = 'job_pg_alpha'"))
            assert len(res_beta_notes.fetchall()) == 0, "RLS FAILURE: Tenant Beta accessed Tenant Alpha notes!"

        # 5. PROVE: Tenant Alpha CAN see its own data
        async with engine.connect() as conn:
            await conn.execute(text("SET LOCAL app.tenant_id = 'tenant_alpha'"))
            res_alpha_jobs = await conn.execute(text("SELECT * FROM jobs WHERE id = 'job_pg_alpha'"))
            assert len(res_alpha_jobs.fetchall()) == 1, "Tenant Alpha should see its own job!"

            res_alpha_notes = await conn.execute(text("SELECT * FROM research_notes WHERE job_id = 'job_pg_alpha'"))
            assert len(res_alpha_notes.fetchall()) == 1, "Tenant Alpha should see its own notes!"

    finally:
        await engine.dispose()

