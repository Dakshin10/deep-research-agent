from __future__ import annotations

import re
from typing import List, Optional
from pydantic import BaseModel, Field

from core.models.router import ModelRouter
from core.state.schemas import Brief, PlanTask


class SubQuery(BaseModel):
    """Represents a targeted sub-query assigned to a parallel research shard."""
    query: str
    source_family: str = "web_general"
    entity: str = ""


class QueryExpander:
    """
    Turns each PlanTask into 5-20 diverse sub-queries tagged by source_family:
    - Synonyms & conceptual variants
    - 'site:' targeted forms for forums (Reddit, HN) and code (GitHub)
    - Question forms ("is X good for Y", "X vs Y")
    - Academic & benchmark queries (arXiv, papers)
    - Video demonstrations & walkthroughs
    - Multi-language geography-targeted forms when relevant
    """

    def __init__(self, model_router: Optional[ModelRouter] = None):
        self.router = model_router or ModelRouter()

    async def expand(
        self,
        task: PlanTask,
        brief: Optional[Brief] = None,
        min_queries: int = 5,
        max_queries: int = 15,
    ) -> List[SubQuery]:
        entity = task.entity
        objective = task.objective
        results: List[SubQuery] = []

        # 1. Web General
        results.append(SubQuery(query=f"{entity} {objective}", source_family="web_general", entity=entity))
        results.append(SubQuery(query=f"{entity} architecture capabilities overview", source_family="web_general", entity=entity))
        results.append(SubQuery(query=f"{entity} enterprise pricing tiers SLA", source_family="web_general", entity=entity))

        # 2. Forums (Reddit, HN, community reviews)
        results.append(SubQuery(query=f"site:reddit.com {entity} production experience review", source_family="forums", entity=entity))
        results.append(SubQuery(query=f"site:news.ycombinator.com {entity} discussion", source_family="forums", entity=entity))
        results.append(SubQuery(query=f"is {entity} good for {objective} questions", source_family="forums", entity=entity))

        # 3. Code (GitHub, developer repos, SDKs)
        results.append(SubQuery(query=f"site:github.com {entity} api client sdk", source_family="code", entity=entity))
        results.append(SubQuery(query=f"{entity} open source implementation repository", source_family="code", entity=entity))

        # 4. Academic & Technical Papers
        results.append(SubQuery(query=f"arxiv {entity} evaluation benchmark methodology", source_family="academic", entity=entity))
        results.append(SubQuery(query=f"{entity} empirical performance study", source_family="academic", entity=entity))

        # 5. Video (Demos, Tech Talks)
        results.append(SubQuery(query=f"{entity} demo architecture deep dive talk", source_family="video", entity=entity))

        # 6. Social Sentiment
        results.append(SubQuery(query=f"{entity} thoughts user feedback", source_family="social", entity=entity))

        # 7. News / Press Releases
        results.append(SubQuery(query=f"{entity} latest release announcement funding", source_family="news", entity=entity))

        # 8. Geographic / Language Variations
        if brief and brief.geography and brief.geography.lower() not in ("global", "us", "north america"):
            geo = brief.geography.strip()
            results.append(SubQuery(query=f"{entity} {objective} {geo} market", source_family="web_general", entity=entity))

        # Limit to max_queries
        return results[:max_queries]
