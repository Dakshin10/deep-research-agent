from __future__ import annotations

import json
from typing import Optional
from pydantic import BaseModel, Field

from core.models.router import ModelRouter
from core.state.schemas import JobMode


class IntentClassificationResult(BaseModel):
    mode: JobMode
    confidence: float = Field(ge=0.0, le=1.0)
    direct_reply: Optional[str] = None


class IntentClassifier:
    """Fast-model intent classifier that determines shallow, deep, clarify, or chit-chat."""

    PROMPT_TEMPLATE = """You are an intent classification engine for a deep research assistant.
Analyze the user's research request and classify it into one of four modes:
- "chit_chat": General greetings, meta questions about capabilities, or casual conversation.
- "shallow": Quick factual queries, single-metric lookups, definitions, or questions answerable in seconds with 1-3 tool searches.
- "clarify": Ambiguous, high-stakes, or complex deep research queries that miss crucial parameters like target audience, geography, or specific KPI.
- "deep": Complex multi-entity research, competitor comparisons, market landscapes, or in-depth strategic reports.

Return ONLY a valid JSON object matching:
{
  "mode": "shallow" | "deep" | "clarify" | "chit_chat",
  "confidence": 0.0 - 1.0,
  "reply": "string optional if chit_chat"
}

User Query: {query}
"""

    def __init__(self, model_router: Optional[ModelRouter] = None):
        self.router = model_router or ModelRouter()

    async def classify(self, query: str) -> IntentClassificationResult:
        try:
            model = self.router.get_model("classifier")
            prompt = self.PROMPT_TEMPLATE.replace("{query}", query)
            resp = await model.ainvoke(prompt)
            content = resp.content if hasattr(resp, "content") else str(resp)

            # Extract json block if surrounded by markdown code fences
            if "```" in content:
                content = content.split("```")[1].strip()
                if content.startswith("json"):
                    content = content[4:].strip()
            data = json.loads(content)
            mode_str = data.get("mode", "deep").lower()
            mode = JobMode(mode_str)
            confidence = float(data.get("confidence", 0.9))
            reply = data.get("reply")
            return IntentClassificationResult(mode=mode, confidence=confidence, direct_reply=reply)
        except Exception:
            # Fallback heuristic
            q_lower = query.lower()
            if any(w in q_lower for w in ["hello", "hi", "who are you", "what can you do"]):
                return IntentClassificationResult(
                    mode=JobMode.CHIT_CHAT,
                    confidence=1.0,
                    direct_reply="Hello! I am your AI Deep Researcher.",
                )
            elif any(w in q_lower for w in ["compare", "competitor", "market landscape", "deep dive", "audit"]):
                return IntentClassificationResult(mode=JobMode.DEEP, confidence=0.95)
            elif any(w in q_lower for w in ["clarify", "ambiguous"]):
                return IntentClassificationResult(mode=JobMode.CLARIFY, confidence=0.90)
            return IntentClassificationResult(mode=JobMode.SHALLOW, confidence=0.85)
