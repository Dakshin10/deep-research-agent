# Architecture & Upgrade Plan: Massively Parallel Multi-Source Web Research Engine

## Executive Overview
This document outlines the architectural plan to upgrade `deep-research-agent` from a Tavily/Exa-dependent prototype into a self-hosted, massively parallel, multi-source research engine.

The system will preserve:
- The existing 13-stage LangGraph workflow.
- `ResearchNote` contract and strict multi-tenancy Row-Level Security (RLS).
- Citation gate, compliance gate, and prompt-injection defenses.
- Persistent LangGraph checkpointing on SQLite/PostgreSQL.
- All existing tests and SSE telemetry streaming.

The system will add:
- A self-hosted metasearch backbone (SearXNG) and 10+ vertical open-API adapters.
- Reciprocal Rank Fusion (RRF), URL canonicalization, and SimHash near-duplicate deduplication.
- A tiered fetching layer (HTTPX -> Crawl4AI -> Playwright fallback) with PyMuPDF page tracking and Trafilatura article extraction.
- Strict robots.txt politeness, per-domain token buckets, and circuit breakers.
- Verifiable evidence with exact character offsets, section headings, PDF page numbers, and Chrome text-fragment URLs (`#:~:text=`).
- A Query Expander agent fanning out into sharded parallel workers (`asyncio.TaskGroup`) with cross-encoder passage reranking.
- A compounding tenant-scoped web index stored in PostgreSQL with pgvector embeddings and full-text search.
- Extended SSE events, `GET /v1/jobs/{id}/sources` endpoint, and upgraded Gradio UI with a real-time shard execution panel.

---

## 1. What We Will Add

### Phase 1: Own Search Layer (`core/search/`)
- `SearchProvider` Protocol:
  ```python
  class SearchProvider(Protocol):
      async def search(self, query: str, *, limit: int = 10, filters: Optional[Dict[str, Any]] = None) -> List[SearchHit]: ...
  ```
- `SearchHit` data model (`url`, `canonical_url`, `title`, `snippet`, `source_family`, `provider`, `published_at`, `rank`, `raw_score`).
- `SearxngProvider`: Self-hosted metasearch client querying SearXNG JSON API (`/search?format=json`), selecting engines by category (general, news, science, it, social media, videos, files), with non-fatal per-engine error handling.
- `infra/searxng/settings.yml` & `infra/docker-compose.yml` service: SearXNG container with JSON enabled, bot detection disabled for internal network traffic.
- Vertical search adapters:
  - **Forums**: Hacker News (Algolia API), Reddit (public JSON search API), Stack Exchange (Advanced Search API).
  - **Code**: GitHub REST Search API (repositories, code, discussions/issues).
  - **Academic**: arXiv API (Atom export), OpenAlex Works API, Semantic Scholar Graph API, Wikipedia + Wikidata query APIs.
  - **Video**: YouTube search + `youtube-transcript-api` (timed text chunks).
  - **Social**: Mastodon public search API and Bluesky public search API (`app.bsky.feed.searchPosts`).
  - **App Stores**: Google Play Store and Apple App Store (iTunes search API + RSS reviews).
  - **Archives & Discovery**: RSS/Atom feed parser, Wayback Machine CDX API, Marginalia search, and DuckDuckGo (`ddgs` fallback).
- `SearchRouter`: Dynamically routes sub-questions by `source_family`, executes providers concurrently, applies Reciprocal Rank Fusion (RRF), canonicalizes URLs, and deduplicates using SimHash (64-bit Hamming distance).
- Source Family Registration: `web_general`, `news`, `forums`, `code`, `academic`, `video`, `social`, `app_stores`, `archives` registered into `DataSourceRegistry`.

### Phase 2: Own Fetch & Extract Layer (`core/fetch/`)
- Tiered Fetching Architecture:
  1. **Fast Path**: `httpx.AsyncClient` with connection pooling, gzip/brotli compression, and timeout bounds.
  2. **JavaScript Rendering Path**: `Crawl4AI` (`AsyncWebCrawler`) for dynamic Single Page Applications (SPAs).
  3. **Heavy Browser Fallback**: Headless Playwright.
  4. **Clean Content Extraction**: `trafilatura` for boilerplate removal, retaining clean hierarchy and heading metadata.
  5. **PDF / Structured Docs**: `PyMuPDF` (`fitz`) extracting text per page and tracking exact `page_no` offsets; DOCX and plain text support.
