/**
 * Build-time generated catalog and TypeScript SDK types for Cloudflare Code Mode.
 */

export interface CatalogItem {
  namespace: string;
  method: string;
  description: string;
  params: string[];
  is_mutation: boolean;
}

export const CATALOG: CatalogItem[] = [
  {
    namespace: 'api.research',
    method: 'deep',
    description: 'Start an autonomous deep research job with parallel query fan-out and location-verified notes.',
    params: ['query', 'breadth', 'depth', 'budget_seconds'],
    is_mutation: false,
  },
  {
    namespace: 'api.research',
    method: 'status',
    description: 'Fetch status and live progress of a running deep research job.',
    params: ['job_id'],
    is_mutation: false,
  },
  {
    namespace: 'api.ideas',
    method: 'search',
    description: 'Search mined hackathon ideas, problem statements, and cluster trends.',
    params: ['query', 'tag', 'min_score', 'limit'],
    is_mutation: false,
  },
  {
    namespace: 'api.ideas',
    method: 'generate',
    description: 'Generate novel IdeaCards synthesized across problem domains.',
    params: ['prompt', 'target_domain', 'count'],
    is_mutation: false,
  },
  {
    namespace: 'api.ideas',
    method: 'trends',
    description: 'Get macro and micro opportunity trends across all mined hackathons.',
    params: ['domain'],
    is_mutation: false,
  },
  {
    namespace: 'api.crawl',
    method: 'start',
    description: 'Launch or inspect continuous web and platform crawlers.',
    params: ['source', 'max_depth'],
    is_mutation: true,
  },
  {
    namespace: 'api.kb',
    method: 'search',
    description: 'Search verified documents and research notes with exact character offsets.',
    params: ['query', 'limit'],
    is_mutation: false,
  },
  {
    namespace: 'api.memory',
    method: 'recall',
    description: 'Recall temporal facts, entities, and relationship histories.',
    params: ['query', 'entity'],
    is_mutation: false,
  },
  {
    namespace: 'api.memory',
    method: 'remember',
    description: 'Propose remembering a new fact or updating an existing entity relation.',
    params: ['entity', 'relation', 'target', 'fact'],
    is_mutation: true,
  },
  {
    namespace: 'api.web',
    method: 'search',
    description: 'Execute privacy-preserving search over SearXNG metasearch instance.',
    params: ['query', 'limit'],
    is_mutation: false,
  },
  {
    namespace: 'api.web',
    method: 'fetch',
    description: 'Tiered fetch (Trafilatura/Playwright) returning clean Markdown text.',
    params: ['url'],
    is_mutation: false,
  },
];

export const SDK_DTS = `
declare namespace api {
  namespace research {
    function deep(params: { query: string; breadth?: number; depth?: number; budget_seconds?: number }): Promise<any>;
    function status(params: { job_id: string }): Promise<any>;
  }
  namespace ideas {
    function search(params: { query: string; tag?: string; min_score?: number; limit?: number }): Promise<any>;
    function generate(params: { prompt: string; target_domain?: string; count?: number }): Promise<any>;
    function trends(params: { domain?: string }): Promise<any>;
  }
  namespace crawl {
    function start(params: { source: string; max_depth?: number }): Promise<any>;
  }
  namespace kb {
    function search(params: { query: string; limit?: number }): Promise<any>;
  }
  namespace memory {
    function recall(params: { query: string; entity?: string }): Promise<any>;
    function remember(params: { entity: string; relation: string; target: string; fact: string }): Promise<any>;
  }
  namespace web {
    function search(params: { query: string; limit?: number }): Promise<any>;
    function fetch(params: { url: string }): Promise<any>;
  }
}
`;
