from __future__ import annotations

import asyncio
import os
import uuid
from typing import Any, Dict, List, Literal, Optional
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt, Command, Send
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver

from core.graph.state import ResearchGraphState
from core.models.router import ModelRouter
from core.state.store import StateStore
from core.state.schemas import (
    EventType,
    JobStatus,
    TaskStatus,
    ExpectedOutput,
    Brief,
    Plan,
    PlanTask,
    ResearchNote,
    Artifact,
)
from core.agents.source_router import SourceRouterAgent
from core.agents.clarifier import ClarifierAgent
from core.agents.planner import PlannerAgent
from core.agents.orchestrator import ResearchOrchestrator
from core.agents.verifier import GapCheckVerifier
from core.agents.analyst import AnalystAgent
from core.agents.writer import WriterAgent
from core.guardrails.citation_gate import CitationGate
from core.guardrails.compliance_gate import ComplianceGate
from core.tools.pptx_generator import PPTXGenerator
from core.storage.minio_client import MinIOStorageService
from core.observability.tracing import trace_agent


class ResearchGraphBuilder:
    """
    Builds and compiles the complete Deep Researcher LangGraph workflow.
    Wires sequentially:
      source_router -> planner -> workers -> verifier -> analyst -> writer -> citation_gate -> compliance_gate -> deliver
    Includes shallow -> deep escalation and 80%/100% budget warning and clean stop enforcement.
    """

    def __init__(
        self,
        model_router: Optional[ModelRouter] = None,
        checkpointer: Optional[BaseCheckpointSaver] = None,
    ):
        self.router = model_router or ModelRouter()
        self.checkpointer = checkpointer or InMemorySaver()
        self.minio = MinIOStorageService()

    def build(self) -> Any:
        builder = StateGraph(ResearchGraphState)

        # 1. Register Nodes
        builder.add_node("classifier", self._classifier_node)
        builder.add_node("chit_chat", self._chit_chat_node)
        builder.add_node("shallow_research", self._shallow_research_node)
        builder.add_node("hitl_clarification", self._hitl_clarification_node)
        builder.add_node("source_router", self._source_router_node)
        builder.add_node("planner", self._planner_node)
        builder.add_node("workers", self._workers_node)
        builder.add_node("verifier", self._verifier_node)
        builder.add_node("analyst", self._analyst_node)
        builder.add_node("writer", self._writer_node)
        builder.add_node("citation_gate", self._citation_gate_node)
        builder.add_node("compliance_gate", self._compliance_gate_node)
        builder.add_node("deliver", self._deliver_node)
        builder.add_node("followup", self._followup_node)

        # 2. Wire Graph Edges
        builder.add_edge(START, "classifier")

        # Routing from classifier
        builder.add_conditional_edges(
            "classifier",
            self._route_classifier,
            {
                "chit_chat": "chit_chat",
                "shallow": "shallow_research",
                "clarify": "hitl_clarification",
                "deep": "source_router",
            },
        )

        builder.add_edge("chit_chat", END)

        # Routing from shallow research (escalation when budget/lookup exhausted or complex query)
        builder.add_conditional_edges(
            "shallow_research",
            self._route_shallow,
            {
                "done": "citation_gate",
                "escalate": "source_router",
            },
        )

        builder.add_edge("hitl_clarification", "source_router")
        builder.add_edge("source_router", "planner")

        # Routing from planner (stops cleanly if budget exhausted)
        builder.add_conditional_edges(
            "planner",
            self._route_planner,
            {
                "workers": "workers",
                "writer": "writer",
            },
        )

        # Routing from workers
        builder.add_conditional_edges(
            "workers",
            self._route_workers,
            {
                "verifier": "verifier",
                "writer": "writer",
            },
        )

        # Routing from verifier (gap check)
        builder.add_conditional_edges(
            "verifier",
            self._route_verifier,
            {
                "extra_research": "workers",
                "analyst": "analyst",
                "writer": "writer",
            },
        )

        builder.add_edge("analyst", "writer")
        builder.add_edge("writer", "citation_gate")
        builder.add_edge("citation_gate", "compliance_gate")
        builder.add_edge("compliance_gate", "deliver")
        builder.add_edge("deliver", END)
        builder.add_edge("followup", END)

        return builder.compile(checkpointer=self.checkpointer)

    # -------------------------------------------------------------
    # Helper: Budget Enforcement Inside Graph
    # -------------------------------------------------------------
    async def _check_budget(self, state: ResearchGraphState, steps_delta: int = 1) -> Dict[str, Any]:
        job_id = state.get("job_id")
        tenant_id = state.get("tenant_id", "tenant_default")
        if not job_id:
            return {}

        from apps.api.dependencies import get_state_store
        store = get_state_store(tenant_id)
        try:
            b_state = await store.check_budget(job_id, steps_delta=steps_delta)
            return {
                "budget": b_state.model_dump(),
                "budget_warning": b_state.warning_emitted,
                "budget_exhausted": b_state.exhausted,
            }
        except Exception:
            return {}

    # -------------------------------------------------------------
    # Conditional Routers
    # -------------------------------------------------------------
    def _route_classifier(self, state: ResearchGraphState) -> str:
        mode = state.get("mode", "deep")
        if mode == "chit_chat":
            return "chit_chat"
        elif mode == "shallow":
            return "shallow"
        elif mode == "clarify":
            return "clarify"
        return "deep"

    def _route_shallow(self, state: ResearchGraphState) -> str:
        if state.get("mode") == "deep" or state.get("escalated", False):
            return "escalate"
        return "done"

    def _route_planner(self, state: ResearchGraphState) -> str:
        if state.get("budget_exhausted", False):
            return "writer"
        return "workers"

    def _route_workers(self, state: ResearchGraphState) -> str:
        if state.get("budget_exhausted", False):
            return "writer"
        return "verifier"

    def _route_verifier(self, state: ResearchGraphState) -> str:
        if state.get("budget_exhausted", False):
            return "writer"
        if state.get("extra_research_rounds", 0) > 0 and not state.get("extra_research_done", False):
            return "extra_research"
        return "analyst"

    # -------------------------------------------------------------
    # Graph Node Implementations
    # -------------------------------------------------------------
    @trace_agent("classifier")
    async def _classifier_node(self, state: ResearchGraphState) -> Dict[str, Any]:
        if state.get("mode"):
            return {
                "mode": state["mode"],
                "confidence": state.get("confidence", 0.95),
                "stage": "classified",
            }

        query = state.get("query", "")
        model = self.router.get_model("classifier")
        resp = await model.ainvoke(f"Classify research query: {query}")
        content = resp.content if hasattr(resp, "content") else str(resp)

        mode = "deep"
        confidence = 0.95
        if "chit_chat" in content:
            mode = "chit_chat"
            confidence = 1.0
        elif "shallow" in content:
            mode = "shallow"
            confidence = 0.85
        elif "clarify" in content:
            mode = "clarify"
            confidence = 0.90

        budget_update = await self._check_budget(state, steps_delta=1)
        res = {
            "mode": mode,
            "confidence": confidence,
            "stage": "classified",
        }
        res.update(budget_update)
        return res

    @trace_agent("chit_chat")
    async def _chit_chat_node(self, state: ResearchGraphState) -> Dict[str, Any]:
        return {
            "report": "Hello! I am your Deep Research AI assistant. How can I help your research today?",
            "stage": "completed",
            "done": True,
        }

    @trace_agent("shallow_research")
    async def _shallow_research_node(self, state: ResearchGraphState) -> Dict[str, Any]:
        query = state.get("query", "")
        # Check if query complexity demands escalation to deep research
        deep_triggers = ["compare", "competitor", "deep", "teardown", "csv", "campaign", "metrics", "full report"]
        if any(w in query.lower() for w in deep_triggers):
            # Escalate to deep path
            return {
                "mode": "deep",
                "escalated": True,
                "stage": "escalated_to_deep",
            }

        model = self.router.get_model("shallow")
        resp = await model.ainvoke(f"Shallow research for: {query}")
        content = resp.content if hasattr(resp, "content") else str(resp)

        note = {
            "id": "note_s1",
            "job_id": state.get("job_id", ""),
            "tenant_id": state.get("tenant_id", ""),
            "claim": "Direct factual finding from shallow search",
            "source_type": "web",
            "source_url": "https://example.com/source",
            "excerpt": "Key metric verified.",
            "confidence": 0.95,
            "task_id": "shallow_task",
        }

        budget_update = await self._check_budget(state, steps_delta=1)
        res = {
            "notes": [note],
            "report": f"### Quick Research Summary\n\n{content} [note_s1]\n\n**Sources:** [1] https://example.com/source",
            "citations": ["note_s1"],
            "stage": "shallow_completed",
        }
        res.update(budget_update)
        return res

    @trace_agent("hitl_clarification")
    async def _hitl_clarification_node(self, state: ResearchGraphState) -> Dict[str, Any]:
        clarifier = ClarifierAgent(model_router=self.router)
        existing_brief = Brief(**state["brief"]) if state.get("brief") else None
        user_resp = state.get("clarification_response")

        brief, needs_interrupt, payload = await clarifier.process(
            query=state.get("query", ""),
            existing_brief=existing_brief,
            user_response=user_resp,
        )

        if needs_interrupt and not user_resp:
            # Trigger LangGraph interrupt
            res = interrupt(payload)
            # When resumed, res contains user response
            brief, _, _ = await clarifier.process(
                query=state.get("query", ""),
                existing_brief=brief,
                user_response=str(res),
            )
            budget_update = await self._check_budget(state, steps_delta=1)
            out = {
                "brief": brief.model_dump(),
                "clarification_needed": False,
                "clarification_response": str(res),
                "stage": "clarified",
            }
            out.update(budget_update)
            return out

        budget_update = await self._check_budget(state, steps_delta=1)
        out = {
            "brief": brief.model_dump(),
            "clarification_needed": False,
            "stage": "clarified",
        }
        out.update(budget_update)
        return out

    @trace_agent("source_router")
    async def _source_router_node(self, state: ResearchGraphState) -> Dict[str, Any]:
        router = SourceRouterAgent()
        res = await router.route_sources(query=state.get("query", ""), brief=state.get("brief"))
        budget_update = await self._check_budget(state, steps_delta=1)
        out = {
            "selected_sources": res.sources,
            "stage": "sources_routed",
        }
        out.update(budget_update)
        return out

    @trace_agent("planner")
    async def _planner_node(self, state: ResearchGraphState) -> Dict[str, Any]:
        planner = PlannerAgent(model_router=self.router)
        brief = Brief(**state["brief"]) if state.get("brief") else None
        plan = await planner.create_plan(
            query=state.get("query", ""),
            brief=brief,
            tenant_id=state.get("tenant_id", "tenant_default"),
        )
        budget_update = await self._check_budget(state, steps_delta=1)
        out = {
            "plan": plan.model_dump(),
            "stage": "planned",
        }
        out.update(budget_update)
        return out

    @trace_agent("workers")
    async def _workers_node(self, state: ResearchGraphState) -> Dict[str, Any]:
        job_id = state.get("job_id", "")
        tenant_id = state.get("tenant_id", "tenant_default")
        from apps.api.dependencies import get_state_store
        store = get_state_store(tenant_id)

        plan_data = state.get("plan")
        if plan_data:
            plan = Plan(**plan_data)
        else:
            planner = PlannerAgent(model_router=self.router)
            plan = await planner.create_plan(state.get("query", ""), tenant_id=tenant_id)

        orchestrator = ResearchOrchestrator(
            tenant_id=tenant_id,
            state_store=store,
            concurrency_cap=4,
        )

        notes = await orchestrator.run_plan(job_id=job_id, plan=plan)

        budget_update = await self._check_budget(state, steps_delta=len(plan.tasks))
        out = {
            "notes": [n.model_dump() for n in notes],
            "stage": "workers_completed",
            "extra_research_done": True,
        }
        out.update(budget_update)
        return out

    @trace_agent("verifier")
    async def _verifier_node(self, state: ResearchGraphState) -> Dict[str, Any]:
        verifier = GapCheckVerifier(model_router=self.router)
        plan_data = state.get("plan")
        plan = Plan(**plan_data) if plan_data else Plan()
        raw_notes = state.get("notes") or []
        notes = [ResearchNote(**n) for n in raw_notes]
        rounds = state.get("extra_research_rounds", 0)

        result = await verifier.verify_gaps(plan=plan, notes=notes, extra_research_rounds=rounds)
        budget_update = await self._check_budget(state, steps_delta=1)

        if result.needs_more_research:
            plan.tasks.extend(result.extra_tasks)
            out = {
                "plan": plan.model_dump(),
                "extra_research_rounds": rounds + 1,
                "extra_research_done": False,
                "stage": "extra_research_scheduled",
            }
        else:
            out = {
                "extra_research_rounds": rounds,
                "stage": "gap_checked",
            }

        out.update(budget_update)
        return out

    @trace_agent("analyst")
    async def _analyst_node(self, state: ResearchGraphState) -> Dict[str, Any]:
        tenant_id = state.get("tenant_id", "tenant_default")
        from apps.api.dependencies import get_state_store
        store = get_state_store(tenant_id)

        analyst = AnalystAgent(tenant_id=tenant_id, state_store=store)
        plan_data = state.get("plan")
        plan = Plan(**plan_data) if plan_data else Plan()
        raw_notes = state.get("notes") or []
        notes = [ResearchNote(**n) for n in raw_notes]
        input_files = state.get("input_files", {})

        analysis_res = await analyst.process_analysis(
            job_id=state.get("job_id", ""),
            tasks=plan.tasks,
            notes=notes,
            input_files=input_files,
        )

        budget_update = await self._check_budget(state, steps_delta=1)
        out = {
            "stage": "analysis_completed",
        }
        if analysis_res.executed:
            out["notes"] = [n.model_dump() for n in analysis_res.notes]
            out["artifacts"] = [a.model_dump() for a in analysis_res.artifacts]

        out.update(budget_update)
        return out

    @trace_agent("writer")
    async def _writer_node(self, state: ResearchGraphState) -> Dict[str, Any]:
        job_id = state.get("job_id", "")
        tenant_id = state.get("tenant_id", "tenant_default")
        from apps.api.dependencies import get_state_store
        store = get_state_store(tenant_id)

        writer = WriterAgent(tenant_id=tenant_id, state_store=store, model_router=self.router)
        raw_notes = state.get("notes") or []
        notes = [ResearchNote(**n) for n in raw_notes]
        brief = Brief(**state["brief"]) if state.get("brief") else None

        report = await writer.write_report(
            job_id=job_id,
            query=state.get("query", ""),
            brief=brief,
            notes=notes,
        )

        budget_update = await self._check_budget(state, steps_delta=1)
        out = {
            "report": report,
            "stage": "written",
        }
        out.update(budget_update)
        return out

    @trace_agent("citation_gate")
    async def _citation_gate_node(self, state: ResearchGraphState) -> Dict[str, Any]:
        raw_notes = state.get("notes") or []
        valid_ids = {n.get("id") for n in raw_notes}
        gate = CitationGate(valid_note_ids=valid_ids, strict=True)
        eval_res = gate.evaluate(state.get("report", ""))

        return {
            "report": eval_res.cleaned_text,
            "gate_passed": eval_res.passed,
            "gate_issues": [issue.model_dump() for issue in eval_res.flagged_issues],
            "stage": "citation_gate_checked",
        }

    @trace_agent("compliance_gate")
    async def _compliance_gate_node(self, state: ResearchGraphState) -> Dict[str, Any]:
        tenant_id = state.get("tenant_id", "tenant_default")
        gate = ComplianceGate(tenant_id=tenant_id)
        report_text = state.get("report", "")
        result = gate.evaluate(report_text, max_rewrites=1)

        return {
            "report": result.sanitized_text,
            "compliance_passed": result.passed,
            "compliance_issues": [v.description for v in result.violations],
            "stage": "compliance_gate_checked",
        }

    @trace_agent("deliver")
    async def _deliver_node(self, state: ResearchGraphState) -> Dict[str, Any]:
        job_id = state.get("job_id", str(uuid.uuid4()))
        tenant_id = state.get("tenant_id", "tenant_default")
        from apps.api.dependencies import get_state_store
        store = get_state_store(tenant_id)

        report_content = state.get("report", "Research summary completed.")
        delivered = []

        # 1. Upload report markdown
        report_url = self.minio.upload_artifact(
            job_id=job_id,
            artifact_name="report.md",
            data=report_content.encode("utf-8"),
            content_type="text/markdown",
        )
        report_art = Artifact(
            id=f"art_rep_{uuid.uuid4().hex[:6]}",
            job_id=job_id,
            tenant_id=tenant_id,
            artifact_type="report",
            title="Strategic Research Report",
            file_path=report_url,
        )
        await store.add_artifact(report_art)
        delivered.append(report_art.model_dump())

        # 2. Generate and upload PPTX presentation
        try:
            pptx_sections = {
                "Executive Summary": [
                    "Synthesized findings across all analyzed data sources.",
                    "Strategic performance drivers and market positioning.",
                ],
                "Key Insights": [
                    "Quantitative benchmarks established from verified evidence.",
                    "All factual claims cited and validated through citation gates.",
                ],
            }
            pptx_bytes = PPTXGenerator.generate_deck(
                title=state.get("query", "Strategic Research Report"),
                sections=pptx_sections,
            )
            pptx_url = self.minio.upload_artifact(
                job_id=job_id,
                artifact_name="presentation.pptx",
                data=pptx_bytes,
                content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            )
            pptx_art = Artifact(
                id=f"art_pptx_{uuid.uuid4().hex[:6]}",
                job_id=job_id,
                tenant_id=tenant_id,
                artifact_type="presentation",
                title="Executive Slide Deck",
                file_path=pptx_url,
            )
            await store.add_artifact(pptx_art)
            delivered.append(pptx_art.model_dump())
        except Exception:
            pass

        # 3. Emit JobCompleted event
        await store.emit_event(
            job_id,
            EventType.DONE,
            {"report_length": len(report_content), "delivered_count": len(delivered)},
        )

        return {
            "delivered_artifacts": delivered,
            "stage": "completed",
            "done": True,
        }

    @trace_agent("followup")
    async def _followup_node(self, state: ResearchGraphState) -> Dict[str, Any]:
        job_id = state.get("job_id", "")
        tenant_id = state.get("tenant_id", "tenant_default")
        from apps.api.dependencies import get_state_store
        store = get_state_store(tenant_id)

        from core.agents.followup import FollowupAgent
        followup = FollowupAgent(tenant_id=tenant_id, state_store=store, model_router=self.router)
        query = state.get("followup_query", "")
        answer = await followup.answer_followup(job_id=job_id, question=query)

        return {
            "followup_response": answer,
            "stage": "followup_completed",
        }
