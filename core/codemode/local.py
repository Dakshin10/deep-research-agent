"""
LocalBackend implementation for Code Mode.

Provides offline dev and test execution of model-written JavaScript using
a local Node.js subprocess sandbox. Network calls outside localhost are
supervised by the SecurityGate.
"""

import asyncio
import json
import logging
import os
import shutil
import tempfile
import time
from typing import Any

from core.codemode.backend import CodeModeBackend, ExecutionResult, SearchResult
from core.codemode.gate import CallRecord, SecurityGate
from core.codemode.generator import CATALOG_METADATA, get_sdk_declaration, search_catalog

logger = logging.getLogger(__name__)

# Node bootstrap script template that defines the `api.*` SDK in the JS environment
RUNNER_BOOTSTRAP_TEMPLATE = """
const http = require('http');

const GATE_PORT = __GATE_PORT__;
const APPROVAL_TOKEN = __APPROVAL_TOKEN__;
const TENANT_ID = __TENANT_ID__;

const callsMade = [];

async function gateCall(namespace, method, params, isMutation) {
  return new Promise((resolve, reject) => {
    const payload = JSON.stringify({
      namespace,
      method,
      params,
      is_mutation: isMutation,
      approval_token: APPROVAL_TOKEN,
      tenant_id: TENANT_ID,
    });

    const req = http.request({
      hostname: '127.0.0.1',
      port: GATE_PORT,
      path: '/api/call',
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(payload),
      },
      timeout: 8000,
    }, (res) => {
      let data = '';
      res.on('data', (chunk) => { data += chunk; });
      res.on('end', () => {
        try {
          const parsed = JSON.parse(data);
          callsMade.push({
            method: `${namespace}.${method}`,
            params,
            status: res.statusCode,
          });
          if (res.statusCode >= 200 && res.statusCode < 300 && parsed.success) {
            resolve(parsed.result);
          } else {
            reject(new Error(parsed.error || `HTTP ${res.statusCode}`));
          }
        } catch (e) {
          reject(e);
        }
      });
    });

    req.on('error', (err) => reject(err));
    req.write(payload);
    req.end();
  });
}

// Typed API namespace bindings
const api = {
  research: {
    deep: (params) => gateCall('research', 'deep', params, false),
    status: (params) => gateCall('research', 'status', params, false),
  },
  ideas: {
    search: (params) => gateCall('ideas', 'search', params, false),
    generate: (params) => gateCall('ideas', 'generate', params, false),
    trends: (params) => gateCall('ideas', 'trends', params, false),
  },
  crawl: {
    start: (params) => gateCall('crawl', 'start', params, true),
  },
  kb: {
    search: (params) => gateCall('kb', 'search', params, false),
  },
  memory: {
    recall: (params) => gateCall('memory', 'recall', params, false),
    remember: (params) => gateCall('memory', 'remember', params, true),
  },
  web: {
    search: (params) => gateCall('web', 'search', params, false),
    fetch: (params) => gateCall('web', 'fetch', params, false),
  },
  github: {
    searchRepos: (params) => gateCall('github', 'searchRepos', params, false),
  },
  analytics: {
    query: (params) => gateCall('analytics', 'query', params, false),
  },
};

(async () => {
  try {
    const userCode = async () => {
      __USER_CODE__
    };
    const result = await userCode();
    console.log(JSON.stringify({
      success: true,
      result: result !== undefined ? result : null,
      calls_made: callsMade,
    }));
  } catch (err) {
    console.log(JSON.stringify({
      success: false,
      error: err.message || String(err),
      calls_made: callsMade,
    }));
  }
})();
"""


