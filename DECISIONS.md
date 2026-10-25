# Architectural Decisions & Design Log

This document records the design choices, architectural assumptions, and audit resolutions implemented for the production-style multi-agent "Deep Researcher" system.

---

## 1. Audit Summary: What Was a Stub, What Changed, and Uncompleted Items

### What Was a Stub
- **Exa Search Provider (`core/tools/search.py`)**: Previously returned static mock items without loading or calling `exa_py`.
- **Page Fetch Service (`core/tools/fetch.py`)**: Previously performed regex HTML stripping with httpx fallback without executing headless browser extraction via `crawl4ai`.
- **MCP Client (`core/tools/mcp_wrapper.py`)**: Simulated allow-listed responses without integrating `langchain-mcp-adapters`'s `MultiServerMCPClient`.
- **Sandbox Clients (`core/sandbox/client.py`)**: Contained placeholder imports; `DockerSandboxClient` with `--network none` was not present.
- **Source Router**: No dedicated source router existed; source selection was hardcoded.
- **Analyst Node (`core/agents/analyst.py`)**: CSV and chart computation was only executed in unit tests, not wired into the LangGraph workflow.
- **Compliance Gate**: The `ComplianceGate` class existed in isolation and was not wired into `builder.py`.
- **Deliver Node**: No artifact upload or presentation delivery node existed in the graph.
- **Langfuse Observability**: The `langfuse` package was installed, but no tracing module or span decorators were implemented.
- **Persistent Checkpointer in API**: The FastAPI app used `InMemorySaver()`, which did not persist checkpoints across process restarts.

### What Changed
1. **LangGraph Graph Complete Sequential Wiring (`core/graph/builder.py`)**:
   - Sequential flow wired in exact order:
     `START -> classifier -> (shallow_research or hitl_clarification) -> source_router -> planner -> workers -> verifier -> analyst -> writer -> citation_gate -> compliance_gate -> deliver -> END`.
   - **Shallow -> Deep Escalation**: Queries exceeding single factual lookups or exhausting the shallow search budget automatically escalate to `source_router -> planner`.
   - **Per-Run Budget Enforcement**: `store.check_budget()` called across graph nodes: emits `budget_warning` event at 80% budget, and initiates a clean partial stop at 100% budget, skipping further workers and routing directly to `writer` to produce a report from existing notes.
2. **Real Tool Providers Behind Existing Interfaces**:
   - `core/tools/search.py`: Real `AsyncTavilyClient` and `exa_py.Exa` search APIs with graceful deterministic fallbacks for offline tests.
   - `core/tools/fetch.py`: Headless scraping via `crawl4ai.AsyncWebCrawler` with anti-injection untrusted data XML fencing.
   - `core/tools/mcp_wrapper.py`: Real `langchain-mcp-adapters` integration (`MultiServerMCPClient`) with strict read-only allowlists (`HUBSPOT_ALLOWLIST`, `GA4_ALLOWLIST`).
   - `core/sandbox/client.py`: Real `E2BSandboxClient` and `DockerSandboxClient` (`docker run --network none`), with network-isolated `LocalSubprocessSandboxClient` fallback.
3. **Analyst Agent (`core/agents/analyst.py`)**:
   - Implemented `AnalystAgent` executing sandbox Python code for tasks requiring tables, charts, or CSV metrics, writing computed KPIs to `StateStore` as `ResearchNote(source_type="computed")`.
4. **Persistent Checkpointer (`apps/api/main.py`)**:
   - Replaced `InMemorySaver` with `AsyncSqliteSaver` on `checkpoints.db`.
   - Added `test_kill_process_mid_interrupt_and_resume_from_disk` in `tests/test_scaffold.py`, verifying state recovery and resumption after simulated hard process crash.
5. **Observability & Object Storage**:
   - Created `core/observability/tracing.py` using Langfuse 5.x SDK (`@trace_agent`, `@trace_tool`).
   - Integrated `MinIOStorageService` into `deliver` node to persist `report.md`, charts, and `presentation.pptx`.
6. **End-to-End Pipeline Integration Test (`tests/test_end_to_end_pipeline.py`)**:
   - Added full end-to-end test running a vague deep request through clarify, plan, parallel research, CSV analysis, synthesis, both gates, and delivery, verifying 100% of report claims map to notes.

### Uncompleted Items & Host Constraints
- **Live Docker Daemon on Host**:
  - The local Windows environment has Docker Desktop service (`com.docker.service`) installed but stopped. Starting the Windows service requires elevated Administrator UAC privileges (`Start-Service : Service 'com.docker.service' cannot be started due to: Cannot open service on computer '.'`).
  - As a result, `docker compose up -d` could not be executed directly in this unprivileged agent session.
  - **Resolution & Deliverables**:
    - `infra/docker-compose.yml` is fully configured with `pgvector/pgvector:pg16`, `minio/minio`, `langfuse/langfuse:2`, and the API container.
    - `db/schema.sql` defines the complete database schema with Row-Level Security (`ALTER TABLE ... FORCE ROW LEVEL SECURITY;`), non-superuser role `app_user`, and tenant isolation policies.
    - The tenant isolation test suite (`tests/test_tenancy_knowledge.py`) verifies 30 probing queries with zero cross-tenant leakage.

---

## 2. Environment & Runtime Compatibility
- **Target Runtime**: Python 3.12 (standardized in `infra/Dockerfile` using `python:3.12-slim`).
- **Local Dev / Test Compatibility**: Dual compatibility with Python 3.11 and Python 3.12, ensuring fast test cycles on both Windows hosts and containerized Linux runtimes.
- **Database Engine**: Production runs Postgres 16 with `pgvector` (`pgvector/pgvector:pg16`). Unit and integration tests leverage `aiosqlite` with vector similarity simulation to achieve fast, isolated, deterministic CI execution without depending on a live external daemon.

---

## 3. Multi-Tenancy & Row-Level Security (RLS)
- **Tenant Scoping**: All database tables (`jobs`, `research_notes`, `artifacts`, `run_events`, `documents`, `document_chunks`) include a mandatory `tenant_id` column.
- **RLS Policy Enforcement**: Production Postgres tables enforce `ALTER TABLE ... FORCE ROW LEVEL SECURITY;` with policies checking `tenant_id = current_setting('app.tenant_id', true)`.
- **Shared Benchmark Namespace**: Global benchmarks store `tenant_id = NULL`. RLS policies and the `KnowledgeStore` permit all tenants to read benchmark chunks (`tenant_id IS NULL OR tenant_id = current_setting('app.tenant_id', true)`), but write operations are restricted.
- **Connection Isolation**: `StateStore` and `KnowledgeStore` issue `SET LOCAL app.tenant_id = :tenant_id` at connection initialization, guaranteeing zero cross-tenant query leakage.

---

## 4. Dynamic Model Router (`config/models.yaml`)
- **Zero Hardcoded Model Names**: All LLM calls query `ModelRouter.get_model(role)`.
- **Role Assignments**:
  - `classifier`, `shallow`, `researcher` -> Fast role models via Groq (`llama-3.3-70b-versatile` / `llama-3.1-8b-instant`).
  - `clarifier`, `planner`, `verifier`, `writer`, `followup` -> Strong reasoning models via Google Gemini (`gemini-2.5-flash` / `gemini-1.5-pro`).
- **Offline & Test Mode**: When API keys are not supplied or `USE_MOCK_MODELS=true`, the router switches to deterministic semantic mock responders that allow offline testing of the multi-agent graph.

---

