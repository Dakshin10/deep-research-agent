# PLAN2.md: IDEA MINER Domain Profile Extension

## Overview
This plan extends `deep-research-agent` (Python 3.12, LangGraph, FastAPI, Postgres+pgvector, MinIO, Langfuse, SearXNG-based search layer, tiered fetch layer, verified-location ResearchNotes, parallel fan-out orchestrator) with the **IDEA MINER** domain profile.

Idea Miner continuously crawls startups, hackathon projects/winners, launch posts, and related write-ups, extracts structured idea records with strict verbatim excerpt verification, and enables clustering, trend analysis, whitespace gap detection, and evidence-grounded idea generation.

---

## Architectural Principles & Strict Constraints
1. **Config-Driven Domain Profile**: Core agent code remains strictly domain-agnostic. All Idea Miner behavior is specified in `config/domains/idea_mining.yaml` and skill definition files (`skills/idea_*/SKILL.md`). The engine switches domain dynamically via `{"domain": "idea_mining"}` in the job request.
2. **Explicit Source Policy & Compliance**: `config/source_policy.yaml` dictates exact permissions per domain (allowed, access method: API/RSS/sitemap/HTML, rate limit, max pages per run). Default for unknown sites: allowed only through search engine results with robots.txt obeyed. Explicitly DENIED domains (LinkedIn, X/Twitter, Facebook, Instagram, Crunchbase) are refused by the crawler, providing hooks for official APIs and manual CSV/JSON imports.
3. **Resumable Postgres-Backed Frontier**: Distributed crawl frontier utilizing `SELECT ... FOR UPDATE SKIP LOCKED` across `crawl_sources`, `crawl_frontier`, and `crawl_runs` tables. Fully crash-resilient and idempotent with ETag/Last-Modified/content-hash freshness checking.
4. **Verbatim Excerpt Location Enforcement**: Every extracted field in `IdeaRecord` (problem, solution, tech stack, prize/placement, traction) must be backed by an exact location evidence item (`char_start`/`char_end`, `page_no`, `video_timestamp`, or `text_fragment_url`). Any unverified field is dropped (`null`) and emits a `field_rejected` event.
5. **No Wholesale Copyright Reproduction & Privacy Guardrails**: Only short factual excerpts (<= 300 chars) are stored in structured records. Full raw documents remain strictly in the private storage layer. Zero collection of personal emails, phone numbers, or private social handles.
6. **Grounding & Originality in Generation**: IdeaCards require 3–8 inspirations linked to verified projects. Generated cards are screened by an Originality Guardrail (cosine similarity distance >= threshold) to prevent plagiarism, and past hackathon winners are visibly attributed.

---

## Phases Breakdown

### Phase 1: Source Policy & Source Adapters
- **Policy Engine (`core/sources/policy.py`)**:
  - `config/source_policy.yaml` defining permissions, methods, rate limits, robots enforcement, and audit dates.
  - CLI `python -m core.sources.policy check <domain>` fetching `robots.txt` and displaying permissions.
  - Crawler enforcement refusing any domain not explicitly allowed.
  - Explicit DENIED list: `linkedin.com`, `x.com`, `twitter.com`, `facebook.com`, `instagram.com`, `crunchbase.com`.
  - Manual import fallback hooks for CSV/JSON.
- **Source Adapters (`core/sources/adapters/`)**:
  - Standard interface: `discover()` yielding listing/project URLs; `parse()` converting pages to `RawProject`.
  - Hackathons: Devpost (gallery + winner filter), Devfolio, DoraHacks, ETHGlobal, MLH, Unstop, Hack2skill, Smart India Hackathon (PDF/web), Kaggle, GitHub (hackathon topic search API).
  - Startups & Launches: Y Combinator directory, Product Hunt API, Hacker News Show/Launch HN (Algolia API), BetaList, Indie Hackers, Reddit API (r/startups, r/SideProject, r/SaaS, r/EntrepreneurRideAlong).
  - Write-ups: dev.to, Hashnode, Medium/Substack RSS, YouTube demo/pitch videos (yt-dlp + transcript API), conference talk pages, PDF pitch decks/reports (PyMuPDF).
  - Adapter Broken Alerting: Isolated CSS/HTML selectors with clear `adapter_broken` event emission on markup changes (no silent failures).
- **Integration**:
  - Register adapters as `SearchProvider` and `DataSource` families in `DataSourceRegistry` and `SearchRouter`.
  - Offline recorded fixtures for all adapters in `tests/fixtures/sources/`.

### Phase 2: Bulk, Resumable, Incremental Crawler
- **Database Architecture (`db/schema_crawl.sql`)**:
  - `crawl_sources`: Registered crawl targets with policy limits and cadence.
  - `crawl_frontier`: URL queue with `state` (`pending`, `leased`, `done`, `failed`), `priority`, `attempts`, `next_attempt_at`, `last_etag`, `last_modified`, `content_hash`.
  - `crawl_runs`: Batch runs tracking duration, fetched pages, bytes, and domain errors.
  - Row locking: `SELECT ... FOR UPDATE SKIP LOCKED` for concurrent workers.
