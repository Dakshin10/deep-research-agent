from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml
from pydantic import BaseModel, Field

from core.observability.tracing import trace_agent


class RouteSourcesResult(BaseModel):
    enabled: bool
    sources: List[str] = Field(default_factory=list)
    reasoning: str = ""


class SourceRouterAgent:
    """
    Selects which data sources (Tavily/Exa, Crawl4AI, GA4 MCP, HubSpot MCP, Knowledge Base)
    should be queried for a given research query, based on configuration and intent.
    """

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or os.path.join("config", "search.yaml")
        self._config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        p = Path(self.config_path)
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
            except Exception:
                pass
        return {}

    @trace_agent("source_router")
    async def route_sources(self, query: str, brief: Optional[Dict[str, Any]] = None) -> RouteSourcesResult:
        data_sources_cfg = self._config.get("data_sources", {})
        enabled = data_sources_cfg.get("enable_source_router", True)
        default_sources = data_sources_cfg.get("default_sources", ["tavily", "kb_retrieve", "crawl4ai"])

        if not enabled:
            return RouteSourcesResult(
                enabled=False,
                sources=default_sources,
                reasoning="Source router is disabled in config; using default sources.",
            )

        q_lower = query.lower()
        if brief and brief.get("goals"):
            q_lower += " " + " ".join(brief["goals"]).lower()

        sources = list(default_sources)
        reasons = ["Included base sources (web search and internal knowledge base)."]

        # GA4 MCP
        ga4_cfg = data_sources_cfg.get("ga4_mcp", {})
        if ga4_cfg.get("enabled", True):
            if any(term in q_lower for term in ["ga4", "google analytics", "traffic", "bounce rate", "sessions", "conversions", "channel"]):
                if "ga4_mcp" not in sources:
                    sources.append("ga4_mcp")
                    reasons.append("Detected analytics/traffic request: routing to GA4 MCP.")

        # HubSpot MCP
        hubspot_cfg = data_sources_cfg.get("hubspot_mcp", {})
        if hubspot_cfg.get("enabled", True):
            if any(term in q_lower for term in ["hubspot", "crm", "deals", "contacts", "pipeline", "companies", "sales"]):
                if "hubspot_mcp" not in sources:
                    sources.append("hubspot_mcp")
                    reasons.append("Detected CRM/deals request: routing to HubSpot MCP.")

        # Reddit
        reddit_cfg = data_sources_cfg.get("reddit", {})
        if reddit_cfg.get("enabled", False):
            if any(term in q_lower for term in ["reddit", "community", "sentiment", "discussions", "forum"]):
                if "reddit" not in sources:
                    sources.append("reddit")
                    reasons.append("Detected community sentiment query: routing to Reddit.")

        return RouteSourcesResult(
            enabled=True,
            sources=sources,
            reasoning="; ".join(reasons),
        )