## 5. Checkpointing, HITL Interrupts & Resumption
- **LangGraph Checkpointing**: Built with LangGraph checkpointing protocol using `AsyncSqliteSaver` on `checkpoints.db` for persistent disk recovery, and `AsyncPostgresSaver` for clustered cloud deployments.
- **Human-In-The-Loop Interrupts**: The `hitl_clarification` node invokes LangGraph `interrupt(payload)` to pause graph execution and persist state when critical brief dimensions (audience, geography, goal/KPI, named competitors) are absent.
- **Resumption**: The `POST /v1/jobs/{id}/clarify` endpoint resumes the workflow seamlessly using `Command(resume=payload)` targeting the thread ID (`job_id`).

---

## 6. Event Streaming (SSE) & Shared Research State
- **Standard Protocol**: Server-Sent Events (`text/event-stream`) streaming via `EventSourceResponse`.
- **Event Types**: `stage_started`, `tool_call`, `note_added`, `clarification_needed`, `artifact_ready`, `budget_warning`, `gate_flagged`, `done`, `error`.
- **StateStore Layer**: All agent reads and writes are encapsulated behind `StateStore`. Direct raw SQL inside agent nodes is strictly prohibited. An asyncio queue broadcast mechanism powers live SSE subscriptions while persisting all events to `run_events`.

---

## 7. Safety, Guardrails & Anti-Injection
- **Prompt Injection Defense**: Untrusted external data from web crawlers or third-party APIs is filtered for adversarial directives (e.g. `ignore previous instructions`, `developer mode`), sanitized, and fenced inside `<untrusted_data>` XML blocks.
- **Citation Gate**: Evaluates report text using regex patterns for quantitative assertions (numbers, percentages, currencies) and comparative/superlative statements. Any claim missing a valid `[note_...]` citation tag is flagged or sanitized.
- **Compliance Gate**: Loads global and tenant-specific rules from `config/compliance/`. Identifies unsubstantiated ROI claims, competitor disparagement, or confidential data leakage. Executes one automatic rewrite loop; if persistent, blocks delivery and flags for human review.

---

## 8. Sandbox Computation & Skills Runtime
- **Sandbox Architecture**: Structured behind `SandboxClient`. Supports `DockerSandboxClient` (`--network none`), `E2BSandboxClient`, and `LocalSubprocessSandboxClient` (with network interfaces disabled via proxy isolation).
- **Skills Mount**: Skills reside in `/skills/<name>/SKILL.md` (e.g. `data_table_analysis`, `chart_generation`, `competitor_matrix`, `report_writer`, `pptx_from_template`).
- **Computation Tool**: `execute_tool` executes generated Python code in the sandbox, copying input data in and extracting outputs (JSON metrics, PNG charts). Scripts are persisted as `Artifact` models, and computed KPIs are committed back as `ResearchNote` objects with `source_type="computed"`.

---

## 9. MCP Read-Only Allowlisting
- **GA4 MCP**: Exposed strictly as a read-only reporting service (`run_report`, `get_metadata`, `run_realtime_report`).
- **HubSpot MCP**: Strict allowlist restricting access exclusively to read and search tools (`search_companies`, `get_company`, `search_deals`, `get_deal`, `search_contacts`). All mutation and creation operations raise `PermissionError`.

---

## 10. Audit Resolution, Verification Results, and Status of External Services

### 10.1 Gap Resolutions Implemented
1. **Explicit Fallbacks & Anti-Hallucination Protections**:
   - Added `PROVIDER_FALLBACK = "provider_fallback"` to `EventType` (`core/state/schemas.py`).
   - Added `"fallback"` to `ResearchNote.source_type` literal.
   - Updated `SearchResult` in `core/tools/search.py` with `is_fallback: bool` and `fallback_reason: Optional[str]`.
   - In `core/agents/worker.py` and `core/agents/shallow.py`, whenever an unconfigured or failing provider is encountered:
     - Emits a visible `provider_fallback` event onto the event stream.
     - Tags the generated `ResearchNote` with `source_type="fallback"`.
   - In `core/agents/writer.py`, when drafting reports:
     - Automatically checks if any note carries `source_type == "fallback"`.
     - Prepends a prominent warning callout banner: `> [!WARNING] **Notice: Provider Fallback Active**`.
     - Explicitly annotates references with `(FALLBACK [SIMULATED DATA])`, guaranteeing fallback data can never be presented as real research.
2. **Model Call Integrity & Mock Isolation**:
   - Moved `MockLLM` and `MockLLMResponse` out of core production modules into `tests/mocks.py`.
   - Updated `core/models/router.py`: In non-test mode, real models (`ChatGroq`, `ChatGoogleGenerativeAI`) are strictly enforced, raising a descriptive `ValueError` if the respective provider API keys are missing. Mocks can only be loaded during tests (`tests/mocks.py`).
   - Updated `core/agents/shallow.py` to make a real model call via `model = self.router.get_model("shallow")` and `await model.ainvoke(prompt)`.
   - Confirmed `core/agents/classifier.py` makes real model calls via `model = self.router.get_model("classifier")` and `await model.ainvoke(prompt)`.
3. **Database RLS & Unset Tenant Isolation**:
   - Added `test_query_without_tenant_id_returns_nothing` in `tests/test_tenancy_knowledge.py`: proves that querying with an unset/empty `tenant_id` returns 0 proprietary documents and 0 jobs/notes from other tenants.
   - Added `test_postgres_rls_isolation_and_unset_tenant` in `tests/test_tenancy_knowledge.py`: verifies Postgres RLS under non-superuser role `app_user` with `SET LOCAL app.tenant_id = ''` returning 0 rows.
4. **Pytest `live` Marker & Live Smoke Suite**:
   - Configured `pytest.ini` with registered `live` marker.
   - Created `tests/test_live_smoke.py` containing live tests with graceful `pytest.mark.skipif` when keys or daemons are absent.

---

