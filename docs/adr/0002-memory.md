# ADR 0002: Layered Temporal Graph Memory & Obsidian Vault Architecture

- **Status:** Accepted
- **Date:** 2026-10-26
- **Context:** `deep-research-agent` requires a unified memory subsystem that persists across user sessions, understands temporal validity (valid_from/valid_to, non-destructive contradiction handling), allows local markdown exploration in an Obsidian vault (`./vault`), and links entities to verified research notes and idea cards (L4 evidence graph).

---

## 1. Engine Candidates & Spike Analysis

We conducted a time-boxed evaluation of memory frameworks and graph engines:

| Candidate | License | Temporal Support | Graph Storage Engine | Maintenance Status | Windows / Docker Hosting | Assessment |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Graphiti (`graphiti-core`)** | Apache-2.0 | Native (`valid_at`, invalidation edges) | FalkorDB / Neo4j | **Actively maintained** by Zep team | Excellent (single container) | **Winner:** Purpose-built for dynamic temporal entity graphs. |
| **Mem0 (Graph Mode)** | Apache-2.0 | Partial (snapshots) | Neo4j / Qdrant | Actively maintained | Good | Good, but lacks fine-grained edge-level temporal invalidation out of the box. |
| **Cognee** | Apache-2.0 | Basic | LanceDB / NetworkX / Neo4j | Active, evolving rapidly | Moderate | Heavyweight pipeline abstractions, less direct control over markdown vault synchronization. |
| **Kùzu** | MIT | Native property graph | Embedded columnar | **Stagnant / Archived** (Post-acquisition) | N/A | **Rejected:** Repository lacks ongoing active releases; not viable for production. |
| **FalkorDB / Neo4j** | SSPL / GPL / Enterprise | Cypher native | In-memory Redis graph / JVM | Actively maintained | Excellent via `docker-compose` | **Selected Graph Stores:** FalkorDB as primary lightweight graph engine with Neo4j compatibility. |

---

## 2. Decision: 5-Layered Architecture (`MemoryService`)

To prevent vendor lock-in and allow seamless backend swapping, memory is architected into 5 distinct layers behind an abstract `MemoryService` protocol:

1. **L0 Working Memory:** LangGraph active state checkpointer and rolling conversation summary.
2. **L1 Episodic Memory:** Chronological episodes stored with turn metadata and vector embeddings.
3. **L2 Semantic Temporal Knowledge Graph:**
   - Entities: `Person`, `Project`, `Org`, `Tool`, `Idea`, `Decision`, `Preference`.
   - Facts & Edges: Valid time intervals (`valid_from`, `valid_to`, `is_active`).
   - Contradiction Policy: When a new fact contradicts an older fact (e.g., "We switched from Postgres to FalkorDB for graphs"), the old fact is marked `valid_to = now` and `is_active = False` rather than being deleted, preserving provenance and audit history.
4. **L3 Obsidian-Compatible Markdown Vault (`./vault`):**
   - Clean, standard markdown files with YAML frontmatter, backlinks, and `[[wikilinks]]`.
   - Organized into folders: `People/`, `Projects/`, `Ideas/`, `Research/`, `Sources/`, `Preferences/`, `Daily/`.
   - Bidirectional synchronization via file watcher (`watchfiles`): Human edits in Obsidian take precedence and update the graph facts automatically.
5. **L4 Evidence Graph:** Direct edge links from graph entities to location-verified `ResearchNotes` and `IdeaRecord` nodes with character offsets and text-fragment URLs.

---

## 3. Hybrid Retrieval & Relevance Gating

Memory retrieval follows a multi-stage fusion pipeline:
1. **Candidate Retrieval:**
   - Dense vector cosine similarity over entity descriptions.
   - BM25 full-text keyword matching over fact statements.
   - 1-to-2 hop BFS graph neighborhood expansion from matched entities.
2. **Reciprocal Rank Fusion (RRF):** Fuses candidates with reciprocal rank formula $RRF(d) = \sum \frac{1}{60 + r_i(d)}$.
3. **Temporal & Salience Reranking:** Applies exponential recency decay ($e^{-\lambda \Delta t}$) and salience weighting ($w \times salience$).
4. **Relevance Gating:** If query similarity falls below the relevance threshold ($< 0.45$), memory injection is bypassed entirely to prevent distracting the model on generic questions.

---

## 4. Privacy, PII Fence, and Hard Forget

- **Strict PII & Secret Fence (`config/memory_policy.yaml`):** Regex guards intercept API keys, passwords, bearer tokens, credit cards, SSNs, and medical records before they can be committed to L2/L3.
- **Verified Hard Forget:** Invoking `memory.forget()` removes the entity and related facts atomically across the graph database, the vector index, the FTS index, and removes the markdown note from the `./vault` directory.
- **Tenant Isolation:** Enforced via `tenant_id` namespace prefixing on graph nodes, vector partitions, and Postgres Row-Level Security.