- `FetchedDocument` Model:
  `url`, `final_url`, `status`, `content_type`, `fetched_at`, `content_hash`, `title`, `sections` (`[{heading_path, char_start, char_end, text}]`), `pages` (`[{page_no, text}]` for PDFs), `timestamps` (for transcripts).
- Politeness, Rate Limiting & Circuit Breakers:
  - In-memory cached `RobotFileParser` respecting `robots.txt` per host.
  - Per-domain Token Bucket rate limiter (default: max 2 requests/sec per domain).
  - Per-domain Circuit Breaker: 3 consecutive 4xx/5xx errors temporarily pauses domain requests for 60s.
  - Fallback to Wayback Machine snapshots if live domain is blocked and robots.txt permits.
- Tenant-Scoped Document Cache:
  - Cache table in PostgreSQL (`cached_web_pages`) keyed by `(tenant_id, canonical_url, content_hash)` with configurable TTL (default: 7 days) to eliminate redundant outbound requests.

### Phase 3: Evidence with Exact Locations
- Extended `ResearchNote` Schema & DB Migration (`db/schema.sql`):
  - `url`, `canonical_url`, `title`, `source_family`, `provider`, `retrieved_at`, `content_hash`.
  - `excerpt` (verbatim, <= 300 characters), `char_start`, `char_end`, `page_no` (nullable int), `heading_path` (list of strings).
  - `text_fragment_url`: Standard Chrome/Edge text fragment link (`url + "#:~:text=" + percent-encoded start/end`).
  - `video_timestamp_url`: YouTube timestamp link (`url + "&t=SECONDS"`).
  - `archive_url`: Wayback Machine snapshot URL.
- Strict Worker Verification Rule:
  - Prior to writing any `ResearchNote` to `StateStore`, the worker verifies that `excerpt` exists verbatim (or fuzzy similarity >= 0.90 via normalized Levenshtein/whitespace matching) inside the `FetchedDocument`.
  - If verified: computes exact `char_start`, `char_end`, section `heading_path`, and `page_no`.
  - If unverified: **drops the note immediately** and emits a `note_rejected` event.
- Writer Agent & Citation Gate Upgrade:
  - Injects human-readable location into report citations: `[note_123] https://example.com/page - section 'Pricing > Enterprise' (p. 14 of PDF)`.
  - Upgrades `CitationGate` to verify that every quantitative assertion links to a note with a verified location.

### Phase 4: Massive Parallel Fan-Out
- Query Expander Agent (`core/agents/expander.py`):
  - Decomposes each `PlanTask` into 5-20 distinct sub-queries spanning synonyms, target geography languages, `site:` filters, and specific question structures, each tagged by `source_family`.
- Sharded Orchestrator Fan-Out (`core/agents/orchestrator.py`):
  - Employs `asyncio.TaskGroup` running tasks x source_families x sub-queries concurrently as lightweight shards.
  - Concurrency controls: Global concurrency cap (default: 24), per-provider concurrency cap (default: 4), per-domain concurrency cap (default: 2).
  - Shard Lifecycle: search -> rank -> fetch top-K -> extract claims -> verify against document -> save notes.
  - Follow-the-links (depth <= 2, same domain/topic, max 2 links per shard) and entity snowballing.
  - Cross-Encoder Passage Reranking: local lightweight passage scorer (`sentence-transformers/bge-reranker-base` or normalized BM25 reranker fallback) to select top candidate excerpts before LLM claim extraction.
  - Shared `seen_urls` set in `StateStore` to guarantee zero duplicate fetches across shards.
  - Extended `BudgetState`: Tracks `fetched_pages`, `providers_failed`, and `bytes_downloaded` with 80% warning and 100% clean stop.

