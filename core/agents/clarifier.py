from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple
from core.models.router import ModelRouter
from core.tools.search import SearchService
from core.knowledge.store import KnowledgeStore
from core.state.schemas import Brief


class ClarifierAgent:
    """Evaluates query context via background lookups and determines missing brief dimensions."""

    ALL_FIELDS = ["audience", "geography", "goal_kpi", "budget", "brand_voice", "named_competitors"]

    def __init__(
        self,
        model_router: Optional[ModelRouter] = None,
        search_service: Optional[SearchService] = None,
        knowledge_store: Optional[KnowledgeStore] = None,
    ):
        self.router = model_router or ModelRouter()
        self.search_service = search_service or SearchService()
        self.knowledge_store = knowledge_store

    async def process(
        self,
        query: str,
        existing_brief: Optional[Brief] = None,
        user_response: Optional[str] = None,
    ) -> Tuple[Brief, bool, Optional[Dict[str, Any]]]:
        brief = existing_brief or Brief()

        # Incorporate user response from previous interrupt round if present
        if user_response:
            brief.clarification_round += 1
            brief.extra_context = (brief.extra_context or "") + f"\nUser Input Round {brief.clarification_round}: {user_response}"
            self._extract_fields_from_text(user_response, brief)

        # Quick background search and KB lookup to enrich context
        bg_search = await self.search_service.search(query, max_results=1)
        bg_context = bg_search[0].content if bg_search else ""
        if self.knowledge_store:
            kb_res = await self.knowledge_store.retrieve(query, top_k=1)
            if kb_res:
                bg_context += "\n" + kb_res[0]["text"]

        # Parse query itself for obvious entity mentions
        self._extract_fields_from_text(query, brief)

        # Determine which fields are still missing
        missing = []
        if not brief.audience:
            missing.append("audience")
        if not brief.geography:
            missing.append("geography")
        if not brief.goal_kpi:
            missing.append("goal_kpi")
        if not brief.named_competitors:
            # Check if competitors were mentioned in query
            comps = self._detect_competitors(query)
            if comps:
                brief.named_competitors = comps
            else:
                missing.append("named_competitors")

        brief.missing_fields = missing

        # Enforce max 2 rounds constraint
        if missing and brief.clarification_round < 2:
            questions = []
            if "audience" in missing:
                questions.append("Who is your primary target audience?")
            if "geography" in missing:
                questions.append("Which geographic regions (e.g., North America, EMEA) should be analyzed?")
            if "goal_kpi" in missing:
                questions.append("What specific KPI or business goal is this research supporting?")
            if "named_competitors" in missing:
                questions.append("Which named competitors would you like benchmarked?")

            interrupt_payload = {
                "missing_fields": missing,
                "questions": questions,
                "round": brief.clarification_round + 1,
            }
            return brief, True, interrupt_payload

        # No interrupt needed; brief is ready
        return brief, False, None

    def _extract_fields_from_text(self, text: str, brief: Brief):
        text_lower = text.lower()
        if not brief.geography:
            for geo in ["north america", "us", "usa", "europe", "emea", "apac", "global"]:
                if geo in text_lower:
                    brief.geography = geo.upper()
                    break

        if not brief.audience:
            for aud in ["enterprise", "b2b", "mid-market", "smb", "consumers", "gen z", "developers"]:
                if aud in text_lower:
                    brief.audience = aud.capitalize()
                    break

        if not brief.goal_kpi:
            for kpi in ["market share", "churn reduction", "cac", "revenue growth", "conversion rate", "ctr"]:
                if kpi in text_lower:
                    brief.goal_kpi = kpi.title()
                    break

    def _detect_competitors(self, query: str) -> List[str]:
        # Known SaaS/marketing entities or regex detection
        known = ["hubspot", "salesforce", "zoho", "marketo", "activecampaign", "klaviyo", "mailchimp", "apollo", "braze"]
        found = [name.capitalize() for name in known if name in query.lower()]
        return found
