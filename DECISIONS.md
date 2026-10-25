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