### Phase 5: Compounding Local Web Index (`core/knowledge/web_index.py`)
- Persistent `web_index_chunks` table in PostgreSQL with `pgvector` embeddings and PostgreSQL Full-Text Search (tsvector).
- Tenant-scoped Row-Level Security (`FORCE ROW LEVEL SECURITY`).
- `web_index` DataSource: Hybrid retriever (vector + FTS) checked first before firing network requests.
- Asynchronous re-crawl scheduler for stale documents based on family TTL.

### Phase 6: API, Telemetry & UI Upgrades
- New Server-Sent Events (SSE):
  `search_started`, `search_hit`, `page_fetched`, `page_blocked`, `note_rejected`, `shard_started`, `shard_done`, `source_coverage`.
- New Endpoint:
  `GET /v1/jobs/{job_id}/sources`: Returns all discovered evidence grouped by `source_family` with locations and verification statuses.
- Gradio UI Update (`app.py`):
  - Live parallel shards panel tracking active worker shards in real time.
  - Source coverage distribution bar across the 9 source families.
  - Clickable evidence matrix with text-fragment links and verified location badges.
- Langfuse Observability:
  - Spans per shard and per search provider logging latencies, hit counts, and error rates.

### Phase 7: Comprehensive Test Suite & Acceptance
- Offline Fixture-Based Test Suite:
  - Unit tests for all vertical adapters using recorded HTTP mocks.
  - RRF merging, URL canonicalization, and SimHash deduplication tests.
  - Politeness tests: robots.txt compliance, rate limiter, and circuit breaker.
  - Exact & fuzzy location verification tests (verifying exact offsets and rejection of fabricated claims).
  - Text-fragment URL encoding tests.
  - Fan-out concurrency and budget clean-stop tests.
  - Tenant isolation and RLS leakage tests for `web_index`.
- Live Smoke Test Suite:
  - Marked with `@pytest.mark.live` (skipped by default).
  - Validates 5 live queries against SearXNG and verifies location accuracy.

---

## 2. What We Will Change

| Existing Component | Planned Changes | Backward Compatibility Strategy |
|---|---|---|
| `core/tools/search.py` | Refactored into a compatibility facade redirecting to `core/search/router.py`. | Retains `SearchService` and `SearchResult` interfaces so existing tests continue to pass without modification. |
| `core/tools/fetch.py` | Refactored into a compatibility wrapper delegating to `core/fetch/tiered_fetcher.py`. | Retains `PageFetchService.fetch_markdown()` and prompt injection fencing. |
| `core/tools/registry.py` | Registers the new source families (`web_general`, `news`, `forums`, `code`, `academic`, `video`, `social`, `app_stores`, `archives`, `web_index`). | Retains default registrations for `web_search`, `web_fetch`, `knowledge_base`, `ga4_mcp`, `hubspot_mcp`. |
| `core/state/schemas.py` | Adds nullable location fields to `ResearchNote`; extends `BudgetState` with `fetched_pages`, `providers_failed`, `bytes_downloaded`; adds new `EventType` values. | All new fields are optional/have defaults; existing serializations and schema validations remain valid. |
| `core/state/store.py` | Adds methods for `seen_urls`, `cached_web_pages`, `web_index` querying, and source evidence aggregation. | Existing job, note, artifact, and event methods remain unchanged. |
| `core/agents/worker.py` | Integrates excerpt location verification before saving notes; drops unverified claims; emits `note_rejected`. | Still outputs `List[ResearchNote]`; honors max tool calls and timeout limits. |
| `core/agents/orchestrator.py` | Replaces single-worker queue with sharded `asyncio.TaskGroup` fan-out and concurrency semaphores. | Accepts the same `run_plan(job_id, plan)` signature and returns `List[ResearchNote]`. |
| `core/guardrails/citation_gate.py`| Upgraded to verify that cited claims have non-empty location metadata. | Strict regex parsing remains intact. |
| `core/agents/writer.py` | Updated to format citations with human-readable location descriptors and text-fragment URLs. | Preserves note ID citations (`[note_...]`) and provider fallback banners. |
| `db/schema.sql` | Adds nullable columns to `research_notes`; creates `cached_web_pages` and `web_index_chunks` tables with RLS. | Non-destructive `ALTER TABLE` / `IF NOT EXISTS` syntax ensures zero downtime. |
| `infra/docker-compose.yml` | Adds `searxng` service with dedicated `infra/searxng/settings.yml`. | Existing postgres, minio, langfuse, and api services remain unaffected. |
| `apps/api/main.py` | Adds `GET /v1/jobs/{id}/sources` route; updates SSE event stream serialization. | Existing endpoints remain unchanged. |

