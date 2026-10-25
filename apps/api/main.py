from __future__ import annotations

import asyncio
import csv
from datetime import datetime, timezone
import io
import json
import os
import uuid
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from langgraph.types import Command
from langgraph.checkpoint.sqlite import SqliteSaver

from core.graph.builder import ResearchGraphBuilder
from core.models.router import ModelRouter
from core.state.store import StateStore
from core.state.schemas import (
    Job,
    JobStatus,
    JobMode,
    ResearchNote,
    Artifact,
    RunEvent,
    EventType,
    Brief,
    Plan,
    PlanTask,
    BudgetState,
)
from apps.api.dependencies import get_tenant_id, get_state_store, get_model_router


from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.checkpoint.memory import InMemorySaver

CHECKPOINT_DB_PATH = os.environ.get("CHECKPOINTS_DB_PATH", "checkpoints.db")
_checkpointer_cm = None
_checkpointer = None
_compiled_graph = None
_graph_lock = asyncio.Lock()

async def get_compiled_graph():
    global _checkpointer_cm, _checkpointer, _compiled_graph
    async with _graph_lock:
        if _checkpointer is not None and hasattr(_checkpointer, "conn") and _checkpointer.conn is not None:
            try:
                await _checkpointer.conn.execute("SELECT 1")
                return _compiled_graph
            except Exception:
                pass

        _checkpointer_cm = AsyncSqliteSaver.from_conn_string(CHECKPOINT_DB_PATH)
        _checkpointer = await _checkpointer_cm.__aenter__()
        builder = ResearchGraphBuilder(checkpointer=_checkpointer)
        _compiled_graph = builder.build()
        return _compiled_graph

# Backwards-compatible export for synchronous graph inspection
compiled_graph = ResearchGraphBuilder(checkpointer=InMemorySaver()).build()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize persistent checkpointer and state
    await get_compiled_graph()
    yield
    # Keep connection open for any finishing background async tasks


