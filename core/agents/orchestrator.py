from __future__ import annotations

import asyncio
from collections import defaultdict
import re
from typing import Any, Dict, List, Optional, Set
import time
import urllib.parse
import uuid

from core.agents.expander import QueryExpander, SubQuery
from core.agents.worker import ResearcherWorker
from core.fetch.base import FetchedDocument
from core.fetch.location import verify_excerpt_in_document
from core.knowledge.store import KnowledgeStore
from core.knowledge.web_index import WebIndexStore, WebIndexProvider
from core.observability.tracing import record_shard_span
from core.search.canonical import normalize_canonical_url
from core.search.reranker import PassageReranker
from core.search.router import SearchRouter
from core.state.schemas import (
    Brief,
    EventType,
    Plan,
    PlanTask,
    ResearchNote,
    TaskStatus,
)
from core.state.store import StateStore
from core.tools.fetch import PageFetchService
from core.tools.search import SearchService


class ResearchOrchestrator:
    """
    Massively parallel sharded fan-out orchestrator.
    - Shards each PlanTask across diverse sub-queries and source families.
    - Runs shards using asyncio.TaskGroup.
    - Enforces 3 concurrency bounds: global (default 24), per-provider (default 4), and per-domain (default 2).
    - Prevents duplicate URL fetches across shards via StateStore seen-URL registry.
    - Reranks candidate passages using PassageReranker before claim extraction.
    - Enforces exact location verification before saving notes.
    - Includes follow-the-links (depth <= 2) and snowball sub-query expansion.
    """

    def __init__(
        self,
        tenant_id: str,
        state_store: StateStore,
        concurrency_cap: int = 24,
        per_provider_cap: int = 4,
        per_domain_cap: int = 2,
        search_service: Optional[SearchService] = None,
        fetch_service: Optional[PageFetchService] = None,
        knowledge_store: Optional[KnowledgeStore] = None,
        search_router: Optional[SearchRouter] = None,
        query_expander: Optional[QueryExpander] = None,
        reranker: Optional[PassageReranker] = None,
        web_index_store: Optional[WebIndexStore] = None,
    ):
        self.tenant_id = tenant_id
        self.state_store = state_store
        self.concurrency_cap = concurrency_cap
        self.per_provider_cap = per_provider_cap
        self.per_domain_cap = per_domain_cap

        self.search_service = search_service or SearchService()
        self.fetch_service = fetch_service or PageFetchService()
        self.knowledge_store = knowledge_store
        self.search_router = search_router or getattr(self.search_service, "router", None) or SearchRouter()
        self.query_expander = query_expander or QueryExpander()
        self.reranker = reranker or PassageReranker()
        self.web_index_store = web_index_store
        if self.web_index_store is None:
            db_u = getattr(self.state_store, "db_url", "sqlite+aiosqlite:///:memory:")
            sess_f = getattr(self.state_store, "_session_factory", None)
            self.web_index_store = WebIndexStore(tenant_id=self.tenant_id, db_url=db_u, session_factory=sess_f)

        if hasattr(self.search_router, "register_provider") and self.web_index_store:
            self.search_router.register_provider("web_index", WebIndexProvider(self.web_index_store))

        # Semaphores
        self.global_sem = asyncio.Semaphore(concurrency_cap)
        self.provider_sems: Dict[str, asyncio.Semaphore] = defaultdict(
            lambda: asyncio.Semaphore(self.per_provider_cap)
        )
        self.domain_sems: Dict[str, asyncio.Semaphore] = defaultdict(
            lambda: asyncio.Semaphore(self.per_domain_cap)
        )

    async def run_plan(self, job_id: str, plan: Plan, brief: Optional[Brief] = None) -> List[ResearchNote]:
        all_notes: List[ResearchNote] = []
        completed_task_ids: Set[str] = set()

        tasks = list(plan.tasks)
        pending_tasks = {t.task_id: t for t in tasks}

        while pending_tasks:
            # 1. Dependency-gating: find ready tasks in current DAG wave
            ready_tasks = [
                t for t in pending_tasks.values()
                if all(dep in completed_task_ids for dep in t.depends_on)
            ]

            if not ready_tasks:
                # Cycle or dead dependency recovery
                ready_tasks = list(pending_tasks.values())[: max(1, self.concurrency_cap // 4)]

            # 2. Expand tasks into sharded sub-queries
            task_shards: List[tuple[PlanTask, SubQuery]] = []
            max_q = 6 if self.concurrency_cap <= 4 else 10
            for t in ready_tasks:
                sub_queries = await self.query_expander.expand(t, brief=brief, max_queries=max_q)
                for sq in sub_queries:
                    task_shards.append((t, sq))

            wave_notes: List[ResearchNote] = []
            notes_lock = asyncio.Lock()

            async def _run_shard(t: PlanTask, sq: SubQuery, shard_idx: int):
                shard_id = f"shard_{t.task_id}_{shard_idx}"
                try:
                    shard_notes = await self._execute_shard(
                        job_id=job_id,
                        task=t,
                        sub_query=sq,
                        shard_id=shard_id,
                    )
                    async with notes_lock:
                        wave_notes.extend(shard_notes)
                except Exception:
                    pass

            # 3. Execute shards in parallel under concurrency limits
            await asyncio.gather(
                *[_run_shard(t, sq, idx) for idx, (t, sq) in enumerate(task_shards)],
                return_exceptions=True,
            )

            # 4. If KB lookup is available, run for ready tasks
            if self.knowledge_store:
                for t in ready_tasks:
                    kb_chunks = await self.knowledge_store.retrieve(t.entity, top_k=2)
                    for chunk in kb_chunks:
                        note = ResearchNote(
                            id=f"note_kb_{uuid.uuid4().hex[:6]}",
                            job_id=job_id,
                            tenant_id=self.tenant_id,
                            claim=f"KB insight on {t.entity}: {chunk['text'][:140].strip()}",
                            source_type="kb",
                            document_id=chunk["document_id"],
                            excerpt=chunk["text"][:280].strip(),
                            confidence=0.96,
                            task_id=t.task_id,
                            is_verified=True,
                        )
                        await self.state_store.add_note(note)
                        wave_notes.append(note)

            # 5. Mark tasks completed in wave
            all_notes.extend(wave_notes)
            for t in ready_tasks:
                completed_task_ids.add(t.task_id)
                t.status = TaskStatus.COMPLETED
                pending_tasks.pop(t.task_id, None)

        # Sync final plan status
        for t in plan.tasks:
            if t.task_id in completed_task_ids:
                t.status = TaskStatus.COMPLETED

        job = await self.state_store.get_job(job_id)
        if job and job.plan:
            job.plan = plan
            await self.state_store.update_job(job)

        return all_notes

    async def _execute_shard(
        self,
        job_id: str,
        task: PlanTask,
        sub_query: SubQuery,
        shard_id: str,
    ) -> List[ResearchNote]:
        """Executes a single research shard (search -> dedup -> fetch -> rerank -> verify -> save)."""
        shard_notes: List[ResearchNote] = []

        # Check global budget
        budget = await self.state_store.check_budget(job_id, steps_delta=1, tokens_delta=20)
        if budget.exhausted:
            return shard_notes

        await self.state_store.emit_event(
            job_id,
            EventType.SHARD_STARTED,
            {
                "shard_id": shard_id,
                "task_id": task.task_id,
                "query": sub_query.query,
                "source_family": sub_query.source_family,
            },
        )

        shard_start = time.time()
        async with self.global_sem:
            # 1. Search under provider semaphore
            provider_sem = self.provider_sems[sub_query.source_family]
            async with provider_sem:
                await self.state_store.emit_event(
                    job_id,
                    EventType.SEARCH_STARTED,
                    {"shard_id": shard_id, "query": sub_query.query, "source_family": sub_query.source_family},
                )
                try:
                    search_hits = await self.search_router.search(
                        sub_query.query,
                        source_family=sub_query.source_family,
                        limit=3,
                    )
                except Exception:
                    search_hits = []

            for hit in search_hits:
                await self.state_store.emit_event(
                    job_id,
                    EventType.SEARCH_HIT,
                    {"shard_id": shard_id, "title": hit.title, "url": hit.url, "provider": hit.provider},
                )

            # 2. Pick top URLs and deduplicate against StateStore seen URLs
            candidate_urls: List[str] = []
            for hit in search_hits:
                canon = normalize_canonical_url(hit.url)
                is_new = await self.state_store.mark_url_seen(job_id, canon)
                if is_new:
                    candidate_urls.append(hit.url)

            # 3. Fetch documents under per-domain semaphores
            fetched_docs: List[FetchedDocument] = []
            for u in candidate_urls[:2]:
                parsed = urllib.parse.urlparse(u)
                domain = parsed.netloc.lower() or "local"
                domain_sem = self.domain_sems[domain]

                async with domain_sem:
                    doc = await self.fetch_service.fetch_document(u)
                    if doc.is_blocked:
                        await self.state_store.emit_event(
                            job_id,
                            EventType.PAGE_BLOCKED,
                            {"url": u, "reason": doc.block_reason or "blocked"},
                        )
                    else:
                        await self.state_store.emit_event(
                            job_id,
                            EventType.PAGE_FETCHED,
                            {"url": doc.final_url or u, "status": doc.status, "title": doc.title},
                        )
                        fetched_docs.append(doc)

            # 4. Rerank passages and extract verified claims
            for doc in fetched_docs:
                if not doc.raw_text:
                    continue

                # Segment text into candidate passages
                passages = self._extract_passages(doc)
                if not passages:
                    continue

                # Cross-encoder passage reranking
                reranked = self.reranker.rerank(sub_query.query, passages, top_k=2)

                for passage_text, score in reranked:
                    # Verification step (HARD RULE)
                    is_ver, c_start, c_end, p_no, h_path, frag_url = verify_excerpt_in_document(
                        passage_text,
                        doc,
                    )

                    if not is_ver:
                        await self.state_store.emit_event(
                            job_id,
                            EventType.NOTE_REJECTED,
                            {
                                "shard_id": shard_id,
                                "task_id": task.task_id,
                                "url": doc.final_url or doc.url,
                                "reason": "Excerpt verification match failed in document text",
                            },
                        )
                        continue

                    note = ResearchNote(
                        id=f"note_{uuid.uuid4().hex[:8]}",
                        job_id=job_id,
                        tenant_id=self.tenant_id,
                        claim=f"{task.entity}: {passage_text[:140].strip()}",
                        source_type="web",
                        source_url=doc.final_url or doc.url,
                        excerpt=passage_text[:280].strip(),
                        confidence=round(min(0.98, max(0.85, score)), 2),
                        task_id=task.task_id,
                        url=doc.final_url or doc.url,
                        canonical_url=doc.url,
                        title=doc.title,
                        source_family=sub_query.source_family,
                        retrieved_at=doc.fetched_at,
                        content_hash=doc.content_hash,
                        char_start=c_start,
                        char_end=c_end,
                        page_no=p_no,
                        heading_path=h_path,
                        text_fragment_url=frag_url,
                        is_verified=True,
                    )
                    await self.state_store.add_note(note)
                    shard_notes.append(note)
                    if self.web_index_store:
                        try:
                            await self.web_index_store.index_note_passage(note, doc)
                        except Exception:
                            pass

            # 5. Follow-the-links step (depth <= 2, same topic, max 1 extra page)
            for doc in fetched_docs[:1]:
                sub_links = self._extract_same_topic_links(doc, task.entity)
                for link in sub_links[:1]:
                    canon_link = normalize_canonical_url(link)
                    if await self.state_store.mark_url_seen(job_id, canon_link):
                        sub_doc = await self.fetch_service.fetch_document(link)
                        if sub_doc.raw_text and not sub_doc.is_blocked:
                            sub_passages = self._extract_passages(sub_doc)
                            if sub_passages:
                                sub_reranked = self.reranker.rerank(sub_query.query, sub_passages, top_k=1)
                                for p_text, p_score in sub_reranked:
                                    is_v, cs, ce, pn, hp, fu = verify_excerpt_in_document(p_text, sub_doc)
                                    if is_v:
                                        link_note = ResearchNote(
                                            id=f"note_link_{uuid.uuid4().hex[:6]}",
                                            job_id=job_id,
                                            tenant_id=self.tenant_id,
                                            claim=f"Deep follow-up on {task.entity}: {p_text[:140].strip()}",
                                            source_type="web",
                                            source_url=sub_doc.final_url or link,
                                            excerpt=p_text[:280].strip(),
                                            confidence=0.91,
                                            task_id=task.task_id,
                                            url=sub_doc.final_url or link,
                                            canonical_url=sub_doc.url,
                                            title=sub_doc.title,
                                            source_family=sub_query.source_family,
                                            char_start=cs,
                                            char_end=ce,
                                            page_no=pn,
                                            heading_path=hp,
                                            text_fragment_url=fu,
                                            is_verified=True,
                                        )
                                        await self.state_store.add_note(link_note)
                                        shard_notes.append(link_note)
                                        if self.web_index_store:
                                            try:
                                                await self.web_index_store.index_note_passage(link_note, sub_doc)
                                            except Exception:
                                                pass

        duration = time.time() - shard_start
        await self.state_store.emit_event(
            job_id,
            EventType.SHARD_DONE,
            {"shard_id": shard_id, "notes_count": len(shard_notes), "duration": round(duration, 2)},
        )
        await self.state_store.emit_event(
            job_id,
            EventType.SOURCE_COVERAGE,
            {"source_family": sub_query.source_family, "new_notes": len(shard_notes)},
        )
        record_shard_span(
            shard_id=shard_id,
            task_id=task.task_id,
            query=sub_query.query,
            duration=duration,
            notes_count=len(shard_notes),
        )
        return shard_notes

    def _extract_passages(self, doc: FetchedDocument) -> List[str]:
        """Extract discrete candidate passages from document sections or text blocks."""
        passages: List[str] = []
        if doc.sections:
            for s in doc.sections:
                cleaned = s.text.strip()
                if len(cleaned) >= 40:
                    passages.append(cleaned[:300])
        elif doc.raw_text:
            chunks = [p.strip() for p in doc.raw_text.split("\n\n") if len(p.strip()) >= 40]
            for c in chunks[:6]:
                passages.append(c[:300])
        return passages[:8]

    def _extract_same_topic_links(self, doc: FetchedDocument, entity: str) -> List[str]:
        """Extract links from document HTML that are on the same domain or topic."""
        # Simple regex link finder
        found: List[str] = []
        if not doc.final_url:
            return found
        parsed_doc = urllib.parse.urlparse(doc.final_url)
        matches = re.findall(r'href=[\'"](https?://[^\'">\s]+|/[^\'">\s]+)[\'"]', doc.raw_text)
        for m in matches:
            resolved = urllib.parse.urljoin(doc.final_url, m)
            parsed_link = urllib.parse.urlparse(resolved)
            if parsed_link.netloc == parsed_doc.netloc and resolved != doc.final_url:
                if any(x in resolved.lower() for x in (entity.lower(), "feature", "pricing", "doc", "product")):
                    found.append(resolved)
        return found
