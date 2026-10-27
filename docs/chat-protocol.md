# Chat Streaming Event Protocol Specification

## 1. Overview
The Deep Research Agent chat backend exposes a single unified SSE (Server-Sent Events) endpoint at `POST /v1/chat`.
Clients connect using HTTP `Accept: text/event-stream`. Events are streamed in real time as JSON payloads formatted as:

```
event: <event_type>
data: <json_serialized_payload>

```

All events carry:
- `event_id`: Unique string identifier for the event.
- `turn_id`: ID of the current assistant response turn.
- `timestamp`: UTC ISO 8601 string.
- `type`: Explicit event type string.

---

## 2. Event Types & Schemas

### 1. `text_delta`
Streams incremental markdown tokens of the assistant's direct response.
```json
{
  "type": "text_delta",
  "turn_id": "turn_abc123",
  "content": "Based on our cross-shard analysis, "
}
```

### 2. `reasoning_summary`
Provides high-level, user-facing summaries of what the agent is currently doing (not internal chain-of-thought).
```json
{
  "type": "reasoning_summary",
  "turn_id": "turn_abc123",
  "summary": "Analyzing technical trade-offs between battery chemistries..."
}
```

### 3. `tool_call_started`
Fired when the agent begins executing an internal tool or Code Mode invocation.
```json
{
  "type": "tool_call_started",
  "turn_id": "turn_abc123",
  "call_id": "call_xyz789",
  "tool_name": "api.research.deep",
  "arguments": {
    "query": "solid state battery energy density",
    "max_shards": 5
  }
}
```

### 4. `tool_call_finished`
Fired when the tool call concludes.
```json
{
  "type": "tool_call_finished",
  "turn_id": "turn_abc123",
  "call_id": "call_xyz789",
  "tool_name": "api.research.deep",
  "success": true,
  "duration_seconds": 1.45,
  "summary": "Extracted 4 verified research notes across 5 shards."
}
```

### 5. `code_execution`
Emitted when the agent executes model-generated JavaScript in the Code Mode sandbox.
```json
{
  "type": "code_execution",
  "turn_id": "turn_abc123",
  "execution_id": "exec_001",
  "code": "const results = await api.ideas.search({ domain: 'Healthcare', placement: 'winner' });\nreturn results.slice(0, 3);",
  "result": "[{\"name\": \"NeuroMesh\", \"placement\": \"winner\"}]",
  "duration_ms": 320,
  "sandboxed": true
}
```

### 6. `research_progress`
Emitted periodically during deep research runs to power the inline Live Research Card.
```json
{
  "type": "research_progress",
  "turn_id": "turn_abc123",
  "job_id": "job_res_456",
  "stage": "workers",
  "active_shards": 5,
  "completed_shards": 3,
  "sources_found": {
    "web_general": 2,
    "academic": 2,
    "code": 1
  },
  "budget_used_pct": 45.0
}
```

### 7. `citation`
Emitted for every verified factual claim linked to an exact document location.
```json
{
  "type": "citation",
  "turn_id": "turn_abc123",
  "note_id": "note_widx_8a",
  "url": "https://example.org/benchmarks",
  "title": "Tenant Web Index Benchmark Cache",
  "excerpt": "Previously verified knowledge indicates sub-15ms response times across distributed nodes.",
  "location": "Section 'Performance > Benchmarks' (offsets 140-320)",
  "text_fragment_url": "https://example.org/benchmarks#:~:text=sub-15ms%20response",
  "verified": true
}
```

### 8. `artifact`
Emitted when a multi-paragraph report, CSV, idea-card collection, or PPTX presentation is ready for the right-hand panel.
```json
{
  "type": "artifact",
  "turn_id": "turn_abc123",
  "artifact_id": "art_rep_999",
  "title": "Comprehensive Battery Chemistry Evaluation",
  "artifact_type": "report",
  "mime_type": "text/markdown",
  "download_url": "/v1/artifacts/art_rep_999/download",
  "preview_content": "## Executive Summary\n..."
}
```

