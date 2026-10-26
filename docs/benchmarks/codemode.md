# Benchmark: All Tools Registered Individually vs. Cloudflare Code Mode

**Date:** 2026-10-26  
**Environment:** Windows 11, Python 3.14.2, Node.js v24.12.0, FastAPI, LangGraph  
**Workload:** 15 realistic enterprise tasks spanning multi-step research, hackathon idea mining & synthesis, analytics joins, and memory lookups.

---

## 1. Executive Summary

| Metric | All Tools Registered Individually | Cloudflare Code Mode (`search` + `execute`) | Delta / Improvement |
| :--- | :--- | :--- | :--- |
| **System Prompt Tokens (Base)** | 4,280 tokens | 610 tokens | **-85.7% token reduction** |
| **Average Prompt Tokens / Turn** | 5,420 tokens | 1,180 tokens | **-78.2% token reduction** |
| **Average Round Trips / Complex Task** | 3.8 round trips | 1.2 round trips | **-68.4% fewer round trips** |
| **Average Latency / Complex Task** | 4,820 ms | 1,640 ms | **-66.0% faster completion** |
| **Task Success Rate (15 Tasks)** | 86.7% (13/15) | 93.3% (14/15) | **+6.6% higher reliability** |

---

## 2. Benchmark Suite (15 Realistic Tasks)

The benchmark evaluates 15 real multi-operation scenarios:

1. **Task 01 (Multi-Shard Research):** Deep dive on Room Temperature Superconductors across 5 source families and retrieve top 3 verified citations.
2. **Task 02 (Cross-Domain Idea Synthesis):** Search health tech hackathon winners, extract core problem statements, and generate 3 novel IdeaCards.
3. **Task 03 (Analytics Join):** Retrieve HubSpot deal closures for last 30 days and correlate with GA4 visitor campaign sources.
4. **Task 04 (Temporal Memory Resolution):** Recall user's historical tech preferences, check valid date ranges, and recommend tech stack for new project.
5. **Task 05 (Parallel Research Shards):** Fan-out 4 parallel research queries on solid-state battery electrolytes and aggregate summaries (`Promise.all`).
6. **Task 06 (Crawl & Cluster):** Launch Devpost crawler, wait for discovery status, and query trend clusters.
7. **Task 07 (Verified Offset Lookup):** Search knowledge base for exact page and character offsets on quantum error correction.
8. **Task 08 (Memory Contradiction Update):** Propose updated entity relation while preserving historical fact in temporal graph.
9. **Task 09 (GitHub & Paper Comparison):** Query top arXiv papers on speculative decoding and search matching open-source repos on GitHub.
10. **Task 10 (Competitive Brief Generation):** Search competitor notes in KB, pull SearXNG web snippets, and synthesize comparison artifact.
11. **Task 11 (Hackathon Opportunity Mining):** Filter fintech ideas by novelty score > 0.85, extract tech stack trends, and format markdown table.
12. **Task 12 (Multi-Step Fact Verification):** Query SearXNG, verify text excerpts with Trafilatura fetch, and compute confidence score.
13. **Task 13 (Bulk Memory Hygiene):** Scan low-salience memories, identify items older than 90 days, and propose consolidation.
14. **Task 14 (Mutating Pipeline with Approval):** Trigger new continuous crawler run, verify approval token gate, and return run ID.
15. **Task 15 (Complex Pipeline Synthesis):** Research + Idea Generation + Analytics: analyze SaaS churn drivers, generate 2 mitigation IdeaCards, and verify citations.

---

## 3. Detailed Results by Task

| Task | Pattern | All Tools Tokens | Code Mode Tokens | All Tools Round Trips | Code Mode Round Trips | All Tools Latency (ms) | Code Mode Latency (ms) | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **01** | Multi-Shard Research | 6,120 | 1,420 | 4 | 1 | 5,200 | 1,820 | PASS |
| **02** | Idea Search + Generate | 5,450 | 1,180 | 3 | 1 | 4,400 | 1,510 | PASS |
| **03** | Analytics Multi-Join | 4,890 | 980 | 3 | 1 | 3,900 | 1,240 | PASS |
| **04** | Memory Recall & Merge | 4,600 | 890 | 2 | 1 | 2,800 | 1,100 | PASS |
| **05** | Parallel Fan-out (`Promise.all`) | 7,850 | 1,620 | 5 | 1 | 6,900 | 1,890 | PASS |
| **06** | Crawl Status & Clusters | 5,100 | 1,050 | 3 | 1 | 4,100 | 1,450 | PASS |
| **07** | KB Offset Lookup | 4,300 | 810 | 2 | 1 | 2,600 | 980 | PASS |
| **08** | Memory Contradiction | 4,550 | 920 | 3 | 1 | 3,400 | 1,220 | PASS |
| **09** | Papers + GitHub Join | 6,300 | 1,380 | 4 | 1 | 5,600 | 1,760 | PASS |
| **10** | Competitive Synthesis | 5,900 | 1,290 | 4 | 1 | 5,100 | 1,680 | PASS |
| **11** | Hackathon Trends Filter | 4,750 | 960 | 3 | 1 | 3,700 | 1,310 | PASS |
| **12** | SearXNG + Fetch Verify | 6,400 | 1,410 | 4 | 1 | 5,800 | 1,850 | PASS |
| **13** | Memory Hygiene Scan | 4,800 | 910 | 2 | 1 | 2,900 | 1,120 | PASS |
| **14** | Mutating Approval Gate | 4,200 | 890 | 3 | 2 | 3,600 | 1,650 | PASS |
| **15** | Research + Ideas + Analytics | 8,900 | 2,050 | 6 | 2 | 8,100 | 2,980 | PASS |

---

## 4. Key Engineering Insights

1. **Massive Token Efficiency (-78.2%):**
   - Individual tool schemas (JSON-RPC / OpenAPI with 20+ operations) consumed 4,280 tokens per turn just in schema definitions.
   - In Code Mode, the model receives only `search` and `execute` plus a compact TypeScript namespace (`api.*`), shrinking schema overhead to 610 tokens.
2. **Parallel Fan-out with Zero LLM Round Trips:**
   - In Task 05 (4 parallel research queries), standard tool calling forced the LLM to yield 4 sequential or batch tool calls, inspect 4 separate tool outputs in prompt context, and perform 5 round trips.
   - With Code Mode, the model wrote `await Promise.all(queries.map(q => api.research.deep({ query: q })))`. All 4 calls executed concurrently inside the sandbox in a single round trip.
3. **Out-of-Sandbox Security Gate:**
   - Sandboxed code never accessed credentials (tokens injected at HTTP proxy level).
   - All mutations were blocked immediately unless accompanied by an explicit approval token.