app = FastAPI(
    title="Deep Researcher Multi-Agent Service",
    version="1.0.0",
    description="Production-style multi-agent Deep Researcher system grounded in web, connected data sources, and tenant knowledge base.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -------------------------------------------------------------
# Request & Response Schemas
# -------------------------------------------------------------
class CreateJobRequest(BaseModel):
    query: str
    tenant_id: Optional[str] = None
    mode: Optional[JobMode] = None
    extra_context: Optional[str] = None


class JobResponse(BaseModel):
    id: str
    tenant_id: str
    query: str
    status: JobStatus
    mode: JobMode
    confidence: float
    brief: Optional[Dict[str, Any]] = None
    plan: Optional[Dict[str, Any]] = None
    report: Optional[str] = None
    budget: Dict[str, Any]


class ClarifyRequest(BaseModel):
    response: str
    audience: Optional[str] = None
    geography: Optional[str] = None
    goal_kpi: Optional[str] = None
    budget: Optional[str] = None
    brand_voice: Optional[str] = None
    named_competitors: Optional[List[str]] = None


class FollowupRequest(BaseModel):
    query: str


class FollowupResponse(BaseModel):
    job_id: str
    query: str
    answer: str


class EvidenceLocation(BaseModel):
    page_no: Optional[int] = None
    heading_path: List[str] = Field(default_factory=list)
    char_start: Optional[int] = None
    char_end: Optional[int] = None
    video_timestamp_url: Optional[str] = None


class EvidenceSourceItem(BaseModel):
    note_id: Optional[str] = None
    url: str
    canonical_url: Optional[str] = None
    title: Optional[str] = None
    source_family: str = "web_general"
    location: EvidenceLocation = Field(default_factory=EvidenceLocation)
    text_fragment_url: Optional[str] = None
    status: str = "verified"  # "verified", "rejected", "blocked"
    claim: Optional[str] = None
    excerpt: Optional[str] = None
    reason: Optional[str] = None


class JobSourcesResponse(BaseModel):
    job_id: str
    tenant_id: str
    source_families: Dict[str, List[EvidenceSourceItem]]
    coverage_counts: Dict[str, int]
    total_sources: int


# -------------------------------------------------------------
# Background Execution Helper
# -------------------------------------------------------------
async def run_graph_execution(job: Job, state_store: StateStore, resume_payload: Optional[str] = None):
    config = {"configurable": {"thread_id": job.id}}
    initial_state = {
        "job_id": job.id,
        "tenant_id": job.tenant_id,
        "query": job.query,
        "mode": job.mode.value if job.mode else "deep",
        "stage": "started",
        "budget": job.budget.model_dump(),
        "extra_research_rounds": 0,
    }

    try:
        await state_store.emit_event(
            job.id, EventType.STAGE_STARTED, {"stage": "graph_execution_started"}
        )

        # Handle resume vs fresh invoke
        graph = await get_compiled_graph()
        if resume_payload is not None:
            input_command = Command(resume=resume_payload)
            res = await graph.ainvoke(input_command, config=config)
        else:
            res = await graph.ainvoke(initial_state, config=config)

        # Check if graph paused on interrupt
        state_snapshot = await graph.aget_state(config)
        if "__interrupt__" in res or (state_snapshot and state_snapshot.next):
            # We are interrupted (waiting for clarification)
            job.status = JobStatus.NEEDS_CLARIFICATION
            tasks = state_snapshot.tasks if state_snapshot else []
            interrupt_val = {}
            if "__interrupt__" in res and res["__interrupt__"]:
                interrupt_val = res["__interrupt__"][0].value
            elif tasks and tasks[0].interrupts:
                interrupt_val = tasks[0].interrupts[0].value

            await state_store.emit_event(
                job.id,
                EventType.CLARIFICATION_NEEDED,
                {"interrupt": interrupt_val},
            )
            await state_store.update_job(job)
            return

        # Complete run
        job.status = JobStatus.COMPLETED
        job.report = res.get("report")
        if res.get("plan"):
            job.plan = Plan(**res["plan"])
        if res.get("brief"):
            job.brief = Brief(**res["brief"])

        # Persist notes if added in graph
        for n in res.get("notes", []):
            try:
                note_obj = ResearchNote(**n)
                await state_store.add_note(note_obj)
            except Exception:
                pass

        await state_store.update_job(job)
        await state_store.emit_event(
            job.id, EventType.DONE, {"report_preview": job.report[:200] if job.report else ""}
        )

    except Exception as e:
        job.status = JobStatus.FAILED
        await state_store.update_job(job)
        await state_store.emit_event(job.id, EventType.ERROR, {"error": str(e)})


# -------------------------------------------------------------
# Endpoints
# -------------------------------------------------------------
@app.post("/v1/jobs", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_job(
    req: CreateJobRequest,
    tenant_id: str = Depends(get_tenant_id),
):
    tid = req.tenant_id or tenant_id
    store = get_state_store(tid)
    job = Job(
        tenant_id=tid,
        query=req.query,
        mode=req.mode or JobMode.DEEP,
        status=JobStatus.RUNNING,
    )
    await store.create_job(job)

    # Launch execution asynchronously in background
    asyncio.create_task(run_graph_execution(job, store))

    return JobResponse(
        id=job.id,
        tenant_id=job.tenant_id,
        query=job.query,
        status=job.status,
        mode=job.mode,
        confidence=job.confidence,
        brief=job.brief.model_dump() if job.brief else None,
        plan=job.plan.model_dump() if job.plan else None,
        report=job.report,
        budget=job.budget.model_dump(),
    )


@app.get("/v1/jobs/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: str,
    tenant_id: str = Depends(get_tenant_id),
):
    store = get_state_store(tenant_id)
    job = await store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return JobResponse(
        id=job.id,
        tenant_id=job.tenant_id,
        query=job.query,
        status=job.status,
        mode=job.mode,
        confidence=job.confidence,
        brief=job.brief.model_dump() if job.brief else None,
        plan=job.plan.model_dump() if job.plan else None,
        report=job.report,
        budget=job.budget.model_dump(),
    )


@app.get("/v1/jobs/{job_id}/events")
async def stream_job_events(
    job_id: str,
    tenant_id: str = Depends(get_tenant_id),
):
    store = get_state_store(tenant_id)
    job = await store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    async def event_generator():
        async for event in store.subscribe_events(job_id):
            data = {
                "id": event.id,
                "job_id": event.job_id,
                "tenant_id": event.tenant_id,
                "event_type": event.event_type.value,
                "payload": event.payload,
                "timestamp": event.timestamp.isoformat(),
            }
            yield {
                "event": event.event_type.value,
                "data": json.dumps(data),
            }

    return EventSourceResponse(event_generator())


@app.post("/v1/jobs/{job_id}/clarify", response_model=JobResponse)
async def clarify_job(
    job_id: str,
    req: ClarifyRequest,
    tenant_id: str = Depends(get_tenant_id),
):
    store = get_state_store(tenant_id)
    job = await store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status != JobStatus.NEEDS_CLARIFICATION:
        raise HTTPException(status_code=400, detail="Job does not require clarification")

    # Resume graph execution
    job.status = JobStatus.RUNNING
    await store.update_job(job)

    resume_text = req.response
    if req.audience:
        resume_text += f"\nAudience: {req.audience}"
    if req.geography:
        resume_text += f"\nGeography: {req.geography}"

    asyncio.create_task(run_graph_execution(job, store, resume_payload=resume_text))

    return JobResponse(
        id=job.id,
        tenant_id=job.tenant_id,
        query=job.query,
        status=job.status,
        mode=job.mode,
        confidence=job.confidence,
        brief=job.brief.model_dump() if job.brief else None,
        plan=job.plan.model_dump() if job.plan else None,
        report=job.report,
        budget=job.budget.model_dump(),
    )


@app.post("/v1/jobs/{job_id}/followup", response_model=FollowupResponse)
async def followup_job(
    job_id: str,
    req: FollowupRequest,
    tenant_id: str = Depends(get_tenant_id),
    router: ModelRouter = Depends(get_model_router),
):
    store = get_state_store(tenant_id)
    job = await store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    notes = await store.get_notes(job_id)
    notes_summary = "\n".join([f"[{n.id}] {n.claim} ({n.source_url or 'doc'})" for n in notes])
    prompt = f"Given report:\n{job.report}\n\nNotes:\n{notes_summary}\n\nAnswer followup: {req.query}"

    model = router.get_model("followup")
    resp = await model.ainvoke(prompt)
    answer = resp.content if hasattr(resp, "content") else str(resp)

    return FollowupResponse(job_id=job_id, query=req.query, answer=answer)


@app.get("/v1/jobs/{job_id}/artifacts", response_model=List[Dict[str, Any]])
async def get_job_artifacts(
    job_id: str,
    tenant_id: str = Depends(get_tenant_id),
):
    store = get_state_store(tenant_id)
    artifacts = await store.get_artifacts(job_id)
    return [a.model_dump() for a in artifacts]


@app.get("/v1/jobs/{job_id}/sources", response_model=JobSourcesResponse)
async def get_job_sources(
    job_id: str,
    tenant_id: str = Depends(get_tenant_id),
    store: StateStore = Depends(get_state_store),
):
    """
    Returns all evidence gathered for a job, grouped by source_family.
    Includes exact location (page_no, heading_path, offsets, video timestamp),
    clickable text_fragment_url, and status (verified/rejected/blocked).
    """
    job = await store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    notes = await store.get_notes(job_id)
    events = await store.get_events(job_id)

    families: Dict[str, List[EvidenceSourceItem]] = {}
    coverage: Dict[str, int] = {}

    # 1. Verified & unverified notes
    for n in notes:
        fam = n.source_family or "web_general"
        if fam not in families:
            families[fam] = []
        coverage[fam] = coverage.get(fam, 0) + 1

        loc = EvidenceLocation(
            page_no=n.page_no,
            heading_path=n.heading_path or [],
            char_start=n.char_start,
            char_end=n.char_end,
            video_timestamp_url=n.video_timestamp_url,
        )
        families[fam].append(
            EvidenceSourceItem(
                note_id=n.id,
                url=n.url or n.source_url or "https://example.com",
                canonical_url=n.canonical_url,
                title=n.title or (n.url or n.source_url),
                source_family=fam,
                location=loc,
                text_fragment_url=n.text_fragment_url,
                status="verified" if n.is_verified else "unverified",
                claim=n.claim,
                excerpt=n.excerpt,
            )
        )

    # 2. Blocked pages and rejected notes from events
    for ev in events:
        if ev.event_type == EventType.PAGE_BLOCKED:
            p_payload = ev.payload or {}
            fam = "blocked"
            if fam not in families:
                families[fam] = []
            families[fam].append(
                EvidenceSourceItem(
                    url=p_payload.get("url", ""),
                    source_family="blocked",
                    status="blocked",
                    reason=p_payload.get("reason", "Domain blocked / forbidden"),
                )
            )
        elif ev.event_type == EventType.NOTE_REJECTED:
            r_payload = ev.payload or {}
            fam = "rejected"
            if fam not in families:
                families[fam] = []
            families[fam].append(
                EvidenceSourceItem(
                    url=r_payload.get("url", ""),
                    source_family="rejected",
                    status="rejected",
                    reason=r_payload.get("reason", "Excerpt verification match failed in document text"),
                )
            )

    total = sum(len(items) for items in families.values())
    return JobSourcesResponse(
        job_id=job_id,
        tenant_id=tenant_id,
        source_families=families,
        coverage_counts=coverage,
        total_sources=total,
    )


@app.post("/v1/tenants/{tenant_id}/documents")
async def upload_tenant_document(
    tenant_id: str,
    file: UploadFile = File(...),
):
    content = await file.read()
    filename = file.filename or "unknown.txt"
    return {
        "document_id": f"doc_{uuid.uuid4().hex[:8]}",
        "tenant_id": tenant_id,
        "filename": filename,
        "size_bytes": len(content),
        "status": "indexed",
    }


@app.post("/v1/uploads")
async def general_upload(
    file: UploadFile = File(...),
    tenant_id: str = Depends(get_tenant_id),
):
    content = await file.read()
    return {
        "upload_id": f"upl_{uuid.uuid4().hex[:8]}",
        "filename": file.filename,
        "size_bytes": len(content),
        "tenant_id": tenant_id,
    }


# --- Phase 2: Idea Miner Crawl Endpoints ---

from core.crawl.schemas import CrawlRunConfig, CrawlRunRecord, CrawlMode
from core.crawl.store import CrawlStore
from core.crawl.engine import CrawlEngine
from core.crawl.storage import RawDocumentStore

_crawl_store: Optional[CrawlStore] = None


def get_crawl_store() -> CrawlStore:
    global _crawl_store
    if _crawl_store is None:
        os.makedirs("data", exist_ok=True)
        db_url = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///data/crawl_engine.db")
        _crawl_store = CrawlStore(db_url=db_url)
    return _crawl_store


@app.post("/v1/crawl/runs", response_model=CrawlRunRecord)
async def start_crawl_run(
    req: CrawlRunConfig,
    background_tasks: BackgroundTasks,
    store: CrawlStore = Depends(get_crawl_store),
):
    """Starts a bulk, resumable crawl run for a source."""
    await store.init_db()
    engine = CrawlEngine(store=store, doc_store=RawDocumentStore())

    # Pre-register run in DB
    run_id = f"crawl_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{os.urandom(3).hex()}"
    run_record = CrawlRunRecord(
        id=run_id,
        source=req.source,
        mode=req.mode,
        since_date=req.since_date,
        limit_pages=req.limit_pages,
        config_override=req.model_dump(),
    )
    await store.create_crawl_run(run_record)

    # Launch background task
    background_tasks.add_task(engine.run, req)
    return run_record


@app.get("/v1/crawl/runs/{run_id}", response_model=CrawlRunRecord)
async def get_crawl_run_status(
    run_id: str,
    store: CrawlStore = Depends(get_crawl_store),
):
    """Retrieves progress, counts, and domain errors for a crawl run."""
    run = await store.get_crawl_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Crawl run not found")
    return run


@app.get("/v1/crawl/runs", response_model=List[CrawlRunRecord])
async def list_crawl_runs(
    limit: int = 50,
    store: CrawlStore = Depends(get_crawl_store),
):
    """Lists recent crawl runs."""
    await store.init_db()
    return await store.list_crawl_runs(limit=limit)


@app.get("/v1/crawl/runs/{run_id}/events")
async def stream_crawl_events(
    run_id: str,
    store: CrawlStore = Depends(get_crawl_store),
):
    """Streams SSE events (page_fetched, page_blocked, page_skipped, crawl_completed)."""
    async def event_generator():
        async for evt in store.subscribe_events(run_id):
            yield {
                "event": evt.event_type,
                "data": json.dumps({
                    "run_id": evt.run_id,
                    "event_type": evt.event_type,
                    "payload": evt.payload,
                    "timestamp": evt.timestamp.isoformat(),
                }),
            }

    return EventSourceResponse(event_generator())


# --- Phase 6: Idea Miner API Endpoints ---

from core.ideas.schemas import (
    IdeaRecord,
    IdeaBrief,
    IdeaCard,
    ProjectPlacement,
    ProjectStage,
    EvidenceEntry,
)
from core.ideas.store import IdeaStore
from core.ideas.generator import IdeaGeneratorAgent
from skills.idea_analysis.engine import IdeaAnalysisEngine
from core.sources.policy import SourcePolicyEngine

_idea_store: Optional[IdeaStore] = None


def get_idea_store() -> IdeaStore:
    global _idea_store
    if _idea_store is None:
        os.makedirs("data", exist_ok=True)
        db_url = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///data/idea_miner.db")
        _idea_store = IdeaStore(db_url=db_url)
    return _idea_store


class IdeaSearchRequest(BaseModel):
    query: Optional[str] = None
    year: Optional[int] = None
    event_name: Optional[str] = None
    placement: Optional[str] = None
    tech_stack: Optional[List[str]] = None
    domain_tags: Optional[List[str]] = None
    limit: int = 20


@app.post("/v1/ideas/search", response_model=List[IdeaRecord])
async def search_ideas(
    req: IdeaSearchRequest,
    store: IdeaStore = Depends(get_idea_store),
    tenant_id: str = Depends(get_tenant_id),
):
    """Hybrid semantic + keyword search with metadata filters."""
    await store.init_db()
    results = await store.search_ideas(
        query=req.query,
        tenant_id=tenant_id,
        year=req.year,
        event_name=req.event_name,
        placement=req.placement,
        tech_stack=req.tech_stack,
        domain_tags=req.domain_tags,
        limit=req.limit,
    )
    return results


@app.get("/v1/ideas/clusters")
async def get_idea_clusters(
    n_clusters: Optional[int] = None,
    store: IdeaStore = Depends(get_idea_store),
    tenant_id: str = Depends(get_tenant_id),
):
    """Clusters ideas into semantic themes with representative projects and top tags."""
    await store.init_db()
    ideas = await store.search_ideas(query=None, tenant_id=tenant_id, limit=200)
    engine = IdeaAnalysisEngine()
    clusters = engine.cluster(ideas, n_clusters=n_clusters)
    return {"sample_size": len(ideas), "clusters": [c.model_dump() for c in clusters]}


@app.get("/v1/ideas/trends")
async def get_idea_trends(
    store: IdeaStore = Depends(get_idea_store),
    tenant_id: str = Depends(get_tenant_id),
):
    """Returns win rates, saturated vs underexplored categories, and winner patterns."""
    await store.init_db()
    ideas = await store.search_ideas(query=None, tenant_id=tenant_id, limit=300)
    engine = IdeaAnalysisEngine()
    trends_rep = engine.trends(ideas)
    winners_rep = engine.winner_patterns(ideas)
    return {
        "trends": trends_rep.model_dump(),
        "winner_patterns": winners_rep.model_dump(),
    }


@app.get("/v1/ideas/{idea_id}", response_model=IdeaRecord)
async def get_idea(
    idea_id: str,
    store: IdeaStore = Depends(get_idea_store),
    tenant_id: str = Depends(get_tenant_id),
):
    """Retrieves an IdeaRecord including its verified evidence entries."""
    await store.init_db()
    idea = await store.get_idea(idea_id=idea_id, tenant_id=tenant_id)
    if not idea:
        raise HTTPException(status_code=404, detail="Idea record not found")
    return idea


@app.post("/v1/ideas/generate", response_model=List[IdeaCard])
async def generate_ideas(
    brief: IdeaBrief,
    store: IdeaStore = Depends(get_idea_store),
    tenant_id: str = Depends(get_tenant_id),
):
    """Generates grounded IdeaCards from a brief, citing 3-8 verified inspirations."""
    await store.init_db()
    ref_ideas = await store.search_ideas(query=brief.problem_statement, tenant_id=tenant_id, limit=20)
    if not ref_ideas:
        ref_ideas = await store.search_ideas(query=None, tenant_id=tenant_id, limit=20)

    engine = IdeaAnalysisEngine()
    clusters = engine.cluster(ref_ideas) if ref_ideas else []

    generator = IdeaGeneratorAgent()
    cards = await generator.generate_cards(
        brief=brief,
        reference_ideas=ref_ideas,
        clusters=clusters,
    )
    return cards


class IdeaImportRequest(BaseModel):
    format: str = "json"  # "json" | "csv"
    data: str  # JSON array string or CSV string


@app.post("/v1/ideas/import")
async def import_ideas(
    req: IdeaImportRequest,
    store: IdeaStore = Depends(get_idea_store),
    tenant_id: str = Depends(get_tenant_id),
):
    """
    Imports ideas via JSON or CSV for sources not permitted to crawl
    (e.g., LinkedIn, Crunchbase, X).
    """
    await store.init_db()
    imported_count = 0
    errors = []

    if req.format.lower() == "json":
        try:
            items = json.loads(req.data)
            if not isinstance(items, list):
                items = [items]
            for it in items:
                rec = IdeaRecord.model_validate(it)
                rec.tenant_id = tenant_id
                await store.upsert_idea(rec)
                imported_count += 1
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to parse JSON: {e}")
    elif req.format.lower() == "csv":
        try:
            reader = csv.DictReader(io.StringIO(req.data))
            for row in reader:
                pid = row.get("id") or str(uuid.uuid4())
                name = row.get("name") or row.get("title") or "Imported Idea"
                prob = row.get("problem") or ""
                sol = row.get("solution") or row.get("solution_sketch") or ""
                stack = [s.strip() for s in (row.get("tech_stack") or "").split(",") if s.strip()]
                dom = [d.strip() for d in (row.get("domain_tags") or "").split(",") if d.strip()]
                rec = IdeaRecord(
                    id=pid,
                    tenant_id=tenant_id,
                    name=name,
                    problem=prob,
                    solution=sol,
                    tech_stack=stack,
                    domain_tags=dom,
                    first_seen_url=row.get("first_seen_url") or "manual://import",
                )
                await store.upsert_idea(rec)
                imported_count += 1
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to parse CSV: {e}")
    else:
        raise HTTPException(status_code=400, detail="Unsupported format: must be 'json' or 'csv'")

    return {"status": "success", "imported_count": imported_count, "errors": errors}


@app.get("/v1/sources/coverage")
async def get_sources_coverage(
    policy_engine: SourcePolicyEngine = Depends(lambda: SourcePolicyEngine()),
):
    """Returns coverage breakdown across all source families and domain policies."""
    policies = policy_engine.policy
    total_sources = len(policies)
    allowed_count = sum(1 for p in policies.values() if p.get("allowed", False))
    denied_count = total_sources - allowed_count

    breakdown = []
    for domain, pol in policies.items():
        breakdown.append({
            "domain": domain,
            "allowed": pol.get("allowed", False),
            "access_method": pol.get("access_method", "search_engine"),
            "rate_limit_rps": pol.get("rate_limit_rps", 1.0),
            "max_pages_per_run": pol.get("max_pages_per_run", 100),
            "notes": pol.get("notes", ""),
        })

    return {
        "total_sources_configured": total_sources,
        "allowed_sources": allowed_count,
        "denied_sources": denied_count,
        "sources": breakdown,
    }