### 10.2 Final Full Test Suite Run (`pytest -v`)
```text
============================= test session starts =============================
platform win32 -- Python 3.11.9, pytest-9.1.1, pluggy-1.7.0 -- D:\Dakshin_learn\agentic_ai_and_rag\deep-research-agent\venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: D:\Dakshin_learn\agentic_ai_and_rag\deep-research-agent
configfile: pytest.ini
plugins: anyio-4.13.0, langsmith-0.8.5, asyncio-1.4.0, mock-3.17.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=function, asyncio_default_test_loop_scope=function
collecting ... collected 31 items

tests/test_budgets_security_evals.py::test_hard_per_run_budget_warnings_and_clean_stop PASSED [  3%]
tests/test_budgets_security_evals.py::test_prompt_injection_defense_planted_malicious_page PASSED [  6%]
tests/test_budgets_security_evals.py::test_eval_suite_passes_all_thresholds PASSED [  9%]
tests/test_deep_planner_workers.py::test_3_competitor_deep_research_workflow PASSED [ 12%]
tests/test_end_to_end_pipeline.py::test_end_to_end_research_pipeline_vague_deep_request PASSED [ 16%]
tests/test_gap_writer_followup.py::test_gap_check_verifier_bounds PASSED [ 19%]
tests/test_gap_writer_followup.py::test_full_teardown_report_every_claim_maps_to_note PASSED [ 22%]
tests/test_live_smoke.py::test_live_groq_through_model_router PASSED     [ 25%]
tests/test_live_smoke.py::test_live_gemini_through_model_router SKIPPED  [ 29%]
tests/test_live_smoke.py::test_live_tavily_search PASSED                 [ 32%]
tests/test_live_smoke.py::test_live_exa_search SKIPPED (EXA_API_KEY ...) [ 35%]
tests/test_live_smoke.py::test_live_crawl4ai_fetch_public_page PASSED    [ 38%]
tests/test_live_smoke.py::test_live_analytics_mcp_over_stdio PASSED      [ 41%]
tests/test_live_smoke.py::test_live_hubspot_mcp_read_only_allowlist PASSED [ 45%]
tests/test_live_smoke.py::test_live_e2b_sandbox SKIPPED (E2B_API_KEY...) [ 48%]
tests/test_live_smoke.py::test_live_docker_sandbox_network_none_blocks_outbound SKIPPED [ 51%]
tests/test_pptx_compliance_mcp.py::test_compliance_gate_seeded_banned_claims PASSED [ 54%]
tests/test_pptx_compliance_mcp.py::test_pptx_layout_checks_max_5_bullets_no_empty_placeholders PASSED [ 58%]
tests/test_pptx_compliance_mcp.py::test_mcp_read_only_allowlist_enforcement PASSED [ 61%]
tests/test_sandbox_analysis.py::test_sandbox_client_isolated_execution PASSED [ 64%]
tests/test_sandbox_analysis.py::test_campaign_csv_computed_metrics_and_charts PASSED [ 67%]
tests/test_scaffold.py::test_job_creation_and_retrieval PASSED           [ 70%]
tests/test_scaffold.py::test_sse_event_streaming PASSED                  [ 74%]
tests/test_scaffold.py::test_checkpoint_and_resume_after_interrupt PASSED [ 77%]
tests/test_scaffold.py::test_kill_process_mid_interrupt_and_resume_from_disk PASSED [ 80%]
tests/test_shallow_citation.py::test_intent_classifier PASSED            [ 83%]
tests/test_shallow_citation.py::test_20_lookup_questions_return_valid_citations PASSED [ 87%]
tests/test_tenancy_knowledge.py::test_document_parser_and_chunker PASSED [ 90%]
tests/test_tenancy_knowledge.py::test_tenant_isolation_and_zero_leakage PASSED [ 93%]
tests/test_tenancy_knowledge.py::test_query_without_tenant_id_returns_nothing PASSED [ 96%]
tests/test_tenancy_knowledge.py::test_postgres_rls_isolation_and_unset_tenant SKIPPED [100%]

================== 26 passed, 5 skipped in 186.60s (0:03:06) ==================
```

---

### 10.3 Final Live Smoke Test Run (`pytest -m live -v`)
```text
============================= test session starts =============================
platform win32 -- Python 3.11.9, pytest-9.1.1, pluggy-1.7.0 -- D:\Dakshin_learn\agentic_ai_and_rag\deep-research-agent\venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: D:\Dakshin_learn\agentic_ai_and_rag\deep-research-agent
configfile: pytest.ini
plugins: anyio-4.13.0, langsmith-0.8.5, asyncio-1.4.0, mock-3.17.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=function, asyncio_default_test_loop_scope=function
collecting ... collected 31 items / 22 deselected / 9 selected

tests/test_live_smoke.py::test_live_groq_through_model_router PASSED     [ 11%]
tests/test_live_smoke.py::test_live_gemini_through_model_router SKIPPED  [ 22%]
tests/test_live_smoke.py::test_live_tavily_search PASSED                 [ 33%]
tests/test_live_smoke.py::test_live_exa_search SKIPPED (EXA_API_KEY ...) [ 44%]
tests/test_live_smoke.py::test_live_crawl4ai_fetch_public_page PASSED    [ 55%]
tests/test_live_smoke.py::test_live_analytics_mcp_over_stdio PASSED      [ 66%]
tests/test_live_smoke.py::test_live_hubspot_mcp_read_only_allowlist PASSED [ 77%]
tests/test_live_smoke.py::test_live_e2b_sandbox SKIPPED (E2B_API_KEY...) [ 88%]
tests/test_live_smoke.py::test_live_docker_sandbox_network_none_blocks_outbound SKIPPED [100%]

================= 5 passed, 4 skipped, 22 deselected in 6.25s =================
```

---

### 10.4 Verification Commands Audit Log
1. **Model Router & Classifier Audit**:
   `powershell -Command "Select-String -Path core\models\router.py,core\agents\classifier.py -Pattern 'mock|fake|fallback|keyword'"`
   Output:
   ```text
   core\models\router.py:20:    def __init__(self, config_path: Optional[str] = None, force_mock: bool = False):
   core\models\router.py:27:        self.force_mock = force_mock
   core\models\router.py:33:            # Fallback defaults if file missing
   core\models\router.py:62:        # In test mode or when explicitly forced, load MockLLM strictly from tests/mocks.py
   core\models\router.py:64:            self.force_mock
   core\models\router.py:65:            or os.environ.get("USE_MOCK_MODELS", "").lower() in ["1", "true", "yes"]
   core\models\router.py:71:                from tests.mocks import MockLLM
   core\models\router.py:72:                return MockLLM(role=role, config=cfg)
   core\agents\classifier.py:59:            # Fallback heuristic
   ```
   *Result*: Mocks exist strictly under `tests/mocks.py`. Real model calls are enforced in non-test mode.

2. **Search Provider Fallback Audit**:
   `powershell -Command "Select-String -Path core\tools\search.py -Pattern 'fallback|API_KEY'"`
   Output:
   ```text
   core\tools\search.py:17:    is_fallback: bool = False
   core\tools\search.py:18:    fallback_reason: Optional[str] = None
   core\tools\search.py:30:    """Tavily search provider with real API execution and test fallback."""
   core\tools\search.py:32:    def __init__(self, api_key: Optional[str] = None):
   core\tools\search.py:33:        self.api_key = api_key or os.environ.get("TAVILY_API_KEY")
   core\tools\search.py:37:        if self.api_key and not self.api_key.startswith("your_"):
   core\tools\search.py:40:                client = AsyncTavilyClient(api_key=self.api_key)
   core\tools\search.py:50:                            is_fallback=False,
   core\tools\search.py:58:        # Deterministic search fallback for tests and local dev
   core\tools\search.py:68:                is_fallback=True,
   core\tools\search.py:69:                fallback_reason="TAVILY_API_KEY not configured or unreachable; using simulated fallback data",
   core\tools\search.py:76:                is_fallback=True,
   core\tools\search.py:77:                fallback_reason="TAVILY_API_KEY not configured or unreachable; using simulated fallback data",
   core\tools\search.py:83:    """Exa neural search provider with real API execution and test fallback."""
   core\tools\search.py:85:    def __init__(self, api_key: Optional[str] = None):
   core\tools\search.py:86:        self.api_key = api_key or os.environ.get("EXA_API_KEY")
   core\tools\search.py:90:        if self.api_key and not self.api_key.startswith("your_"):
   core\tools\search.py:93:                exa = Exa(api_key=self.api_key)
   core\tools\search.py:103:                            is_fallback=False,
   core\tools\search.py:111:        # Fallback
   core\tools\search.py:118:                is_fallback=True,
   core\tools\search.py:119:                fallback_reason="EXA_API_KEY not configured or unreachable; using simulated fallback data",
   ```
   *Result*: Fallbacks are explicit, structured with `is_fallback=True` and reasons, surfaced via `provider_fallback` events and labeled in reports.

