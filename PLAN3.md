# PLAN3.md: Unified Claude-Style Agent with Cloudflare Code Mode & Graph Memory

## Executive Summary
This document establishes the master architectural plan to evolve `deep-research-agent` from a fragmented tab-based UI (Streamlit/Gradio) into a **single, unified AI assistant product**:
- **Interface**: One Claude-style chat interface (Next.js + TypeScript + Tailwind + shadcn/ui) with inline reasoning, live parallel research cards, exact scroll-to-text citation chips, interactive memory graph, and an artifact side drawer.
- **Agent Backend**: A unified LangGraph Main Agent (`core/chat/`) exposing a typed SSE event protocol over `/v1/chat`, with dynamic model routing, tenant-isolated persistence, and human-in-the-loop approval.
- **Tool Architecture**: Cloudflare **Code Mode** (`search` + `execute`) running sandboxed JavaScript in V8 isolates against an OpenAPI-derived typed SDK, with host-level allowlists and credential fencing.
- **Memory Subsystem**: Layered memory (L0 working, L1 episodic, L2 temporal knowledge graph, L3 Obsidian-compatible bidirectional markdown vault, L4 evidence graph).
- **Existing Systems**: Deep research graph, fan-out orchestrator, SearXNG, fetch/verify layer, and Idea Miner crawler/trends are migrated into typed SDK namespaces accessible directly from the single chat box.

---

## 1. Monorepo Directory Layout

```
deep-research-agent/
├── apps/
│   ├── api/                     # FastAPI backend (chat endpoint, SSE streaming, tenant RLS)
│   ├── web/                     # Next.js 14 App Router Claude-style Chat UI
│   └── codemode/                # Cloudflare Worker project (MCP handler, Dynamic Worker isolate)
├── config/
│   ├── models.yaml              # Fast, strong, code roles with provider failover
│   ├── search.yaml              # Search providers and family routing
│   ├── source_policy.yaml       # Domain compliance and crawl allowlists
│   ├── memory_policy.yaml       # Privacy rules, PII filters, and retention policies
│   └── domains/                 # Domain-specific prompts & profiles
├── core/
│   ├── chat/                    # Main Agent (LangGraph), SSE protocol, prompt router, turn manager
│   ├── codemode/                # CodeModeBackend interface (CloudflareBackend vs LocalBackend), gate, audit
│   ├── memory/                  # MemoryService interface (temporal KG, Obsidian sync, hybrid RRF retrieval)
│   ├── agents/                  # Existing multi-agent subgraphs (planner, verifier, writer, analyst)
│   ├── crawl/                   # Existing continuous crawler frontier and engine
│   ├── ideas/                   # Existing idea extraction, resolver, clustering, and generator
│   ├── search/                  # Existing SearXNG and vertical search adapters
│   ├── fetch/                   # Existing tiered fetch and verbatim location extractor
│   ├── guardrails/              # Citation gate, compliance gate, prompt-injection fencing
│   ├── observability/           # Langfuse tracing per chat turn and code execution
│   └── state/                   # PostgreSQL/SQLite schemas and stores
├── db/                          # Migrations (schema_chat.sql, schema_memory.sql, etc.)
├── docs/
│   ├── chat-protocol.md         # SSE event protocol specification
│   ├── adr/
│   │   ├── 0001-ui.md           # Custom Next.js vs LibreChat/OpenWebUI evaluation
│   │   ├── 0002-memory.md       # Graphiti vs Mem0 vs FalkorDB evaluation
│   │   └── 0003-codemode.md     # Cloudflare Code Mode & Dynamic Workers ADR
│   └── benchmarks/
│       ├── codemode.md          # 15-task Code Mode vs all-tools benchmark
│       └── memory.md            # 40-question temporal memory eval
├── legacy/
│   └── app.py                   # Preserved Streamlit/Gradio prototype
├── tests/                       # 120+ unit, integration, gate, memory, and e2e tests
├── vault/                       # Obsidian-compatible plain markdown vault (bidirectional sync)
│   ├── Daily/
│   ├── Ideas/
│   ├── People/
│   ├── Preferences/
│   ├── Projects/
│   ├── Research/
│   └── Sources/
├── .env.example                 # Documented environment variables and API keys
├── docker-compose.yml           # Unified multi-service deployment
├── package.json                 # Monorepo workspace root
└── requirements.txt             # Python 3.12 dependencies
```

