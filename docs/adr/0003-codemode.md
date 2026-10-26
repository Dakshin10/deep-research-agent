# ADR 0003: Cloudflare Code Mode Tool Layer & Sandbox Architecture

**Status**: Accepted  
**Date**: 2026-10-26  
**Deciders**: Principal Engineering Team  
**Scope**: Code Mode MCP Server, Dynamic Workers sandbox, SDK generation, and offline fallback backend.

---

## 1. Context & Problem Statement

In the previous prototype, agent tool access was implemented either as individual LangChain tools or direct function bindings. As the product expands to cover:
- Deep research workflows (parallel fan-out, SearXNG, academic, code, forums)
- Idea mining (crawler frontier, extraction, clustering, trends, generator)
- Knowledge base & temporal memory retrieval
- Upstream MCP servers (GA4, HubSpot, HRMS, GitHub, Reddit, etc.)
- Public web APIs

Registering every single endpoint as an individual MCP tool schema inflates the LLM context window with tens of thousands of tokens per turn (50+ endpoints can easily consume 30,000–60,000 prompt tokens). Furthermore, multi-step actions require multiple LLM round-trips to filter, join, and paginate data.

We need a unified tool interface where:
1. The agent sees only **TWO** universal tools: `search(code)` and `execute(code)`.
2. Model-generated JavaScript executes securely in an isolated sandbox.
3. Multi-call operations (such as parallel fan-out across 10+ sources) can execute in a single turn via `Promise.all`.
4. Credentials never leak into the sandbox or model prompt.
5. Outbound network traffic is strictly mediated by a host-level security gate.
6. Local development and CI tests can run completely offline without Cloudflare paid account barriers.

---

## 2. Research & Up-to-Date Cloudflare Specifications

Based on official documentation from Cloudflare Agents SDK (v0.20.0+), Model Context Protocol SDK v2 (`@modelcontextprotocol/server@2.0.0`), and the open-source reference `ancs21/codemode-workers`:

### A. The Code Mode Pattern (`search` + `execute`)
- **`search(code)`**: Runs inside an isolated JavaScript context with **no network access**. It queries an in-memory catalog containing OpenAPI specs and TypeScript declarations. It returns only the exact method signatures and type definitions matching the model's query, preserving a flat, minimal token footprint.
- **`execute(code)`**: Takes a JavaScript snippet written by the model and executes it inside a secure sandbox where only a typed `api.*` SDK is injected. Intermediate filtering, array transformations, and joins execute inside the V8 isolate. Only the final structured return value is passed back to the LLM.

### B. Cloudflare Dynamic Workers & Worker Loader
- Dynamic Workers provision isolated V8 environments on demand in milliseconds via Cloudflare's Worker Loader API (`env.LOADER.load()`).
- Configuration:
  ```jsonc
  {
    "worker_loaders": [
      {
        "binding": "LOADER"
      }
    ]
  }
  ```
- **Sandbox Isolation**:
  - `globalOutbound: null` is set on dynamically loaded workers, completely blocking unmediated internet access.
  - Filesystem access and environment variable access are disabled.
  - Sandboxed code cannot read `process.env` or Cloudflare `env` secrets.
- **Host Security Gate**:
  - The dynamic worker communicates with external services exclusively through a host-provided proxy bridge (`codemode.request` / `api.*`).
  - The gate verifies host allowlists (FastAPI backend, approved MCP endpoints, public APIs), injects credentials securely outside the sandbox, enforces concurrency caps, timeout limits, and result payload truncation.

### C. MCP Server Handler Migration: `createMcpHandler` vs `McpAgent`
- **Legacy (`McpAgent`)**: Relied on stateful Cloudflare Durable Objects to maintain long-lived SSE/WebSocket protocol sessions.
- **Current Recommended (`createMcpHandler`)**: Cloudflare Agents SDK v0.20.0+ and MCP SDK v2 officially transitioned to `createMcpHandler` for stateless HTTP Workers.
  ```typescript
  import { McpServer } from "@modelcontextprotocol/server";
  import { createMcpHandler } from "agents/mcp/server";

  function createServer() {
    const server = new McpServer({ name: "codemode-worker", version: "1.0.0" });
    server.tool("search", { code: z.string() }, async ({ code }) => { ... });
    server.tool("execute", { code: z.string() }, async ({ code }) => { ... });
    return server;
  }

  export default {
    fetch(request: Request, env: Env, ctx: ExecutionContext) {
      return createMcpHandler(createServer)(request, env, ctx);
    }
  };
  ```