### 9. `clarification_request`
Emitted when the HITL clarifier determines that the user brief is underspecified.
```json
{
  "type": "clarification_request",
  "turn_id": "turn_abc123",
  "question": "Which market region should we prioritize for this commercialization analysis?",
  "suggested_answers": [
    "North America & Europe",
    "Asia-Pacific (APAC)",
    "Global enterprise scale"
  ]
}
```

### 10. `approval_request`
Emitted when Code Mode requests a mutating action that requires user consent.
```json
{
  "type": "approval_request",
  "turn_id": "turn_abc123",
  "action_id": "act_crawl_123",
  "description": "Start a crawler run against devpost.com (max 50 pages).",
  "payload": {
    "source": "devpost",
    "mode": "discover",
    "limit_pages": 50
  }
}
```

### 11. `memory_used`
Discloses which memory items and temporal facts influenced the response.
```json
{
  "type": "memory_used",
  "turn_id": "turn_abc123",
  "memories": [
    {
      "id": "mem_01",
      "entity": "Project CarbonTrace",
      "fact": "User is building a Tier-3 supply chain carbon auditor in Python.",
      "provenance": "Conversation from Oct 19, 2026"
    }
  ]
}
```

### 12. `memory_write_proposed`
Emitted when a candidate memory was extracted from the conversation for user confirmation.
```json
{
  "type": "memory_write_proposed",
  "turn_id": "turn_abc123",
  "entity": "Tech Preferences",
  "fact": "Prefers FastAPI and LangGraph over raw OpenAI client.",
  "confidence": 0.88
}
```

### 13. `ui_action`
Emitted when the agent initiates a client-side interface state change (opening an overlay, triggering export, or changing mode) purely from natural language.
```json
{
  "type": "ui_action",
  "turn_id": "turn_abc123",
  "action": "ui.open_memory_graph",
  "payload": {
    "entity": "SolidStateBatteries",
    "section": "graph"
  }
}
```
Supported actions:
- `ui.open_memory_graph`: Opens the full-screen interactive memory canvas.
- `ui.open_sources`: Opens the slide-over source citations sheet.
- `ui.open_artifact`: Opens the right-hand panel for a specific artifact ID (`{"artifact_id": "art_123"}`).
- `ui.open_settings`: Opens the settings sheet overlay (`{"section": "models" | "codemode"}`).
- `ui.set_private_mode`: Toggles incognito mode on/off (`{"private": true}`).
- `ui.export_vault`: Triggers download of the `./vault` zip bundle.
- `ui.switch_backend`: Changes Code Mode backend (`{"backend": "local" | "cloudflare"}`).

### 14. `job_update`
Emitted when a background long-running job changes state or completes while the user is away or multi-tasking.
```json
{
  "type": "job_update",
  "turn_id": "turn_abc123",
  "job_id": "job_deep_789",
  "status": "completed",
  "progress_pct": 100.0,
  "summary": "Completed 5 shards and synthesized 12 verified notes.",
  "artifact_id": "art_rep_999"
}
```

### 15. `error`
Emitted on fatal turn errors.
```json
{
  "type": "error",
  "turn_id": "turn_abc123",
  "message": "Upstream search service unavailable after retry.",
  "code": "SEARCH_UPSTREAM_ERROR"
}
```

### 16. `done`
Emitted when the turn has completed and all parts are persisted.
```json
{
  "type": "done",
  "turn_id": "turn_abc123",
  "finish_reason": "stop",
  "total_tokens": 842,
  "duration_seconds": 2.14
}
```

---

## 3. Stream Resumability & Last-Event-ID

To support page reloads, network hiccups, and multi-turn conversations where long background jobs run asynchronously:
1. Every SSE message frame includes a sequential `id: <event_id>` line:
   ```
   id: evt_01h9x3k2
   event: research_progress
   data: {"type": "research_progress", ...}
   ```
2. When the browser reconnects, it sends the standard `Last-Event-ID` header:
   ```
   GET /v1/chat/stream?conversation_id=conv_123
   Last-Event-ID: evt_01h9x3k2
   ```
3. The server replays any buffered events occurring after `Last-Event-ID`, restoring live status lines and background research shards without restarting the run.