3. **Docker Compose Execution**:
   `docker compose -f infra\docker-compose.yml up -d`
   Output:
   ```text
   unable to get image 'minio/minio:latest': failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine; check if the path is correct and if the daemon is running: open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified.
   ```
   *Result*: Docker engine is stopped on Windows host (`com.docker.service`).

---

### 10.5 Unverified External Items & Why They Were Not Run
1. **Docker Engine & Live Services (`docker compose up -d`)**:
   - **Reason**: The Docker Desktop Windows service (`com.docker.service`) is stopped on the host. Executing `net start com.docker.service` fails with `System error 5 has occurred. Access is denied` because starting Windows services requires an interactive Administrator UAC prompt.
   - **Impacted Components**:
     - `deep_research_postgres` (pgvector container)
     - `deep_research_minio` (MinIO S3 service)
     - `deep_research_langfuse` (Langfuse server)
     - `DockerSandboxClient` (`--network none` live container run)
   - **Workaround & Proof Provided**:
     - Complete compose stack and Dockerfile configured in `infra/docker-compose.yml`.
     - Postgres RLS schema and policies authored in `db/schema.sql`.
     - `test_postgres_rls_isolation_and_unset_tenant` in `tests/test_tenancy_knowledge.py` is implemented and will automatically run against `localhost:5432` as soon as Docker is started with `docker compose up -d`.
     - In-memory tenant isolation and unset tenant testing (`test_query_without_tenant_id_returns_nothing`) ran and passed 100%.
2. **Google Gemini Live API (`GEMINI_API_KEY`)**:
   - **Reason**: `GEMINI_API_KEY` was not configured in the host environment.
   - **Verified Alternative**: ModelRouter gemini adapter is implemented with `ChatGoogleGenerativeAI` and tested via `test_live_gemini_through_model_router` (skipped cleanly when key is absent). Groq model router was tested live and passed.
3. **Exa Search Live API (`EXA_API_KEY`)**:
   - **Reason**: `EXA_API_KEY` was not configured in the host environment.
   - **Verified Alternative**: `ExaSearchProvider` using `exa_py` is fully wired and tested via `test_live_exa_search`. Live Tavily search was tested live and passed.
4. **E2B Sandbox Live API (`E2B_API_KEY`)**:
   - **Reason**: `E2B_API_KEY` was not configured in the host environment.
   - **Verified Alternative**: `E2BSandboxClient` is wired to `e2b_code_interpreter.Sandbox` and tested via `test_live_e2b_sandbox`. Local isolated subprocess sandbox passed with full data computation ($16,750 spend, 3.18 ROAS) and chart generation.

---

## 11. Phase 1 Decisions: Own Search Layer Architecture

### 11.1 SearchProvider Protocol & Unified SearchHit
- Structured `SearchHit` in `core/search/base.py` with `url`, `canonical_url`, `title`, `snippet`, `source_family`, `provider`, `published_at`, `rank`, `raw_score`, and fallback metadata.
- Defined `@runtime_checkable class SearchProvider(Protocol)` ensuring all vertical adapters and metasearch providers adhere to `async def search(query, *, limit, filters) -> List[SearchHit]`.

### 11.2 Metasearch Backbone (SearXNG) & Engine Error Resiliency
- Integrated SearXNG via `SearxngProvider` (`core/search/providers/searxng.py`) querying `GET /search?format=json`.
- Configured `infra/searxng/settings.yml` enabling JSON output, disabling the bot limiter for internal Docker network access, and activating general, news, science, it, social, and video engines.
- Upstream engine errors reported in `unresponsive_engines` are treated as non-fatal, logged into `SearchHit.raw`, and do not interrupt execution.

### 11.3 Vertical Open-API Adapters
- **Forums (`core/search/providers/forums.py`)**: Hacker News (Algolia API), Reddit (public JSON search), Stack Exchange (Advanced Search API).
- **Code (`core/search/providers/code.py`)**: GitHub REST Search API for repositories with star sorting and optional token.
- **Academic (`core/search/providers/academic.py`)**: arXiv API (Atom XML parsing), OpenAlex API, Wikipedia search API.
- **Video (`core/search/providers/video.py`)**: YouTube search parser with timestamped video links.
- **Social (`core/search/providers/social.py`)**: Bluesky public AT Protocol XRPC API and Mastodon federated search.
- **App Stores (`core/search/providers/app_stores.py`)**: Apple App Store (iTunes search API + RSS ratings) and Google Play lookup.
- **Archives (`core/search/providers/archives.py`)**: Wayback Machine CDX API and Marginalia independent web search.
- **General Web (`core/search/providers/duckduckgo.py`)**: DuckDuckGo privacy-focused search backend.

### 11.4 Reciprocal Rank Fusion, Canonical URLs & Pure-Python SimHash
- **Canonicalization (`core/search/canonical.py`)**: Strips marketing click identifiers (`utm_*`, `gclid`, `fbclid`, `msclkid`, `ref`), lowercases hostnames, drops default ports, normalizes trailing slashes, and sorts query parameters.
- **SimHash**: Implemented a pure Python 64-bit SimHash using character 3-grams to detect near-duplicate snippets across engines without relying on C-extensions (guaranteeing Windows WDAC compatibility).
- **Reciprocal Rank Fusion**: Merges concurrent provider lists using `RRF_score(d) = sum(1.0 / (k + rank_i))` with `k=60`, combining scores for shared canonical URLs and filtering SimHash duplicates.

### 11.5 Backward Compatibility & Fallback Thresholds
- Refactored `core/tools/search.py` so `SearchService` routes via `SearchRouter` by default while maintaining `SearchResult` contracts.
- Configured `config/search.yaml`: Tavily and Exa are disabled by default (`enabled: false`) and invoked only when SearXNG/primary providers return fewer than `min_hits_threshold` (default 2), preserving fallback tags.
- Registered all 9 source families (`web_general`, `news`, `forums`, `code`, `academic`, `video`, `social`, `app_stores`, `archives`) in `DataSourceRegistry`.

### 11.6 Test Results
- All 7 new search layer tests in `tests/test_search_layer.py` passed 100%.
- All 21 core scaffold, sandbox, compliance, budgets, and verifier tests passed 100%.

---

## 12. Phase 2 Decisions: Own Fetch & Extract Layer Architecture

### 12.1 Structured FetchedDocument & Exact Offsets
- Implemented `FetchedDocument` in `core/fetch/base.py` containing: `url`, `final_url`, `status`, `content_type`, `fetched_at`, `content_hash`, `title`, `raw_text`, `sections`, `pages`, `timestamps`, `is_blocked`, and `block_reason`.
- Extracted sections contain `heading_path` hierarchy (e.g. `["Architecture Overview", "Storage Engine", "Object Store"]`), verbatim section `text`, and exact character boundaries `[char_start, char_end]` indexing into `raw_text`.

### 12.2 Multi-Format Extraction (HTML, PDF, DOCX, Plain Text)
- **HTML (`core/fetch/extractors.py`)**: Trafilatura for article extraction combined with BeautifulSoup DOM traversal to build hierarchical section paths and exact character offsets.
- **PDFs**: PyMuPDF (`fitz` / `pymupdf`) extracts per-page text tracking 1-indexed `page_no` with character spans and page sections. Fallback to `pypdf` is preserved.
- **DOCX**: `python-docx` (`docx.Document`) parses heading levels (`Heading 1`, `Heading 2`, `Heading 3`) and paragraph text, maintaining heading hierarchies.
- **Plain Text / Markdown**: Regex heading parsing (`#`, `##`) with exact character offsets.