### D. Plan, Pricing, and Runtime Limits
- **Cloudflare Plans**: Dynamic Workers / Worker Loader bindings currently require a Cloudflare Workers Paid plan ($5/mo minimum) or Workers for Platforms enterprise licensing.
- **Execution Limits**:
  - CPU Time: 50ms default on free; up to 30s (or 15 min on Unbound) on Paid plans.
  - Memory: 128MB default up to 512MB.
  - Subrequests: 50 on Free, 1000 on Paid (plenty for `Promise.all` fan-out of 10–50 parallel shards).

---

## 3. Decision: Dual-Backend Architecture (`CodeModeBackend`)

To ensure development velocity, zero-dependency CI runs, and seamless Cloudflare deployment, we define an abstract interface:

```python
class CodeModeBackend(Protocol):
    async def search(self, query: str, *, tenant_id: str) -> str: ...
    async def execute(self, code: str, *, tenant_id: str, approval_token: Optional[str] = None) -> Dict[str, Any]: ...
```

### Implementations:
1. **`CloudflareBackend` (Production)**:
   - Connects to the Cloudflare Worker via `langchain-mcp-adapters` or HTTP/SSE JSON-RPC.
   - Dynamic Worker isolate runs on Cloudflare Edge with Worker Loader.
   - Token-authenticated with per-tenant signed JWTs.
2. **`LocalBackend` (Development & CI)**:
   - Runs locally in Python using Node.js / Deno or a secure sandbox process with the exact same generated TypeScript/JavaScript SDK and gate.
   - Network disabled for user code; outbound calls routed via a Python supervisor HTTP proxy that enforces the identical host allowlist and credential injection.
   - Allows all unit and integration tests to pass locally on Windows/Linux without requiring an active Cloudflare Paid subscription or internet connection.

---

## 4. Security & Safety Model

1. **Host & Path Allowlist**: Outbound requests from `execute` are restricted to:
   - Internal FastAPI services: `/v1/research/*`, `/v1/ideas/*`, `/v1/crawl/*`, `/v1/kb/*`, `/v1/memory/*`.
   - Verified upstream public APIs: GitHub API, arXiv API, Reddit JSON, Hacker News Algolia, OpenAlex, Wikipedia.
   - Configured MCP server endpoints.
2. **Read-Only by Default**:
   - Mutating calls (POST, PUT, DELETE, triggering crawlers or mutating memory) require an `approval_token` generated by the user through the chat interface approval card.
3. **No Credential Exposure**:
   - API tokens (`GROQ_API_KEY`, `TAVILY_API_KEY`, `MINIO_SECRET_KEY`, OAuth tokens) exist solely in host environment memory and are injected at the HTTP request boundary.
4. **Untrusted Data Fencing**:
   - All tool responses returned to the model are wrapped in `<untrusted_tool_result>` tags to prevent indirect prompt injection.
5. **Audit Logging**:
   - Every `execute()` call logs: tenant ID, code hash, timestamp, duration, endpoints contacted, payload size, and approval status.

---

## 5. Consequences & Verification

- **Pros**:
  - Dramatic context compression: ~500 tokens for tool definitions instead of 30,000+.
  - Rapid multi-call fan-out in single turn (`Promise.all`).
  - Defense-in-depth: sandboxed V8 execution + out-of-sandbox proxy gate.
  - Zero test friction: `LocalBackend` ensures 100% green offline tests.
- **Verification**:
  - Test suite in `tests/test_codemode_gate.py` validates host allowlist, credential isolation, timeout caps, mutation approval enforcement, and prompt injection fencing.
  - Benchmark suite in `docs/benchmarks/codemode.md` measuring prompt token savings, round-trip latency, and execution reliability.