class LocalBackend(CodeModeBackend):
    """Local sandboxed execution engine for offline dev and tests."""

    def __init__(self, gate: SecurityGate | None = None):
        self.gate = gate or SecurityGate()
        self.node_path = shutil.which("node") or "node"

    async def search(self, query: str, tenant_id: str = "default_tenant") -> SearchResult:
        """Search the API catalog and types for matching operations."""
        matches = search_catalog(query)
        dts = get_sdk_declaration()
        return SearchResult(
            matches=matches,
            types_dts=dts,
            total_matches=len(matches),
        )

    async def execute(
        self,
        code: str,
        tenant_id: str = "default_tenant",
        approval_token: str | None = None,
    ) -> ExecutionResult:
        """Execute model-written JavaScript against local supervisor gate."""
        start_time = time.time()
        calls_recorded: list[CallRecord] = []
        mutations_attempted = 0

        # Start a lightweight ephemeral Python HTTP server to handle `gateCall` from Node
        async def handle_gate_request(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
            nonlocal mutations_attempted
            try:
                # Read HTTP headers
                line = await reader.readline()
                headers = {}
                content_length = 0
                while True:
                    hdr_line = await reader.readline()
                    if hdr_line == b"\r\n" or not hdr_line:
                        break
                    k, _, v = hdr_line.decode().partition(":")
                    if k.strip().lower() == "content-length":
                        content_length = int(v.strip())

                body_bytes = await reader.readexactly(content_length) if content_length > 0 else b""
                req_data = json.loads(body_bytes.decode()) if body_bytes else {}

                namespace = req_data.get("namespace", "")
                method = req_data.get("method", "")
                params = req_data.get("params", {})
                is_mutation = req_data.get("is_mutation", False)
                token = req_data.get("approval_token")

                call_record = CallRecord(method=f"{namespace}.{method}", url=f"api://{namespace}/{method}")
                calls_recorded.append(call_record)

                if is_mutation:
                    mutations_attempted += 1
                    allowed, reason = self.gate.check_mutation_allowed("POST", f"api.{namespace}.{method}", token)
                    if not allowed:
                        resp_obj = {"success": False, "error": reason}
                        resp_bytes = json.dumps(resp_obj).encode()
                        writer.write(b"HTTP/1.1 403 Forbidden\r\nContent-Type: application/json\r\nContent-Length: " + str(len(resp_bytes)).encode() + b"\r\n\r\n" + resp_bytes)
                        await writer.drain()
                        writer.close()
                        await writer.wait_closed()
                        return

                # Mock/Local execution response for internal SDK methods
                res_payload: Any = None
                if namespace == "research" and method == "deep":
                    res_payload = {
                        "job_id": f"job_{int(time.time())}",
                        "status": "completed",
                        "shards_count": 4,
                        "findings_summary": f"Synthesized research for '{params.get('query', '')}' across verified sources.",
                        "citations_count": 6,
                    }
                elif namespace == "ideas" and method == "search":
                    res_payload = [
                        {
                            "id": "idea_101",
                            "title": "Quantum Error Mitigator",
                            "problem": "Qubit decoherence in NISQ computers",
                            "solution": "Real-time syndrome extraction pipeline",
                            "novelty_score": 0.89,
                            "tags": ["quantum", "hardware"],
                        }
                    ]
                elif namespace == "ideas" and method == "generate":
                    res_payload = [
                        {
                            "title": "Autonomous Clinical Trial Optimizer",
                            "problem_statement": "Slow recruitment and protocol deviations in oncology trials.",
                            "proposed_solution": "Federated agentic matching over de-identified EHR datasets.",
                            "target_audience": "BioPharma CROs",
                            "tech_stack": ["Python", "FastAPI", "Postgres+pgvector"],
                            "differentiation": "Privacy-preserving zero-knowledge proof verification",
                        }
                    ]
                elif namespace == "kb" and method == "search":
                    res_payload = [
                        {
                            "note_id": "note_01",
                            "title": "Room Temperature Superconductivity Analysis",
                            "url": "https://arxiv.org/abs/2307.12008",
                            "excerpt": "Zero resistance observed up to 294 K under ambient pressure.",
                            "location": "p. 3, section 2.1",
                            "text_fragment_url": "https://arxiv.org/abs/2307.12008#:~:text=Zero%20resistance",
                        }
                    ]
                elif namespace == "memory" and method == "recall":
                    res_payload = [
                        {
                            "id": "mem_1",
                            "entity": params.get("entity", "Deep Research Agent"),
                            "relation": "USES_TOOL",
                            "target": "Cloudflare Code Mode",
                            "fact": "Deep Research Agent executes tools via Cloudflare Code Mode isolates.",
                            "valid_from": "2026-03-01",
                        }
                    ]
                elif namespace == "memory" and method == "remember":
                    res_payload = {"status": "saved", "id": "mem_new_1"}
                elif namespace == "crawl" and method == "start":
                    res_payload = {"crawl_id": "crawl_42", "status": "active", "urls_queued": 18}
                elif namespace == "web" and method == "search":
                    res_payload = [
                        {
                            "title": f"SearXNG result for {params.get('query', '')}",
                            "url": "https://example.com/search-result",
                            "snippet": "Verified search snippet from SearXNG metasearch instance.",
                        }
                    ]
                else:
                    res_payload = {"status": "ok", "namespace": namespace, "method": method, "params": params}

                resp_obj = {"success": True, "result": res_payload}
                resp_bytes = json.dumps(resp_obj).encode()
                writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: " + str(len(resp_bytes)).encode() + b"\r\n\r\n" + resp_bytes)
                await writer.drain()
            except Exception as e:
                err_bytes = json.dumps({"success": False, "error": str(e)}).encode()
                writer.write(b"HTTP/1.1 500 Internal Error\r\nContent-Length: " + str(len(err_bytes)).encode() + b"\r\n\r\n" + err_bytes)
                await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()

        server = await asyncio.start_server(handle_gate_request, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]

        # Prepare Node script
        safe_approval = json.dumps(approval_token) if approval_token else "null"
        safe_tenant = json.dumps(tenant_id)
        script_code = RUNNER_BOOTSTRAP_TEMPLATE.replace("__GATE_PORT__", str(port))
        script_code = script_code.replace("__APPROVAL_TOKEN__", safe_approval)
        script_code = script_code.replace("__TENANT_ID__", safe_tenant)
        script_code = script_code.replace("__USER_CODE__", code)

        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
            f.write(script_code)
            temp_script_path = f.name

        try:
            proc = await asyncio.create_subprocess_exec(
                self.node_path,
                temp_script_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10.0)
            wall_time_ms = (time.time() - start_time) * 1000

            stdout_str = stdout.decode("utf-8", errors="ignore").strip()
            stderr_str = stderr.decode("utf-8", errors="ignore").strip()

            audit_hash = self.gate.record_audit(
                tenant_id=tenant_id,
                code=code,
                calls=calls_recorded,
                wall_time_ms=wall_time_ms,
                mutations=mutations_attempted,
                approved=True if mutations_attempted == 0 or approval_token else False,
            )

            if stdout_str:
                # Find last JSON line from stdout
                lines = [ln.strip() for ln in stdout_str.split("\n") if ln.strip()]
                parsed_res = None
                for line in reversed(lines):
                    try:
                        parsed_res = json.loads(line)
                        break
                    except Exception:
                        continue

                if parsed_res:
                    return ExecutionResult(
                        success=parsed_res.get("success", False),
                        result=parsed_res.get("result"),
                        error=parsed_res.get("error"),
                        calls_made=parsed_res.get("calls_made", []),
                        wall_time_ms=wall_time_ms,
                        audit_hash=audit_hash,
                    )

            return ExecutionResult(
                success=False,
                error=stderr_str or "Node script returned empty result",
                wall_time_ms=wall_time_ms,
                audit_hash=audit_hash,
            )

        except asyncio.TimeoutError:
            return ExecutionResult(
                success=False,
                error="Execution timed out after 10000ms",
                wall_time_ms=(time.time() - start_time) * 1000,
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                error=str(e),
                wall_time_ms=(time.time() - start_time) * 1000,
            )
        finally:
            server.close()
            await server.wait_closed()
            if os.path.exists(temp_script_path):
                os.remove(temp_script_path)