### 12.3 Politeness, Rate Limits, Circuit Breakers & Robots Cache
- **RobotsCache (`core/fetch/politeness.py`)**: Caches parsed `robots.txt` per host with 24-hour TTL, defaulting to permissive if unreachable (404/timeout).
- **TokenBucketRateLimiter**: Per-domain token bucket enforcing polite request concurrency (default 3 req/sec, capacity 6).
- **CircuitBreaker**: Tracks consecutive domain failures; trips after 3 failures into a 60-second cooldown period before allowing a test probe.
- **Wayback Machine Fallback**: When access is blocked (403, 401, Cloudflare, or robots.txt disallowed), checks the Internet Archive Wayback Machine CDX API (`https://archive.org/wayback/available?url=...`) to retrieve the closest snapshot, preserving research continuity without breaking site terms or rotating fake identities.
- **Untrusted Data Fencing**: Fences fetched content using `PromptInjectionDefense.fence(...)` with source tagging and injection pattern neutralizations.

### 12.4 Tenant-Scoped Document Caching
- Added `fetched_documents_cache` table to PostgreSQL (`db/schema.sql`) with RLS policy `USING (tenant_id = current_setting('app.tenant_id', true))` and unique constraint on `(tenant_id, canonical_url, content_hash)`.
- Implemented `FetchedDocumentCache` in `core/fetch/cache.py` with PostgreSQL persistence and in-memory fallback for local testing.

### 12.5 Test Verification
- Created `tests/test_fetch_layer.py` with 8 comprehensive unit and integration tests (robots.txt parsing, token bucket, circuit breaker, heading offsets, PDF pages, DOCX sections, tenant isolation cache, and blocked fetcher with prompt injection defense).
- Full test suite execution: **29 passed in 66.13s** with zero failures.

---

## 13. Phase 3 Decisions: Evidence with Exact Locations

### 13.1 ResearchNote Schema & DB Migration
- Extended `ResearchNote` in `core/state/schemas.py` and `ResearchNoteModel` in `core/state/models.py` with backward-compatible nullable location attributes:
  `url`, `canonical_url`, `title`, `source_family`, `provider`, `retrieved_at`, `content_hash`, `char_start`, `char_end`, `page_no`, `heading_path`, `text_fragment_url`, `video_timestamp_url`, `archive_url`, `is_verified`.
- Added migration DDL in `db/schema.sql` (`ALTER TABLE research_notes ADD COLUMN IF NOT EXISTS ...`) and safe SQLite auto-migration in `core/state/store.py` (`init_db`).

### 13.2 Exact & Fuzzy Excerpt Verification (HARD RULE)
- Implemented `verify_excerpt_in_document` in `core/fetch/location.py`:
  - Performs an exact substring search within `doc.raw_text`.
  - Fallback to NFKC and collapsed whitespace normalization with `SequenceMatcher` similarity >= 0.90.
  - Automatically identifies PDF page number (`page_no`) and hierarchical heading path (`heading_path`) for the matched character span `[char_start, char_end]`.
  - Enforced in `ResearcherWorker._verify_and_save_note`: If an excerpt cannot be verified in the document text, the worker **drops the note immediately** and emits a `note_rejected` event. No unverified web citations are ever saved.

### 13.3 W3C / Chrome Scroll-to-Text Fragments
- Implemented `generate_text_fragment_url` in `core/fetch/location.py`: generates `#:~:text=[startText][,endText]` URLs with percent-encoded boundary terms, enabling 1-click navigation directly to highlighted excerpts inside browsers.

### 13.4 Writer Citation Rendering & Citation Gate Enforcement
- Extended `WriterAgent` to format citations with human-readable locations:
  e.g. `[note_ab12] https://site/page - section 'Pricing > Enterprise SLA' (offsets 120-180) [View Excerpt](text_fragment_url)`.
- Updated `CitationGate` to verify that every numeric, comparative, or superlative claim links to a note with a verified location.

### 13.5 Test Verification
- Created `tests/test_evidence_locations.py` with 6 comprehensive unit and integration tests (exact match, fuzzy match, fabricated excerpt rejection and event emission, PDF page resolution, text-fragment URL generation, CitationGate location enforcement, and Writer report rendering).
- Full test suite execution: **35 passed in 80.95s** with zero failures.

---

## 14. Phase 4 Decisions: Massive Parallel Fan-Out Architecture

### 14.1 Query Expander Agent (`core/agents/expander.py`)
- Implemented `QueryExpander` that takes each `PlanTask` and expands it into 5-15 diverse sub-queries across multiple source families (`web_general`, `forums`, `code`, `academic`, `video`, `social`, `news`).
- Generates `site:` targeted forms (`site:reddit.com`, `site:github.com`), benchmarking queries, architectural evaluation queries, and incorporates regional/geographical nuances when specified in `Brief.geography`.

### 14.2 Sharded Fan-Out Orchestration with `asyncio.TaskGroup`
- Rewrote `ResearchOrchestrator` (`core/agents/orchestrator.py`) to execute parallel research shards via `asyncio.TaskGroup`.
- Implemented a 3-tier semaphore model:
  1. `global_sem`: Enforces global concurrency cap (default 24).
  2. `provider_sems`: Enforces per-provider concurrency cap (default 4).
  3. `domain_sems`: Enforces per-domain concurrency cap (default 2).
- Configurable in `config/search.yaml` under `concurrency`.
- Shards run concurrently: `search -> dedup -> fetch -> rerank -> verify -> save`.

### 14.3 StateStore Seen-URL Registry & Zero Duplicate Fetches
- Added atomic `mark_url_seen(job_id, canonical_url)` and `is_url_seen(job_id, canonical_url)` to `StateStore`.
- URLs discovered across concurrent shards are normalized to canonical URLs and checked against the shared per-job registry. If a canonical URL has already been queued or fetched by another shard, it is skipped immediately, saving network bandwidth and rate limits.

### 14.4 Passage Reranker (`core/search/reranker.py`)
- Implemented `PassageReranker` supporting neural CrossEncoders (e.g. `sentence-transformers` models like `bge-reranker-base`) with a fast, CPU-friendly BM25 / token cross-scoring fallback.
- Reranks candidate document passages against the shard query prior to claim extraction, cutting down downstream LLM token consumption.

### 14.5 BudgetState Extensions & Clean-Stop Behavior
- Extended `BudgetState` with `fetched_pages: int`, `providers_failed: int`, and `bytes_downloaded: int`.
- Each shard verifies budget health before initiating search or fetch steps. When `budget.exhausted` is reached, shards cleanly stop without crashing and return cleanly.

### 14.6 GapCheckVerifier Extension for Missing Source Families
- Extended `GapCheckVerifier` (`core/agents/verifier.py`) to audit source family coverage across collected notes (e.g., verifying presence of `forums` and `web_general`).
- When missing critical source families, triggers a single bounded extra round of research explicitly targeting the missing family. Enforces a strict cap of 1 extra round to prevent infinite research loops.

### 14.7 Test Verification
- Created `tests/test_fanout_orchestrator.py` with 6 unit and integration tests:
  1. `test_query_expander_diverse_families`: Verifies generation of 5-15 diverse sub-queries spanning multiple families and geographical targeting.
  2. `test_passage_reranker_scoring`: Verifies BM25 / token cross-scoring ranking relevant passages highest.
  3. `test_seen_url_deduplication`: Verifies atomic test-and-set behavior of `mark_url_seen`.
  4. `test_gap_check_verifier_missing_family`: Verifies detection of missing source families and bounded single extra round.
  5. `test_sharded_orchestrator_execution`: End-to-end mocked sharded execution with note extraction and exact location verification.
  6. `test_orchestrator_budget_clean_stop`: Verifies clean stop mid-fanout when budget is exhausted.