- **Crawler Service (`core/crawl/`)**:
  - Modes: `discover` (listing/sitemaps), `fetch` (download & extract), `refresh` (conditional ETag/hash re-check).
  - Hard limit guards: max pages, max bytes, max duration, per-domain concurrency semaphores, jittered delays, exponential backoff, circuit breakers.
  - Honest User-Agent with contact email from `.env`.
  - MinIO raw document archive with `content_hash` and `fetched_at`.
- **Interfaces**:
  - CLI: `python -m core.crawl run --source devpost --since 2022 --limit 5000`.
  - REST API: `POST /v1/crawl/runs`, `GET /v1/crawl/runs/{id}`, SSE event stream.

### Phase 3: Structured Idea Extraction with Verified Evidence
- **Data Model (`core/ideas/schemas.py` & `db/schema_ideas.sql`)**:
  - `IdeaRecord`: id, name, one_liner, problem, solution, target_users, domain_tags, tech_stack, business_model, stage, traction, source_kind, event_name, year, placement/prize, team_size, links, first_seen_url, all_source_urls, confidence, extracted_at.
  - `EvidenceEntry`: field, url, excerpt, char_start, char_end, page_no, video_timestamp, text_fragment_url.
  - Verifier check: drop unverified field to null and emit `field_rejected`.
- **Extraction Agent (`core/ideas/extractor.py`)**:
  - Fast model first-pass, strong model fallback for ambiguous/dense content.
  - JSON schema constraints, retry on invalid JSON, text chunking for long articles.
  - Language detection & automatic translation preserving original text.
- **Entity Resolution (`core/ideas/resolver.py`)**:
  - Cross-link deduplication (shared GitHub, demo URL, YouTube link).
  - Fuzzy title + embedding cosine similarity merge.
  - Merge audit trail and un-merge capability.
- **Privacy Engine**:
  - Automatic scrubbing of emails, phone numbers, addresses, and private handles.
- **Search & Embeddings**:
  - Canonical embedding over `problem + solution + tech + users`.
  - pgvector HNSW index + PostgreSQL full-text search (tsvector) for hybrid retrieval.

### Phase 4: Analysis Engine
- **Sandboxed Analyst Skills (`skills/idea_analysis/`)**:
  - `clustering`: HDBSCAN/KMeans clustering over embeddings with LLM cluster naming and sizing.
  - `trends`: Tech stack, domain, and problem area trajectories over years/events; saturated vs underexplored category calculation.
  - `winner_patterns`: Statistical comparisons between winners and non-winners (team size, video presence, tech choices) with explicit sample sizes and no causation claims.
  - `whitespace`: Identification of low-density embedding regions crossed with user problem statements (e.g. SIH problem statements).
  - Production of structured notes and Matplotlib PNG charts with verified project references.

### Phase 5: Evidence-Grounded Idea Generation
- **Idea Generator Agent (`core/ideas/generator.py`)**:
  - Input: Problem statement/brief, constraints (stack, team size, timeframe, target hackathon/event), nearest clusters/projects.
  - Output: `IdeaCard` list (title, problem, target users, solution sketch, why now, tech stack, architecture, MVP scope, differentiation, risks, inspirations).
- **Originality Guardrail (`core/ideas/guardrails.py`)**:
  - Cosine distance check against existing `IdeaRecord`s.
  - Rejection or explicit iterative improvement flagging.
  - Clear attribution warning when inspiration stems from a past hackathon winner.
- **Export Formats**:
  - Markdown report, JSON, CSV idea cards, and PPTX slide deck (max 5 bullets per slide).

### Phase 6: API, UI & Observability
- **API Endpoints (`apps/api/routers/ideas.py` & `crawl.py`)**:
  - `POST /v1/ideas/search`: Hybrid semantic + keyword + filter search.
  - `GET /v1/ideas/{id}`: Detailed idea record with evidence links.
  - `GET /v1/ideas/clusters`: Active clusters and representative ideas.
  - `GET /v1/ideas/trends`: Saturation and win-rate trends.
  - `POST /v1/ideas/generate`: Evidence-grounded idea generation.
  - `POST /v1/ideas/import`: Manual CSV/JSON ingestion for denied domains.
  - `GET /v1/sources/coverage`: Domain and source family crawl status.
- **Gradio Visualizer Tabs (`app.py`)**:
  - Crawl Monitor, Idea Explorer, Trends & Clusters, Idea Generator.
- **Observability**:
  - Langfuse spans for crawl sources, extraction batches, and cost tracking per 1,000 pages.

### Phase 7: Tests & Acceptance
- Offline unit and integration test suite with recorded fixtures:
  - Source policy enforcement (denied domain refusal).
  - Adapter discover & parse functionality.
  - Resumable crawler recovery after crash.
  - Idea extraction with verbatim location verification and hallucination dropping.
  - Entity resolution merge/un-merge.
  - Privacy data scrubbing.
  - Clustering, trends, and originality guardrails.
  - Multi-tenant RLS isolation.
- Live smoke tests (`@pytest.mark.live`) for 3 public sources.
- Full acceptance run validating >= 2,000 projects across >= 5 sources, >= 90% verified placement fields, relevant search, and >= 5 original IdeaCards.
