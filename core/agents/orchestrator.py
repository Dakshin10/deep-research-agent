from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional
from core.state.store import StateStore
from core.state.schemas import Plan, PlanTask, ResearchNote, TaskStatus
from core.agents.worker import ResearcherWorker
from core.tools.search import SearchService
from core.tools.fetch import PageFetchService
from core.knowledge.store import KnowledgeStore


class ResearchOrchestrator:
    """Orchestrates concurrent worker execution honoring dependency graph and concurrency cap."""

    def __init__(
        self,
        tenant_id: str,
        state_store: StateStore,
        concurrency_cap: int = 4,
        search_service: Optional[SearchService] = None,
        fetch_service: Optional[PageFetchService] = None,
        knowledge_store: Optional[KnowledgeStore] = None,
    ):
        self.tenant_id = tenant_id
        self.state_store = state_store
        self.concurrency_cap = concurrency_cap
        self.search_service = search_service
        self.fetch_service = fetch_service
        self.knowledge_store = knowledge_store
        self.semaphore = asyncio.Semaphore(concurrency_cap)

    async def run_plan(self, job_id: str, plan: Plan) -> List[ResearchNote]:
        all_notes: List[ResearchNote] = []
        completed_task_ids = set()

        tasks = list(plan.tasks)
        pending_tasks = {t.task_id: t for t in tasks}

        while pending_tasks:
            # Find all tasks whose dependencies are met
            ready_tasks = [
                t for t in pending_tasks.values()
                if all(dep in completed_task_ids for dep in t.depends_on)
            ]

            if not ready_tasks:
                # If there's an unresolved cycle or dead dependency, take the remaining tasks
                ready_tasks = list(pending_tasks.values())[: self.concurrency_cap]

            async def _run_single_worker(t: PlanTask) -> List[ResearchNote]:
                async with self.semaphore:
                    worker = ResearcherWorker(
                        worker_id=f"worker_{t.task_id}",
                        tenant_id=self.tenant_id,
                        state_store=self.state_store,
                        search_service=self.search_service,
                        fetch_service=self.fetch_service,
                        knowledge_store=self.knowledge_store,
                    )
                    return await worker.execute_task(t, job_id)

            # Run wave concurrently up to concurrency cap
            wave_results = await asyncio.gather(*[_run_single_worker(t) for t in ready_tasks])

            for t, notes in zip(ready_tasks, wave_results):
                all_notes.extend(notes)
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