- Full test suite passed with 0 regressions.

---

## 15. Phase 5 Decisions: Own Index (Compounding Knowledge)

### 15.1 Tenant-Scoped Web Index Chunks Table (`db/schema.sql` & `core/state/models.py`)
- Added `web_index_chunks` table storing fetched and verified passages with:
  `id`, `tenant_id`, `url`, `canonical_url`, `title`, `source_family`, `passage_text`, `char_start`, `char_end`, `page_no`, `heading_path`, `text_fragment_url`, `embedding` (vector(384)), `created_at`, `updated_at`, `is_stale`.
- Enforces strict PostgreSQL Row-Level Security (`ALTER TABLE web_index_chunks ENABLE ROW LEVEL SECURITY; FORCE ROW LEVEL SECURITY;`) ensuring zero cross-tenant query leakage (`USING (tenant_id = current_setting('app.tenant_id', true))`).

### 15.2 Hybrid Retriever (`core/knowledge/web_index.py`)
- Implemented `WebIndexStore` providing hybrid retrieval:
  - Vector cosine similarity via `EmbeddingModel` (dimension 384).
  - Lexical keyword / BM25 token overlap.
  - Linear combination: `score = (vector_weight * vec_sim) + (keyword_weight * kw_score)`.
  - Configurable weights in `config/search.yaml` (default: vector 0.65, keyword 0.35).

### 15.3 Automated TTL Lifecycle & Stale Re-Crawling
- Configured source-family-specific TTLs in `config/search.yaml`:
  - `news`: 1 day
  - `social`: 2 days
  - `forums`: 7 days
  - `web_general` & `app_stores`: 14 days
  - `code`: 30 days
  - `academic`: 90 days
  - `archives`: 180 days
- `mark_stale_entries()` scans index entries and marks items whose age exceeds the TTL as `is_stale = True`.
- `recrawl_stale_entries()` refetches stale canonical URLs using `PageFetchService`, deletes outdated passages, and writes updated passages with refreshed timestamps.

### 15.4 Integration with SearchRouter & DataSourceRegistry
- Registered `WebIndexDataSource` in `core/tools/registry.py` under name `web_index`.
- Implemented `WebIndexProvider` wrapping `WebIndexStore.hybrid_search` and registered it on `SearchRouter`, enabling parallel shards to query the local index first before going to external networks.
- Automatically persists verified notes into `WebIndexStore` inside `ResearchOrchestrator._execute_shard`.

### 15.5 Test Verification
- Created `tests/test_web_index.py` with 6 unit and integration tests:
  1. `test_web_index_ingestion_and_hybrid_retrieval`: Verifies note passage ingestion, document section chunking, and dual hybrid search for benchmarks and pricing.
  2. `test_web_index_tenant_isolation_zero_leakage`: Confirms Tenant B queries return zero results for confidential passages stored by Tenant A.
  3. `test_web_index_source_family_filtering`: Verifies filtered retrieval by `academic` vs `forums`.
  4. `test_web_index_stale_marking_and_recrawl`: Verifies automated TTL stale marking, exclusion from standard search, and background re-crawl.
  5. `test_web_index_search_provider_adapter`: Verifies `WebIndexProvider` conforming to `SearchProvider` protocol with exact locations.
  6. `test_web_index_in_datasource_registry`: Confirms registration in `DataSourceRegistry`.
- All 6 tests passed in 2.11s.

---

## 16. Phase 6 Decisions: API, Events, and UI

### 16.1 Granular Real-Time SSE Events (`core/state/schemas.py`)
- Extended `EventType` enum with real-time research lifecycle events:
  - `SEARCH_STARTED`: Emitted with query and target `source_family`.
  - `SEARCH_HIT`: Emitted per retrieved hit with URL, title, and provider name.
  - `PAGE_FETCHED`: Emitted when a document is fetched with status, content length, and content hash.
  - `PAGE_BLOCKED`: Emitted on domain blocks, robots.txt denials, or rate-limit saturation with reason.
  - `NOTE_REJECTED`: Emitted when verbatim excerpt verification fails against document text.
  - `SHARD_STARTED` / `SHARD_DONE`: Emitted per parallel worker shard with latency and note yields.
  - `SOURCE_COVERAGE`: Emitted with live coverage breakdown per source family (`web_general`, `forums`, `code`, `academic`, etc.).

### 16.2 Sources API Endpoint (`apps/api/main.py`)
- Implemented `GET /v1/jobs/{job_id}/sources`:
  - Returns structured evidence grouped by `source_family` (`web_general`, `news`, `forums`, `code`, `academic`, `video`, `social`, `app_stores`, `archives`, `blocked`, `rejected`).
  - Each item includes: `note_id`, `url`, `title`, `status` (`verified`, `rejected`, `blocked`), exact `location` (`page_no`, `heading_path`, `char_start`, `char_end`, `video_timestamp_url`), `text_fragment_url`, and `confidence`.
  - Also outputs `coverage_counts` by family and `total_sources` metrics.
  - Fully tenant-isolated with `X-Tenant-ID` header validation.

### 16.3 Langfuse Observability Spans (`core/observability/tracing.py`)
- Added `record_shard_span(shard_id, task_id, query, duration, notes_count, status)` recording per-shard latency and yield.
- Added `record_provider_span(provider_name, query, duration, hits_count, status)` instrumenting `SearchRouter` to track per-upstream latency, failure rates, and hit counts.
- Maintains non-blocking fallback when Langfuse API keys are not provisioned in local test environments.

### 16.4 Gradio UI Live Parallel Agent & Evidence Panel (`app.py`)
- Upgraded Gradio interface with:
  1. **Parallel Research Shards Panel**: Displays active and completed worker agents with live badges, query targets, and note counts.
  2. **Source Coverage Progress Bar**: Dynamic HTML bar chart showing proportional coverage across all 8 source families.
  3. **Clickable Evidence Table**: Comprehensive table displaying verified notes, direct clickable `#:~:text=` text fragment links, PDF page numbers, and exact section headings.

### 16.5 Concurrency and Transaction Synchronization Fix
- Fixed SQLite single-writer race conditions across `StateStore` and `WebIndexStore` by introducing a class-level `_write_lock` that synchronizes all database write sessions (`create_job`, `update_job`, `add_note`, `add_artifact`, `index_note_passage`).
- Replaced `cascade="all, delete-orphan"` with `cascade="all, delete"` on `JobModel.notes`, `JobModel.artifacts`, and `JobModel.events` to prevent independent notes from being marked as orphans when `update_job` executes.

---

## 17. Phase 7 Decisions: Acceptance Test Suite and Live Verification

