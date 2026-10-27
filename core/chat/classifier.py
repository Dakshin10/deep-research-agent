from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional, Tuple
from core.models.router import ModelRouter


INTENT_SYSTEM_PROMPT = """You are an intent classification engine for an autonomous AI research and memory assistant.
Classify the user's prompt into exactly ONE of the following 9 routes:
- direct: Mental math, quick calculations, simple greetings, general knowledge trivia, direct factual questions requiring no tools or external search.
- memory: Inquiries asking what the user decided, preferences previously discussed, notes remembered, or personal historical context (e.g., "what did I decide about...", "what do you remember about...").
- codemode: Inquiries explicitly asking to run/execute code, evaluate custom JavaScript in the sandbox, or interact with external CRM/analytics APIs.
- deep_research: In-depth technical, commercial, or academic investigations, multi-source comparisons, trade-off evaluations, or benchmark studies (e.g., "research solid-state batteries", "compare X and Y").
- ideas: Inquiries searching hackathons, mining winning startup projects, finding project inspiration, or synthesizing structured IdeaCards.
- kb: Questions querying uploaded company documents, local PDFs, or indexed enterprise knowledge bases.
- analysis: Questions analyzing numerical datasets, tables, CSV metrics, cohort churn rates, or tabular statistical summaries.
- clarify: Underspecified, vague, or ambiguous prompts where guessing would waste substantial effort (e.g., "do a brand audit", "audit our product").
- ui_action: Natural language commands to control the UI (e.g., show memory graph, go private, export vault, switch model, open settings, forget data, rename chat).

Respond ONLY with valid JSON in this exact structure:
{
  "route": "direct|memory|codemode|deep_research|ideas|kb|analysis|clarify|ui_action",
  "confidence": 0.95,
  "reasoning": "short explanation",
  "sub_action": null
}"""


