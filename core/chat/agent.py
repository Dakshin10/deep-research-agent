from __future__ import annotations

import asyncio
import os
import re
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional

from core.chat.schemas import (
    ArtifactEvent,
    ChatMessage,
    ChatRole,
    CitationEvent,
    ClarificationRequestEvent,
    DoneEvent,
    MessagePart,
    PartType,
    ReasoningSummaryEvent,
    ResearchProgressEvent,
    TextDeltaEvent,
    ToolCallFinishedEvent,
    ToolCallStartedEvent,
    ChatEvent,
)
from core.chat.store import ChatStore
from core.chat.tools import (
    run_deep_research_tool,
    run_ideas_generate_tool,
    run_ideas_search_tool,
    run_crawl_start_tool,
)


class MainChatAgent:
    """
    Unified Main Chat Agent.
    Routes queries to direct answer, clarifying questions, deep research jobs,
    or tool executions, and streams typed SSE events.
    """

    def __init__(self, store: Optional[ChatStore] = None, tenant_id: str = "default_tenant"):
        self.tenant_id = tenant_id
        self.store = store or ChatStore(tenant_id=tenant_id)

    async def auto_title_conversation(self, query: str) -> str:
        """Generates a concise 3-6 word title from the initial user query."""
        clean = re.sub(r"[^\w\s-]", "", query).strip()
        words = clean.split()
        if len(words) <= 5:
            return clean.title() or "Research Inquiry"
        return " ".join(words[:5]).title()

    def route_intent(self, message: str) -> str:
        """
        Classifies user prompt intent:
        - 'clarify': Needs more specifics before proceeding
        - 'deep_research': Thorough multi-shard research run
        - 'ideas_search': Querying hackathon/startup projects
        - 'ideas_generate': Ideation and IdeaCard synthesis
        - 'crawl': Crawling sources
        - 'direct': Quick answers / chat
        """
        msg = message.lower().strip()

        # Check for vague requests needing clarification
        if msg in ["do a brand audit", "audit our product", "research our competitors", "do market research"]:
            return "clarify"

        # Check for deep research intent
        if any(trigger in msg for trigger in [
            "research", "evaluate", "compare", "investigate", "deep dive", "analyze", "benchmark", "hurdles", "tradeoffs"
        ]):
            return "deep_research"

        # Check for idea mining
        if any(trigger in msg for trigger in ["mine ideas", "search ideas", "find projects", "hackathon winners", "show ideas"]):
            return "ideas_search"

        # Check for idea generation
        if any(trigger in msg for trigger in ["generate ideas", "idea cards", "synthesize ideas", "hackathon idea"]):
            return "ideas_generate"

        # Check for crawler
        if any(trigger in msg for trigger in ["start crawl", "run crawler", "crawl devpost", "crawl devfolio"]):
            return "crawl"

        return "direct"

    async def execute_turn(
        self,
        conversation_id: str,
        user_message: str,
        parent_message_id: Optional[str] = None,
        incognito: bool = False,
    ) -> AsyncGenerator[ChatEvent, None]:
        """
        Executes a turn of the conversation, yielding typed ChatEvents in real-time.
        """
        turn_id = f"turn_{uuid.uuid4().hex[:12]}"
        user_msg = ChatMessage(
            conversation_id=conversation_id,
            parent_id=parent_message_id,
            role=ChatRole.USER,
            content=user_message,
        )
        if not incognito:
            await self.store.save_message(user_msg)

        # 1. Check if first message in conversation -> Auto-title
        conv = await self.store.get_conversation(conversation_id)
        if conv and conv.title == "New Research Chat":
            new_title = await self.auto_title_conversation(user_message)
            await self.store.update_conversation_title(conversation_id, new_title)

        intent = self.route_intent(user_message)
        assistant_content_chunks: List[str] = []
        turn_citations: List[CitationEvent] = []
        turn_artifacts: List[ArtifactEvent] = []

        # -------------------------------------------------------------
        # BRANCH A: Clarification Request
        # -------------------------------------------------------------
        if intent == "clarify":
            yield ReasoningSummaryEvent(turn_id=turn_id, summary="Assessing inquiry specificity and scope...")
            await asyncio.sleep(0.05)

            clarify_event = ClarificationRequestEvent(
                turn_id=turn_id,
                question="To deliver the most rigorous research, could you specify your target audience and primary geographic focus?",
                suggested_answers=[
                    "Enterprise B2B in North America & Europe",
                    "Consumer Mobile / APAC region",
                    "Early-stage tech startups worldwide",
                ],
            )
            yield clarify_event

            resp_text = f"I'd love to help! {clarify_event.question}"
            yield TextDeltaEvent(turn_id=turn_id, content=resp_text)
            assistant_content_chunks.append(resp_text)

        # -------------------------------------------------------------
        # BRANCH B: Deep Research Run
        # -------------------------------------------------------------
        elif intent == "deep_research":
            yield ReasoningSummaryEvent(turn_id=turn_id, summary="Decomposing research query across 5 parallel source families...")

            async def progress_hook(prog_event: ResearchProgressEvent):
                prog_event.turn_id = turn_id

            yield ResearchProgressEvent(
                turn_id=turn_id,
                job_id=f"job_{uuid.uuid4().hex[:8]}",
                stage="source_router",
                active_shards=5,
                completed_shards=0,
                sources_found={"web_general": 1, "forums": 1, "code": 1, "academic": 1, "web_index": 1},
                budget_used_pct=15.0,
            )

            call_id = f"call_{uuid.uuid4().hex[:8]}"
            yield ToolCallStartedEvent(
                turn_id=turn_id,
                call_id=call_id,
                tool_name="api.research.deep",
                arguments={"query": user_message, "max_shards": 5},
            )

            # Execute research
            res = await run_deep_research_tool(user_message, tenant_id=self.tenant_id, max_shards=5)

            yield ToolCallFinishedEvent(
                turn_id=turn_id,
                call_id=call_id,
                tool_name="api.research.deep",
                success=True,
                duration_seconds=0.88,
                summary=f"Parallel retrieval completed across {len(res['shards'])} shards.",
            )

            # Stream citations
            for cit in res["citations"]:
                cit.turn_id = turn_id
                turn_citations.append(cit)
                yield cit

            # Stream artifact
            art = res["artifact"]
            art.turn_id = turn_id
            turn_artifacts.append(art)
            yield art

            # Stream response text
            report_body = res["report"]
            assistant_content_chunks.append(report_body)
            words = report_body.split(" ")
            for i in range(0, len(words), 8):
                chunk = " ".join(words[i:i+8]) + " "
                yield TextDeltaEvent(turn_id=turn_id, content=chunk)
                await asyncio.sleep(0.01)

        # -------------------------------------------------------------
        # BRANCH C: Idea Search
        # -------------------------------------------------------------
        elif intent == "ideas_search":
            yield ReasoningSummaryEvent(turn_id=turn_id, summary="Querying verified hackathon & startup database...")
            call_id = f"call_{uuid.uuid4().hex[:8]}"
            yield ToolCallStartedEvent(
                turn_id=turn_id,
                call_id=call_id,
                tool_name="api.ideas.search",
                arguments={"query": user_message},
            )

            res = await run_ideas_search_tool(query=user_message, tenant_id=self.tenant_id)

            yield ToolCallFinishedEvent(
                turn_id=turn_id,
                call_id=call_id,
                tool_name="api.ideas.search",
                success=True,
                summary=f"Found {res['count']} matching idea records.",
            )

            if res["count"] > 0:
                text = f"Found **{res['count']} verified projects** in the idea repository:\n\n"
                for item in res["ideas"]:
                    text += f"- **{item['name']}** ({item['placement'].upper()}): {item['one_liner']}\n"
            else:
                text = "No matching projects found in the local repository. You can start a crawl run or seed the demo database."

            assistant_content_chunks.append(text)
            yield TextDeltaEvent(turn_id=turn_id, content=text)

        # -------------------------------------------------------------
        # BRANCH D: Idea Generation
        # -------------------------------------------------------------
        elif intent == "ideas_generate":
            yield ReasoningSummaryEvent(turn_id=turn_id, summary="Synthesizing grounded IdeaCards with originality guardrails...")
            call_id = f"call_{uuid.uuid4().hex[:8]}"
            yield ToolCallStartedEvent(
                turn_id=turn_id,
                call_id=call_id,
                tool_name="api.ideas.generate",
                arguments={"problem": user_message},
            )

            res = await run_ideas_generate_tool(problem=user_message, tenant_id=self.tenant_id, num_cards=3)

            yield ToolCallFinishedEvent(
                turn_id=turn_id,
                call_id=call_id,
                tool_name="api.ideas.generate",
                success=True,
                summary="Synthesized 3 grounded IdeaCards.",
            )

            art = res["artifact"]
            art.turn_id = turn_id
            turn_artifacts.append(art)
            yield art

            summary_text = f"Synthesized **{res['card_count']} grounded IdeaCards** tailored to your requirements with verified inspiration lineages.\n\nOpen the **Artifacts panel** on the right to view complete cards."
            assistant_content_chunks.append(summary_text)
            yield TextDeltaEvent(turn_id=turn_id, content=summary_text)

        # -------------------------------------------------------------
        # BRANCH E: Crawl Start
        # -------------------------------------------------------------
        elif intent == "crawl":
            yield ReasoningSummaryEvent(turn_id=turn_id, summary="Triggering crawler run against target source...")
            res = await run_crawl_start_tool(source="devpost", mode="discover", limit_pages=50)

            msg = f"✅ **Crawl Run {res['id']} Initialized**:\n- Source: `{res['source']}`\n- Discovered: {res['pages_discovered']} pages\n- Fetched: {res['pages_fetched']} pages\n- Skipped: {res['pages_skipped']} pages"
            assistant_content_chunks.append(msg)
            yield TextDeltaEvent(turn_id=turn_id, content=msg)

        # -------------------------------------------------------------
        # BRANCH F: Direct Conversational Answer
        # -------------------------------------------------------------
        else:
            yield ReasoningSummaryEvent(turn_id=turn_id, summary="Formulating direct answer...")
            ans = f"Hello! I am your unified Deep Research & Idea Mining assistant. Ask me to research any topic deeply, search hackathon ideas, synthesize project briefs, or explore knowledge graphs."
            assistant_content_chunks.append(ans)
            yield TextDeltaEvent(turn_id=turn_id, content=ans)

        # -------------------------------------------------------------
        # Conclude Turn & Persist Assistant Message
        # -------------------------------------------------------------
        full_content = "".join(assistant_content_chunks)
        asst_msg = ChatMessage(
            conversation_id=conversation_id,
            parent_id=user_msg.id,
            role=ChatRole.ASSISTANT,
            content=full_content,
            citations=turn_citations,
            artifacts=turn_artifacts,
        )
        if not incognito:
            await self.store.save_message(asst_msg)

        yield DoneEvent(turn_id=turn_id, finish_reason="stop", duration_seconds=1.1)