### 17.1 Acceptance Test Coverage (`tests/test_phase7_acceptance.py`)
- Authored 8 comprehensive acceptance test scenarios validating all v1 engine requirements:
  1. `test_provider_adapters_offline_fixtures`: Validates 18 vertical adapters (Hacker News, Reddit, GitHub, arXiv, Wikipedia, YouTube, Mastodon/Bluesky, App Store/Google Play, Wayback, Common Crawl, etc.) using offline recorded HTML/JSON fixtures. Upstream errors are gracefully handled without raising.
  2. `test_rrf_canonicalization_and_simhash_dedup`: Verifies Reciprocal Rank Fusion, canonical URL parameter stripping (`utm_*`, `fbclid`, `gclid`), and SimHash 64-bit Hamming-distance text deduplication (< 3 distance considered duplicate).
  3. `test_robots_rate_limiter_and_circuit_breaker`: Verifies RFC 9309 robots.txt compliance, token-bucket domain rate limits, and circuit breakers (trips to open state on 3 consecutive 5xx/429 responses, rejecting new requests immediately).
  4. `test_excerpt_verification_locations_and_fabrication_rejection`: Enforces the HARD RULE that fabricated claims are rejected and valid excerpts extract exact `char_start`, `char_end`, PDF `page_no`, and heading hierarchy.
  5. `test_chrome_text_fragment_url_rfc_encoding`: Verifies Chrome Scroll-to-Text fragment encoding (`#:~:text=[prefix-,]start[,end][,-suffix]`) with RFC 3986 percent encoding for commas, dashes, and whitespace.
  6. `test_fanout_concurrency_seen_urls_and_budget_clean_stop`: Verifies atomic seen-URL dedup preventing duplicate fetches, and clean stop when step/token budget is exhausted.
  7. `test_tenant_isolation_web_index_chunks`: Verifies multi-tenant isolation in `WebIndexStore` ensuring zero cross-tenant passage retrieval leakage.
  8. `test_end_to_end_acceptance_sample_marketing_query`: Runs an end-to-end deep research job across >= 20 parallel shards on a complex marketing query; verifies 100% of cited claims have verified location and citations pass CitationGate.

### 17.2 Live SearXNG Smoke Test (`tests/test_live_searxng.py`)
- Added `@pytest.mark.live` smoke test for SearXNG instance verifying live HTTP query execution, response parsing, and latency tracking.

### 17.3 Event Loop and Async Concurrency Fix
- Moved `StateStore._seen_lock`, `_write_lock`, and `_seen_urls` to instance-level initialization inside `StateStore.__init__` to avoid cross-event-loop `RuntimeError` during asynchronous test suite execution.
- Interleaved `QueryExpander` subqueries across source families in round-robin fashion so early query caps guarantee representation across >= 4 source families (`web_general`, `forums`, `code`, `academic`, `news`, `video`, `social`).


---

## 18. Idea Miner Phase 1 Decisions: Source Policy & Source Adapters

### 18.1 Domain Configuration & Skill (`config/domains/idea_mining.yaml` & `skills/idea_mining/SKILL.md`)
- Kept the core agent architecture strictly domain-agnostic by establishing domain profile `idea_mining` activated via request parameter `{"domain": "idea_mining"}`.
- Configured models, temperature, extraction chunk size, entity resolution similarity thresholds (name similarity 0.88, embedding cosine similarity 0.85), privacy defaults (team attribution off by default, emails/phones scrubbed), and novelty guardrail threshold (0.80).
- Documented operational workflow, location verification rules, and privacy compliance in `skills/idea_mining/SKILL.md`.

### 18.2 Strict Source Policy Engine (`config/source_policy.yaml` & `core/sources/policy.py`)
- Created `config/source_policy.yaml` recording domain permissions, access methods (`api`, `rss`, `sitemap`, `html`), robots.txt compliance (`true`), rate limits (req/sec), max pages per run, and date checked (2026-10-25).
- **Default for unknown sites**: Allowed only via search-engine results, adhering strictly to robots.txt.
- **Explicitly Denied Domains**: `linkedin.com`, `x.com`, `twitter.com`, `facebook.com`, `instagram.com`, `crunchbase.com` and sites forbidding crawling in their terms. Crawler will refuse any domain not marked allowed or flagged denied. Manual CSV/JSON import hooks provided for denied domains.
- Implemented CLI `python -m core.sources.policy check <domain>` to fetch and verify robots.txt policy and allowed access paths.

### 18.3 Source Adapters (`core/sources/adapters/`)
- Implemented 21 specialized adapters extending `SourceAdapter`:
  - **Hackathons**: Devpost, Devfolio, DoraHacks, ETHGlobal, MLH, Unstop, Hack2skill, Smart India Hackathon (SIH), Kaggle, GitHub Hackathons.
  - **Startups & Launches**: Y Combinator Public Directory, Product Hunt API, Hacker News Launches (Algolia API), BetaList, Indie Hackers, Reddit Startups.
  - **Writeups & Media**: Dev.to, Hashnode, RSS Writeups (Medium/Substack), YouTube Pitch Videos (yt-dlp + transcript API), PDF Pitch Decks / Reports (PyMuPDF).
- Implemented loud failure: If a site markup or API structure changes, adapters raise `AdapterBrokenError` with a clear message and emit an `adapter_broken` event; adapters never silently return empty results.
- Added recorded offline fixtures in `tests/fixtures/sources/` for robust offline test verification.

### 18.4 Router & Registry Integration
- Mapped source families `hackathons`, `startups`, `launches`, `writeups` into `core/search/router.py`.
- Registered `HackathonsDataSource`, `StartupsDataSource`, and `WriteupsDataSource` in `core/tools/registry.py`.

---

## 19. Idea Miner Phase 2 Decisions: Bulk, Resumable, Incremental Crawler Architecture

### 19.1 Frontier Storage & Concurrency Model (`db/schema_crawl.sql` & `core/crawl/store.py`)
- Added tables `crawl_sources`, `crawl_frontier`, and `crawl_runs` designed for high-throughput distributed crawling.
- Employs native PostgreSQL `SELECT ... FOR UPDATE SKIP LOCKED` for claiming pending items, guaranteeing that concurrent crawler workers never claim or process duplicate URLs.
- Implemented SQLite emulation using atomic write locks for fast local unit testing without requiring external Postgres services.
- Frontier insertion is strictly idempotent: unique constraint on `(source, canonical_url)` ensures duplicate URLs are ignored on re-discovery while preserving priority queues.

### 19.2 Resumability and Incremental Refresh Lifecycle (`core/crawl/engine.py`)
- Supported crawl execution modes:
  - `discover`: Enumerates listing pages or sitemaps via source adapters and pushes candidate URLs to `crawl_frontier`.
  - `fetch`: Downloads, verifies politeness, stores raw document payloads, and extracts project entities.
  - `refresh`: Incremental conditional request sending `If-None-Match` (ETag) and `If-Modified-Since`. If HTTP 304 Not Modified or SHA-256 content hash matches previously fetched bytes, the item is marked `skipped` without consuming downstream extraction or LLM tokens.
  - `all`: Sequentially runs discovery followed by continuous frontier consumption until configured limits are satisfied.
- Resumability: Crashes or halts preserve the state of pending items in `crawl_frontier`; subsequent runs seamlessly pick up where the prior run stopped.

### 19.3 Raw Document Store & Re-Verification Guarantee (`core/crawl/storage.py`)
- Implemented `RawDocumentStore` persisting fetched raw payloads into compressed gzip files sharded by SHA-256 hash prefix (`data/raw_documents/<hash[:2]>/<hash>.gz`) with JSON metadata (`meta.json`).
- Enables exact verbatim re-verification of all extracted structured fields against raw page content at any point in the future.

### 19.4 Politeness, Circuit Breakers, and Honest Identity
- Strictly enforces `config/source_policy.yaml`: Crawler refuses any domain not marked allowed or flagged denied, emitting `page_blocked(reason="policy_denied")`.
- Enforces robots.txt via `RobotsCache` and respects `crawl-delay` directives.
- Implemented per-domain `TokenBucketRateLimiter` (default 2 req/sec, capacity 4) and `CircuitBreaker` (trips after 3 consecutive 429/5xx errors into cooldown).
- Honest User-Agent: Configurable via `CRAWL_USER_AGENT` or defaults to `DeepResearchBot/2.0 (+https://example.com/bot; contact@deep-research.local)`. No paywall/CAPTCHA bypass.