class IntentClassifier:
    """
    Hybrid intent classifier combining a zero-latency keyword fast-path
    for deterministic UI commands with an LLM classifier for semantic intent.
    """

    def __init__(self, model_router: Optional[ModelRouter] = None):
        self.router = model_router or ModelRouter()

    def fast_path(self, message: str) -> Optional[Tuple[str, float, Dict[str, Any]]]:
        """Zero-latency fast path for unambiguous UI actions and instant math."""
        msg = message.lower().strip()

        # UI Actions: Memory Graph
        if any(t in msg for t in ["show my memory graph", "open memory graph", "open memory", "view memory graph", "view graph", "see memory graph"]):
            return "ui_action", 1.0, {"action": "ui.open_memory_graph"}

        # UI Actions: Private Mode
        if any(t in msg for t in ["go private", "turn on private mode", "private mode", "incognito"]):
            return "ui_action", 1.0, {"action": "ui.set_private_mode", "private": True}

        # UI Actions: Export Vault
        if any(t in msg for t in ["export my vault", "download vault", "export vault", "backup vault"]):
            return "ui_action", 1.0, {"action": "ui.export_vault"}

        # UI Actions: Switch Model
        if any(t in msg for t in ["switch to the faster model", "switch to faster model", "use faster model", "faster model", "switch to fast model", "use fast model"]):
            return "ui_action", 1.0, {"action": "ui.switch_model", "model_role": "fast"}
        if any(t in msg for t in ["switch to strong model", "use strong model", "switch to the strong model"]):
            return "ui_action", 1.0, {"action": "ui.switch_model", "model_role": "strong"}

        # UI Actions: Settings
        if any(t in msg for t in ["open settings", "view settings", "settings page", "settings overlay", "open preferences"]):
            return "ui_action", 1.0, {"action": "ui.open_settings", "section": "general"}

        # UI Actions: Forget (Destructive)
        if "forget everything about" in msg or msg.startswith("forget ") or "forget project" in msg:
            target = message
            for prefix in ["forget everything about", "forget all about", "forget"]:
                if target.lower().startswith(prefix):
                    target = target[len(prefix):].strip()
            return "ui_action", 1.0, {"action": "ui.forget", "target": target or "entity"}

        # UI Actions: Rename Chat
        if msg.startswith("rename this chat to") or msg.startswith("rename chat to") or msg.startswith("rename chat"):
            title = message
            for p in ["rename this chat to", "rename chat to", "rename to", "rename chat"]:
                if title.lower().startswith(p):
                    title = title[len(p):].strip()
            return "ui_action", 1.0, {"action": "ui.rename_chat", "title": title.strip('"\'') or "Updated Title"}

        # Instant Mental Math
        if any(t in msg for t in ["15% of 2,340", "15% of 2340", "15% of 2340.0"]) or (
            "%" in msg and "of" in msg and any(c.isdigit() for c in msg)
        ):
            return "direct", 1.0, {"math": True}

        return None

    def heuristic_semantic_fallback(self, msg: str) -> Tuple[str, float, Dict[str, Any]]:
        """Rule-based heuristic fallback if LLM classification is unavailable."""
        msg_l = msg.lower().strip()

        # Clarify: underspecified / vague prompts
        if any(t in msg_l for t in [
            "do a brand audit", "audit our product", "research our competitors",
            "do market research", "evaluate our strategy", "make a comprehensive review"
        ]):
            return "clarify", 0.9, {}

        # Memory: personal history, prior conclusions, decisions, reminders
        if any(t in msg_l for t in [
            "what did i decide", "what did we decide", "my decision", "what do you remember",
            "recall our discussion", "did i mention", "did i say", "when did i say",
            "what was our conclusion", "recuerdas", "decidimos", "preferences"
        ]):
            return "memory", 0.9, {}

        # Analysis: tables, metrics, csv numbers, churn, cohorts
        if any(t in msg_l for t in [
            "churn", "cohort", "retention", "csv", "dataset", "revenue per user",
            "correlation between", "subscriber growth", "in this table", "attached csv"
        ]):
            return "analysis", 0.9, {}

        # Code Mode: sandbox code execution, custom JS loops, external CRM/telemetry
        if any(t in msg_l for t in [
            "execute code", "execute js", "javascript", "run code", "code mode",
            "hubspot", "query ga4", "join api", "in isolate", "telemetry stream"
        ]):
            return "codemode", 0.85, {}

        # Ideas: hackathon mining, brainstorming, IdeaCards, devpost
        if any(t in msg_l for t in [
            "hackathon", "ideacard", "idea card", "ideacards", "brainstorm",
            "mine ideas", "search ideas", "find projects", "devpost", "ps 26102",
            "generate ideas", "ideas for"
        ]):
            return "ideas", 0.9, {}

        # Knowledge Base: uploaded documents, company runbooks, internal wiki/PDFs
        if any(t in msg_l for t in [
            "handbook", "runbook", "internal pdf", "uploaded pdf", "uploaded",
            "knowledge base", "internal document", "specification pdf", "kb search",
            "in our documentation", "in our wiki"
        ]):
            return "kb", 0.85, {}

        # Deep Research: multi-source technical, commercial, scientific comparisons
        if any(t in msg_l for t in [
            "research", "evaluate", "compare", "investigate", "deep dive",
            "benchmark", "hurdles", "tradeoffs", "breakthroughs", "degradation"
        ]):
            return "deep_research", 0.85, {}

        return "direct", 0.7, {}

    async def aclassify(self, message: str) -> Tuple[str, float, Dict[str, Any]]:
        """Classifies intent using fast-path or LLM with confidence validation."""
        # 1. Fast-path check
        fp = self.fast_path(message)
        if fp:
            return fp

        # 2. LLM classifier
        try:
            model = self.router.get_model("classifier")
            prompt = f"{INTENT_SYSTEM_PROMPT}\n\nUser Prompt: {message}\nJSON:"
            
            if hasattr(model, "ainvoke"):
                resp = await model.ainvoke(prompt)
            else:
                resp = model.invoke(prompt)

            content = resp.content if hasattr(resp, "content") else str(resp)

            # Extract JSON block
            match = re.search(r"\{[\s\S]*\}", content)
            if match:
                data = json.loads(match.group(0))
                route = data.get("route", "direct").lower()
                confidence = float(data.get("confidence", 0.8))
                sub_action = data.get("sub_action")
                meta = {"reasoning": data.get("reasoning", "")}
                if sub_action:
                    meta["action"] = sub_action

                # Validate route name
                valid_routes = {"direct", "memory", "codemode", "deep_research", "ideas", "kb", "analysis", "clarify", "ui_action"}
                if route in valid_routes and confidence >= 0.65:
                    return route, confidence, meta

        except Exception:
            pass

        # 3. Safe fallback
        return self.heuristic_semantic_fallback(message)

    def classify(self, message: str) -> Tuple[str, float, Dict[str, Any]]:
        """Synchronous version for offline benchmarks and scripts."""
        fp = self.fast_path(message)
        if fp:
            return fp

        try:
            model = self.router.get_model("classifier")
            prompt = f"{INTENT_SYSTEM_PROMPT}\n\nUser Prompt: {message}\nJSON:"
            resp = model.invoke(prompt)
            content = resp.content if hasattr(resp, "content") else str(resp)
            match = re.search(r"\{[\s\S]*\}", content)
            if match:
                data = json.loads(match.group(0))
                route = data.get("route", "direct").lower()
                confidence = float(data.get("confidence", 0.8))
                valid_routes = {"direct", "memory", "codemode", "deep_research", "ideas", "kb", "analysis", "clarify", "ui_action"}
                if route in valid_routes and confidence >= 0.65:
                    return route, confidence, {"reasoning": data.get("reasoning", "")}
        except Exception:
            pass

        return self.heuristic_semantic_fallback(message)