---

## 2. Phase-by-Phase Roadmap

### Phase 1: Unified Agent Backend (`core/chat/`)
1. **Main Agent (LangGraph)**:
   - Root decision router: Direct Answer | Use Code Mode Tools | Deep Research Run | Ask Clarifying Question.
   - Context window manager: Rolling summarization for long conversations with intact citation anchors.
   - Support for user turn controls: Stop generation, regenerate turn, edit-and-resubmit (tree branching).
2. **Typed SSE Streaming Protocol (`docs/chat-protocol.md`)**:
   - Event types: `text_delta`, `reasoning_summary`, `tool_call_started`, `tool_call_finished`, `code_execution`, `research_progress`, `citation`, `artifact`, `clarification_request`, `approval_request`, `memory_used`, `memory_write_proposed`, `error`, `done`.
3. **Postgres & Tenant Persistence (`db/schema_chat.sql`)**:
   - Tables: `conversations`, `messages`, `message_parts`, `attachments`, `turn_feedback`, `branches`.
   - Automatic conversation title generation using fast model.
4. **Model Router Roles (`config/models.yaml`)**:
   - Extended with `code` role (optimized for concise, typed JavaScript against `api.*`).
   - Strict untrusted data fencing (`<untrusted_tool_result>`) for all outputs.

### Phase 2: Claude-Style Web Interface (`apps/web/`)
1. **ADR 0001 (`docs/adr/0001-ui.md`)**:
   - Compare Custom Next.js (App Router + shadcn/ui) vs LibreChat vs Open WebUI; select custom Next.js for tight artifact/memory integration.
2. **Layout & Components**:
   - Left Sidebar: History, search, new chat, folders, memory graph shortcut.
   - Center Chat: Streaming markdown, KaTeX math, Mermaid diagrams, expandable code execution blocks, live research card (parallel shards, sources by family, budget meter).
   - Right Drawer: Artifacts (markdown reports, CSV tables, PPTX slides, idea cards) with downloads; Sources drawer with exact location snippets.
   - Inline Cards: Clarification quick-replies, mutation Approval/Deny cards, Memory Used chips with inspector.
   - Incognito chat toggle (disables memory read/write).
3. **Retire `app.py`**:
   - Move old prototype to `legacy/app.py`. Ensure 100% of former capabilities are available in chat.

### Phase 3: Cloudflare Code Mode Tool Layer (`apps/codemode/` & `core/codemode/`)
1. **Worker Service**:
   - Cloudflare Worker implementing `createMcpHandler` from Cloudflare Agents SDK v0.20+ / MCP SDK v2.
   - Exposes `search(code)` and `execute(code)` authenticated by signed JWT tokens.
2. **Catalog & Typed SDK**:
   - Build-time generator reading FastAPI OpenAPI spec and upstream MCP specs, outputting TypeScript declarations (`api.research.*`, `api.ideas.*`, `api.crawl.*`, `api.kb.*`, `api.memory.*`, `api.web.*`, etc.).
3. **Dynamic Sandbox & Security Gate**:
   - Worker Loader (`env.LOADER.load()`) launching isolated V8 dynamic workers with `globalOutbound: null`.
   - Supervisor gate enforcing host allowlist, path allowlist, credential injection, concurrency limits, payload caps, and audit logs.
4. **Backend Abstraction (`CodeModeBackend`)**:
   - `CloudflareBackend`: Remote edge deployment via Cloudflare Worker.
   - `LocalBackend`: Local sandboxed runner for offline development and CI tests on Windows/Linux.
5. **Agent Repair Loop & Benchmarks**:
   - 1-2 turn syntax error feedback loop.
   - 15-task comparative benchmark committed in `docs/benchmarks/codemode.md`.