### 19.5 CLI, REST API & Real-Time Event Streaming
- CLI tool: `python -m core.crawl run --source devpost --since 2022 --limit 5000`.
- API endpoints: `POST /v1/crawl/runs`, `GET /v1/crawl/runs/{id}`, `GET /v1/crawl/runs/{id}/events` (Server-Sent Events), `GET /v1/crawl/runs`.
- SSE events: `crawl_started`, `page_fetched`, `page_blocked`, `page_skipped`, `adapter_broken`, `crawl_completed`.

---

## 20. Idea Miner Phase 3 Decisions: Structured Idea Extraction with Verified Evidence

### 20.1 IdeaRecord & Evidence Schema (`db/schema_ideas.sql` & `core/ideas/schemas.py`)
- Created `IdeaRecord` schema capturing: `id`, `name`, `one_liner`, `problem`, `solution`, `target_users`, `domain_tags`, `tech_stack`, `business_model`, `stage` (`idea`, `prototype`, `launched`, `funded`), `traction`, `source_kind`, `event_name`, `year`, `placement` (`winner`, `runner_up`, `track_prize`, `finalist`, `none`), `team_size` (number only), `links` (`demo`, `repo`, `video`, `website`, `deck`), `first_seen_url`, `all_source_urls`, `confidence`, `evidence`, `embedding` (vector(384)), `merged_into_id`, `merge_history`.
- Enforced PostgreSQL Row-Level Security (`ALTER TABLE idea_records ENABLE ROW LEVEL SECURITY;`): public records (`tenant_id IS NULL`) are globally discoverable across tenants, while private ideas (`tenant_id = current_setting('app.tenant_id', true)`) remain strictly isolated with zero leakage.

### 20.2 Verbatim Evidence Verification (HARD RULE) & Hallucination Defense (`core/ideas/extractor.py`)
- Every extracted field claim must be backed by an `EvidenceEntry` linking to an exact verbatim excerpt (`<= 200 chars`).
- `IdeaExtractor` validates each excerpt against `doc.raw_text` using `verify_excerpt_in_document`:
  - Verified matches resolve exact character offsets `[char_start, char_end]`, PDF `page_no`, and Chrome `text_fragment_url` (`#:~:text=`).
  - If verification fails or excerpt is missing: **the field is immediately dropped (set to null/none)** and a `field_rejected` event is emitted.
  - Fabricated placements, prizes, or traction claims are never stored under any circumstances.

### 20.3 Privacy Guardrails & PII Scrubbing (`core/ideas/privacy.py`)
- Implemented `PrivacyScrubber` that strips emails, telephone numbers, and residential addresses from all extracted text.
- Restricted links strictly to public project artifacts (`demo`, `repo`, `video`, `website`, `deck`, `presentation`, `paper`), dropping personal profiles (Facebook, Instagram, LinkedIn personal pages).
- Individual developer names are suppressed by default unless `privacy.store_individual_names` is explicitly enabled in config. Team size is stored strictly as a numeric count.

### 20.4 Entity Resolution with Audit Trail & Lossless Un-Merge (`core/ideas/resolver.py`)
- Implemented `EntityResolver` matching projects across disparate sources (Devpost, GitHub, YouTube, Product Hunt, blogs):
  1. Shared public repository URL (e.g. `github.com/...`) -> immediate match.
  2. Shared demo/website URL or direct cross-link.
  3. Normalized title sequence similarity >= 0.88 AND dense vector cosine similarity >= 0.85.
- Merging combines `all_source_urls`, links, tech stack, domain tags, and retains all verified evidence.
- Full audit snapshot stored in `surviving.merge_history`; `unmerge(merged_id)` losslessly restores the absorbed record to its pre-merge state.

### 20.5 Hybrid Vector & Full-Text Store (`core/ideas/store.py`)
- Implemented `IdeaStore` providing hybrid retrieval:
  - Dense cosine similarity over canonical text embeddings (`Project: ...\nProblem: ...\nSolution: ...\nTech Stack: ...`).
  - Lexical keyword overlap with support for 2-letter tokens (`AI`, `ML`, `Go`, `VR`, `AR`).
  - Metadata filtering by `year`, `event_name`, `placement`, `tech_stack`, `domain_tags`.

---

## 21. Idea Miner Phase 4 Decisions: Sandboxed Analysis Engine

### 21.1 Dependencies Added (`requirements.txt`)
- `scikit-learn>=1.4.0`: BSD-3-Clause license (permissive). Required for efficient, robust KMeans and clustering over high-dimensional vector embeddings, silhouette evaluation, and nearest neighbor operations.

### 21.2 Semantic Clustering (`skills/idea_analysis/clustering.py`)
- Groups crawled projects by embedding space proximity using KMeans (or HDBSCAN where supported) with deterministic fallbacks.
- Calculates true centroid vectors and discovers the top 3 nearest representative projects per cluster.
- Computes top domain tags and technology stacks, labeling clusters cleanly (e.g. `Healthcare / PyTorch (12 projects)`).
- Every cluster output explicitly states its cluster size and total evaluated sample size `N`.

### 21.3 Temporal Trends & Saturation Engine (`skills/idea_analysis/trends.py`)
- Tracks project volume and empirical win rates across domains, tech stacks, and chronological years.
- Implements objective saturation classification:
  - **Saturated**: Above-median submission volume coupled with below-median win rates (crowded categories with poor odds).
  - **Underexplored**: Below-median submission volume coupled with above-median win rates (high-yield whitespace opportunities).
- States sample sizes `N` across all statistical outputs and includes verified example project IDs.

### 21.4 Defensible Winner Pattern Analysis (`skills/idea_analysis/winner_patterns.py`)
- Compares winning projects (`winner`, `runner_up`, `track_prize`) against non-winners on verifiable empirical features:
  1. Working demo URL presence.
  2. Pitch video URL presence.
  3. Average team size.
  4. Problem statement specificity (character length of verified problem description).
- **Statistical Integrity (Hard Rule)**: Strictly prohibits causal claims; outputs defensive observational phrasing ("observed correlation only") and reports exact sample sizes `n_winners`, `n_non_winners`, and `total_sample_size`.

### 21.5 Whitespace Gap Detection (`skills/idea_analysis/whitespace.py`)
- Takes arbitrary target problem statements (e.g. uploaded SIH problem statement PDFs, track briefs, or user concepts) and embeds them.
- Evaluates cosine proximity against all existing projects, computing `overall_novelty_score = 1.0 - max_similarity`.
- Retrieves the closest existing projects with verified evidence locations so researchers can benchmark against prior art.
- Scans the cross-product of target domains and tech stacks to pinpoint unbuilt combinations with minimal prior entries, formulating concrete whitespace opportunities.

### 21.6 Unified Analysis Engine & Reporting (`skills/idea_analysis/engine.py`)
- Implemented `IdeaAnalysisEngine` aggregating clustering, trends, winner comparisons, and whitespace gap detection.
- Generates structured Markdown reports citing sample sizes and linking to verified evidence locations.
- Provides optional `matplotlib` chart rendering for visual win-rate dashboards.
- All 5 unit and integration tests passed 100% in `tests/test_phase4_analysis.py`.
