from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple
from core.models.router import ModelRouter
from core.state.schemas import Plan, PlanTask, ResearchNote, ExpectedOutput, TaskStatus


class GapCheckResult:
    def __init__(self, needs_more_research: bool, extra_tasks: List[PlanTask]):
        self.needs_more_research = needs_more_research
        self.extra_tasks = extra_tasks


class GapCheckVerifier:
    """Audits accumulated research notes against the plan and adds at most one extra round of tasks."""

    def __init__(self, model_router: Optional[ModelRouter] = None):
        self.router = model_router or ModelRouter()

    async def verify_gaps(
        self,
        plan: Plan,
        notes: List[ResearchNote],
        extra_research_rounds: int = 0,
    ) -> GapCheckResult:
        # Enforce maximum of ONE extra round
        if extra_research_rounds >= 1:
            return GapCheckResult(needs_more_research=False, extra_tasks=[])

        # Check which tasks have notes
        task_notes_count = {t.task_id: 0 for t in plan.tasks}
        for n in notes:
            if n.task_id in task_notes_count:
                task_notes_count[n.task_id] += 1

        uncovered_tasks = [t for t in plan.tasks if task_notes_count[t.task_id] == 0]

        if uncovered_tasks:
            extra_tasks = []
            for t in uncovered_tasks[:2]:
                extra_tasks.append(
                    PlanTask(
                        task_id=f"{t.task_id}_followup",
                        objective=f"Deep-dive gap resolution: {t.objective}",
                        entity=t.entity,
                        source_hints=["web_search", "web_fetch"],
                        expected_output=t.expected_output,
                        depends_on=[],
                        status=TaskStatus.PENDING,
                    )
                )
            return GapCheckResult(needs_more_research=True, extra_tasks=extra_tasks)

        return GapCheckResult(needs_more_research=False, extra_tasks=[])
