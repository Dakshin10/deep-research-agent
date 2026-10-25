from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from core.models.router import ModelRouter
from core.state.schemas import Plan, PlanTask, ExpectedOutput, TaskStatus, Brief
from core.tools.registry import DataSourceRegistry


class PlannerAgent:
    """Strong-model planner decomposing research goals into max 8 structured tasks with dependency mapping."""

    PLANNER_PROMPT = """You are the Lead Research Strategist for a premium marketing agency.
Create a structured research plan for the following project.

User Query: {query}
Audience: {audience}
Geography: {geography}
Goal/KPI: {goal_kpi}
Named Competitors: {competitors}
Available Data Sources: {data_sources}

Rules:
1. Maximum 8 tasks.
2. Each task must specify: task_id, objective, entity, source_hints (from available sources), expected_output ('notes', 'notes+table', 'notes+chart'), and depends_on (list of task_ids that must complete first).
3. First establish overall market context, then create focused tasks for individual competitors, then comparative synthesis.

Output ONLY valid JSON matching:
{{
  "tasks": [
    {{
      "task_id": "string",
      "objective": "string",
      "entity": "string",
      "source_hints": ["string"],
      "expected_output": "notes" | "notes+table" | "notes+chart",
      "depends_on": ["string"]
    }}
  ]
}}
"""

    def __init__(
        self,
        model_router: Optional[ModelRouter] = None,
        source_registry: Optional[DataSourceRegistry] = None,
    ):
        self.router = model_router or ModelRouter()
        self.registry = source_registry or DataSourceRegistry()

    async def create_plan(
        self,
        query: str,
        brief: Optional[Brief] = None,
        tenant_id: str = "tenant_default",
    ) -> Plan:
        brief = brief or Brief()
        available_sources = list(self.registry.get_descriptions(tenant_id).keys())

        model = self.router.get_model("planner")
        prompt = self.PLANNER_PROMPT.format(
            query=query,
            audience=brief.audience or "General B2B",
            geography=brief.geography or "Global",
            goal_kpi=brief.goal_kpi or "Competitive benchmark",
            competitors=", ".join(brief.named_competitors) if brief.named_competitors else "Key Market Rivals",
            data_sources=", ".join(available_sources),
        )

        resp = await model.ainvoke(prompt)
        content = resp.content if hasattr(resp, "content") else str(resp)

        try:
            if "```" in content:
                content = content.split("```")[1].strip()
                if content.startswith("json"):
                    content = content[4:].strip()
            data = json.loads(content)
            raw_tasks = data.get("tasks", [])
            tasks: List[PlanTask] = []
            for t in raw_tasks[:8]:
                output_type = ExpectedOutput.NOTES
                if t.get("expected_output") == "notes+table":
                    output_type = ExpectedOutput.NOTES_AND_TABLE
                elif t.get("expected_output") == "notes+chart":
                    output_type = ExpectedOutput.NOTES_AND_CHART

                tasks.append(
                    PlanTask(
                        task_id=t.get("task_id", f"task_{len(tasks)+1}"),
                        objective=t.get("objective", "Conduct targeted research"),
                        entity=t.get("entity", "Market"),
                        source_hints=t.get("source_hints", ["web_search"]),
                        expected_output=output_type,
                        depends_on=t.get("depends_on", []),
                        status=TaskStatus.PENDING,
                    )
                )
            if tasks:
                return Plan(tasks=tasks, round=1)
        except Exception:
            pass

        # Robust heuristic fallback planner for 3-competitor and marketing deep requests
        return self._build_deterministic_plan(query, brief, available_sources)

    def _build_deterministic_plan(
        self,
        query: str,
        brief: Brief,
        sources: List[str],
    ) -> Plan:
        competitors = brief.named_competitors or ["HubSpot", "Salesforce", "Zoho"]
        tasks: List[PlanTask] = []

        # 1. Market context task
        market_task_id = "task_market_overview"
        tasks.append(
            PlanTask(
                task_id=market_task_id,
                objective=f"Evaluate overarching B2B marketing automation landscape for {brief.geography or 'Global'} market",
                entity="Industry Landscape",
                source_hints=["web_search", "knowledge_base"],
                expected_output=ExpectedOutput.NOTES,
                depends_on=[],
                status=TaskStatus.PENDING,
            )
        )

        # 2. Competitor-specific tasks
        comp_task_ids = []
        for i, comp in enumerate(competitors[:4], 1):
            tid = f"task_comp_{comp.lower()}"
            comp_task_ids.append(tid)
            tasks.append(
                PlanTask(
                    task_id=tid,
                    objective=f"Analyze {comp} product capabilities, tier pricing, and target market positioning",
                    entity=comp,
                    source_hints=["web_search", "web_fetch"],
                    expected_output=ExpectedOutput.NOTES_AND_TABLE,
                    depends_on=[market_task_id],
                    status=TaskStatus.PENDING,
                )
            )

        # 3. Comparative matrix & positioning task
        tasks.append(
            PlanTask(
                task_id="task_comparative_synthesis",
                objective="Synthesize feature gaps, pricing parity, and ROI tradeoffs across all analyzed solutions",
                entity="Competitive Matrix",
                source_hints=["web_search", "knowledge_base"],
                expected_output=ExpectedOutput.NOTES_AND_CHART,
                depends_on=comp_task_ids,
                status=TaskStatus.PENDING,
            )
        )

        return Plan(tasks=tasks[:8], round=1)