### Phase 4: Graph Memory (`core/memory/`)
1. **Engine Spike & ADR 0002 (`docs/adr/0002-memory.md`)**:
   - Evaluate Graphiti (`graphiti-core`), Mem0, Cognee, and FalkorDB/Neo4j on Windows + Docker.
   - Select primary engine based on temporal facts (`valid_from`/`valid_to`), entity resolution, and provenance tracking.
2. **Layered Memory Stack**:
   - L0: Working memory (LangGraph checkpoint state + rolling summary).
   - L1: Episodic memory (conversations with embeddings and timestamps).
   - L2: Semantic temporal knowledge graph (entities, relations, facts, contradictions).
   - L3: Obsidian vault (`./vault` markdown files with YAML frontmatter, `[[wikilinks]]`, and `watchfiles` bidirectional sync).
   - L4: Evidence graph (links between memories and verified `ResearchNote`/`IdeaRecord` anchors).
3. **Memory Tools & Policy**:
   - `memory.recall`, `memory.remember`, `memory.forget` (hard-delete across graph, vector, and vault).
   - `config/memory_policy.yaml`: PII blacklist (passwords, payment details, SSN, healthcare).
   - Nightly consolidation and community summarization.
   - 40-question benchmark committed in `docs/benchmarks/memory.md`.

### Phase 5: Existing Features Migration into SDK
- Expose all existing core capabilities through typed endpoints and SDK methods:
  - `api.research.deep(query, mode, max_shards)`
  - `api.ideas.search(query, domain, tech, placement)`
  - `api.ideas.generate(brief)`
  - `api.crawl.start(source, mode, limit)`
  - `api.kb.upload(file)` & `api.kb.search(query)`
  - `api.analytics.ga4(query)` & `api.analytics.hubspot(query)`

### Phase 6: Observability, Evals & Test Suite
- Comprehensive test coverage:
  - `tests/test_chat_protocol.py`: SSE event schema validation.
  - `tests/test_chat_router.py`: Routing decisions on 30 sample prompts.
  - `tests/test_codemode_gate.py`: Host allowlist, secret leak prevention, mutation blocking, timeout enforcement.
  - `tests/test_memory_graph.py`: Temporal facts, contradiction invalidation, hard forget, Obsidian file sync.
  - `tests/test_e2e_chat.py`: End-to-end chat turn flow with citation click-through and memory integration.
- Langfuse trace spans per turn, tool invocation, and code execution.

### Phase 7: Run & Deploy
- `docker-compose.yml`: postgres+pgvector, graph DB (FalkorDB/Neo4j), minio, searxng, langfuse, api, web.
- `apps/codemode/wrangler.jsonc` deployment configuration.
- Updated `README.md` with full Mermaid architecture diagram and 10-minute setup guide.

---

## 3. Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Cloudflare Paid Plan required for Dynamic Workers in cloud | High | Implement dual `CodeModeBackend` (`CloudflareBackend` + `LocalBackend`). CI and local development run 100% offline via `LocalBackend`. |
| Event loop conflicts in Python async callers | Medium | Strictly use `run_coro` / clean task management; no global `nest_asyncio` monkey patching that breaks Uvicorn/Starlette. |
| Bidirectional vault sync conflicts | Medium | Human edits in Obsidian always win. File watcher debouncing (1s) and explicit conflict file emission (`note.conflict.md`) on ambiguous collisions. |
| Prompt injection via untrusted tool outputs | Critical | Strict `<untrusted_tool_result>` XML fencing on all responses from web search, fetch, and Code Mode executions. |
| Model code errors in JavaScript | Medium | Automated repair loop: syntax and runtime errors are fed back to the code model up to 2 times before falling back. |

---

## 4. Open Questions & Resolution Paths

1. **Graph Database Engine**: Primary target is `FalkorDB` (Redis-based, high performance, clean Cypher) or `Neo4j Community`, while keeping memory engine behind the `MemoryService` abstraction.
2. **Web Framework Chat Primitives**: Evaluate `assistant-ui` vs Vercel AI SDK vs native custom React hooks; customize with our typed SSE protocol adapter.
