"""
Catalog and TypeScript SDK declaration generator.

Extracts typed definitions from FastAPI application and generates:
- TypeScript d.ts declaration text for the model prompt
- Structured JSON catalog for the search(code) tool
"""

import json
from typing import Any


DEFAULT_SDK_DECLARATION = """// Deep Research Agent - Code Mode Typed SDK
// Available globally as `api.*`. Return only the specific data needed.

declare namespace api {
  namespace research {
    /**
     * Start an autonomous deep research job with parallel query fan-out and location-verified notes.
     */
    function deep(params: {
      query: string;
      breadth?: number;
      depth?: number;
      budget_seconds?: number;
    }): Promise<{
      job_id: string;
      status: string;
      shards_count: number;
      findings_summary: string;
      citations_count: number;
    }>;

    /**
     * Fetch status and live progress of a running deep research job.
     */
    function status(params: { job_id: string }): Promise<{
      job_id: string;
      stage: string;
      active_shards: number;
      completed_shards: number;
      budget_used_pct: number;
    }>;
  }

  namespace ideas {
    /**
     * Search mined hackathon ideas, problem statements, and cluster trends.
     */
    function search(params: {
      query: string;
      tag?: string;
      min_score?: number;
      limit?: number;
    }): Promise<Array<{
      id: string;
      title: string;
      problem: string;
      solution: string;
      novelty_score: number;
      tags: string[];
    }>>;

    /**
     * Generate novel IdeaCards synthesized across problem domains.
     */
    function generate(params: {
      prompt: string;
      target_domain?: string;
      count?: number;
    }): Promise<Array<{
      title: string;
      problem_statement: string;
      proposed_solution: string;
      target_audience: string;
      tech_stack: string[];
      differentiation: string;
    }>>;

    /**
     * Get macro and micro opportunity trends across all mined hackathons.
     */
    function trends(params: { domain?: string }): Promise<{
      clusters: Array<{ name: string; size: number; growth_rate: number }>;
      emerging_technologies: string[];
    }>;
  }

  namespace crawl {
    /**
     * Launch or inspect continuous web and platform crawlers.
     */
    function start(params: { source: string; max_depth?: number }): Promise<{
      crawl_id: string;
      status: string;
      urls_queued: number;
    }>;
  }

  namespace kb {
    /**
     * Search verified documents and research notes with exact character offsets.
     */
    function search(params: { query: string; limit?: number }): Promise<Array<{
      note_id: string;
      title: string;
      url: string;
      excerpt: string;
      location: string;
      text_fragment_url: string;
    }>>;
  }

  namespace memory {
    /**
     * Recall temporal facts, entities, and relationship histories.
     */
    function recall(params: { query: string; entity?: string }): Promise<Array<{
      id: string;
      entity: string;
      relation: string;
      target: string;
      fact: string;
      valid_from: string;
      valid_to?: string;
    }>>;

    /**
     * Propose remembering a new fact or updating an existing entity relation.
     */
    function remember(params: {
      entity: string;
      relation: string;
      target: string;
      fact: string;
    }): Promise<{ status: string; id: string }>;
  }

  namespace web {
    /**
     * Execute privacy-preserving search over SearXNG metasearch instance.
     */
    function search(params: { query: string; limit?: number }): Promise<Array<{
      title: string;
      url: string;
      snippet: string;
    }>>;

    /**
     * Tiered fetch (Trafilatura/Playwright) returning clean Markdown text.
     */
    function fetch(params: { url: string }): Promise<{
      url: string;
      title: string;
      content: string;
      status_code: number;
    }>;
  }

  namespace github {
    function searchRepos(params: { query: string; limit?: number }): Promise<any>;
    function getRepo(params: { owner: string; repo: string }): Promise<any>;
  }

  namespace analytics {
    function query(params: { metric: string; date_range: string }): Promise<any>;
  }
}
"""

CATALOG_METADATA = [
    {
        "namespace": "api.research",
        "method": "deep",
        "description": "Start an autonomous deep research job with parallel query fan-out and location-verified notes.",
        "params": ["query", "breadth", "depth", "budget_seconds"],
        "is_mutation": False,
    },
    {
        "namespace": "api.research",
        "method": "status",
        "description": "Fetch status and live progress of a running deep research job.",
        "params": ["job_id"],
        "is_mutation": False,
    },
    {
        "namespace": "api.ideas",
        "method": "search",
        "description": "Search mined hackathon ideas, problem statements, and cluster trends.",
        "params": ["query", "tag", "min_score", "limit"],
        "is_mutation": False,
    },
    {
        "namespace": "api.ideas",
        "method": "generate",
        "description": "Generate novel IdeaCards synthesized across problem domains.",
        "params": ["prompt", "target_domain", "count"],
        "is_mutation": False,
    },
    {
        "namespace": "api.ideas",
        "method": "trends",
        "description": "Get macro and micro opportunity trends across all mined hackathons.",
        "params": ["domain"],
        "is_mutation": False,
    },
    {
        "namespace": "api.crawl",
        "method": "start",
        "description": "Launch or inspect continuous web and platform crawlers.",
        "params": ["source", "max_depth"],
        "is_mutation": True,
    },
    {
        "namespace": "api.kb",
        "method": "search",
        "description": "Search verified documents and research notes with exact character offsets.",
        "params": ["query", "limit"],
        "is_mutation": False,
    },
    {
        "namespace": "api.memory",
        "method": "recall",
        "description": "Recall temporal facts, entities, and relationship histories.",
        "params": ["query", "entity"],
        "is_mutation": False,
    },
    {
        "namespace": "api.memory",
        "method": "remember",
        "description": "Propose remembering a new fact or updating an existing entity relation.",
        "params": ["entity", "relation", "target", "fact"],
        "is_mutation": True,
    },
    {
        "namespace": "api.web",
        "method": "search",
        "description": "Execute privacy-preserving search over SearXNG metasearch instance.",
        "params": ["query", "limit"],
        "is_mutation": False,
    },
    {
        "namespace": "api.web",
        "method": "fetch",
        "description": "Tiered fetch (Trafilatura/Playwright) returning clean Markdown text.",
        "params": ["url"],
        "is_mutation": False,
    },
    {
        "namespace": "api.github",
        "method": "searchRepos",
        "description": "Search GitHub repositories by query.",
        "params": ["query", "limit"],
        "is_mutation": False,
    },
    {
        "namespace": "api.analytics",
        "method": "query",
        "description": "Query analytics data (GA4, HubSpot read-only).",
        "params": ["metric", "date_range"],
        "is_mutation": False,
    },
]


def get_sdk_declaration() -> str:
    """Return TypeScript declaration text for system prompts."""
    return DEFAULT_SDK_DECLARATION


def search_catalog(query: str) -> list[dict[str, Any]]:
    """Search catalog items matching query string."""
    q = query.lower()
    results = []
    for item in CATALOG_METADATA:
        text = f"{item['namespace']}.{item['method']} {item['description']}".lower()
        if q in text or any(q in p.lower() for p in item["params"]):
            results.append(item)
    return results