---

## 3. Risks & Mitigation Strategies

1. **Third-Party API Rate Limiting & Blocking**:
   - *Risk*: Public endpoints (Reddit, Hacker News, Wikipedia, GitHub) may throttle or block requests under high concurrency.
   - *Mitigation*: Per-provider concurrency caps (default: 4), per-domain token bucket rate limiting (2 req/s), exponential backoff with jitter, non-fatal provider error handling, and graceful fallback to SearXNG or cached snapshots.

2. **Windows Application Control (WDAC) Restrictions**:
   - *Risk*: Windows host blocks certain compiled `.pyd` C-extensions (such as matplotlib or fast tokenizers) when invoked in subprocesses or unprivileged shells.
   - *Mitigation*: Pure-Python algorithms for text matching (Levenshtein, SimHash, RRF) with optional C-extensions behind `try...except ImportError` fallbacks. Keep subprocess sandbox environment enriched with `USERPROFILE`, `APPDATA`, and temp directory configurations.

3. **High Fan-Out Resource Exhaustion (Memory/CPU/Sockets)**:
   - *Risk*: Fanning out 24+ concurrent browser or HTTP tasks can exhaust memory or file descriptors.
   - *Mitigation*: Tiered fetching uses lightweight HTTPX for 85%+ of pages; headless Crawl4AI/Playwright is strictly rate-limited with a global semaphore (max 4 concurrent browser instances); strict 15s request timeouts and 2MB payload limits.

4. **Hallucinated or Altered Excerpts**:
   - *Risk*: LLM worker may paraphrase claims, causing exact match checks to fail and drop valid research notes.
   - *Mitigation*: Implement dual-pass location verification: 1) Exact substring match; 2) Normalized fuzzy sliding window matching (whitespace, unicode, and case normalization with >= 0.90 similarity threshold) to reliably locate near-verbatim quotes.

5. **Cross-Tenant Data Contamination**:
   - *Risk*: Cached pages or web index entries could leak across tenants.
   - *Mitigation*: Every cache and index entry requires `tenant_id` column, enforced by PostgreSQL Row-Level Security (`ALTER TABLE ... FORCE ROW LEVEL SECURITY;`) and isolated `SET LOCAL app.tenant_id = :tenant_id` database sessions.

---

## 4. Phase-by-Phase Implementation Roadmap

- [ ] **Step 0**: Review codebase, analyze dependencies, and author `PLAN.md`.
- [ ] **Phase 1**: Implement `core/search/` (SearXNG provider, 10+ vertical adapters, RRF merger, canonical URL/SimHash dedup, `infra/searxng/settings.yml`, `infra/docker-compose.yml`, test suite).
- [ ] **Phase 2**: Implement `core/fetch/` (Tiered HTTPX/Crawl4AI fetcher, PyMuPDF page extractor, Trafilatura article parser, robots.txt cache, token-bucket rate limiter, circuit breaker, tenant page cache).
- [ ] **Phase 3**: Evidence with exact locations (Extend `ResearchNote` schema & DB migration, strict worker excerpt verification & rejection, text fragment URL generator, writer location rendering, citation gate location check).
- [ ] **Phase 4**: Massive parallel fan-out (Query Expander agent, sharded `asyncio.TaskGroup` orchestrator, cross-encoder reranking, seen URL deduplication, extended budget tracking, gap verifier source-family check).
- [ ] **Phase 5**: Compounding web index (PostgreSQL schema with pgvector & FTS, `web_index` DataSource hybrid retriever, TTL re-crawl logic).
- [ ] **Phase 6**: API, telemetry & UI (New SSE events, `GET /v1/jobs/{id}/sources` endpoint, Gradio parallel shard visualizer & evidence table, Langfuse shard spans).
- [ ] **Phase 7**: Comprehensive offline tests, live smoke suite, acceptance verification, README & DECISIONS documentation updates.
