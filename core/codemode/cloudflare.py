"""
CloudflareBackend for Code Mode.

Connects to Cloudflare Workers Dynamic Worker MCP endpoint:
- search(code): runs catalog search in isolate with no network
- execute(code): runs code in dynamic isolate with typed SDK and supervisor gate
"""

import hashlib
import json
import logging
import time
from typing import Any

import httpx

from core.codemode.backend import CodeModeBackend, ExecutionResult, SearchResult
from core.codemode.generator import DEFAULT_SDK_DECLARATION

logger = logging.getLogger(__name__)


class CloudflareBackend(CodeModeBackend):
    """Production backend connecting to Cloudflare Worker MCP server."""

    def __init__(
        self,
        endpoint_url: str = "http://127.0.0.1:8787/mcp",
        auth_token: str = "cf_tenant_secret_token",
    ):
        self.endpoint_url = endpoint_url
        self.auth_token = auth_token

    async def search(self, query: str, tenant_id: str = "default_tenant") -> SearchResult:
        """Call search tool on the Cloudflare Worker MCP endpoint."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.post(
                    self.endpoint_url,
                    headers={
                        "Authorization": f"Bearer {self.auth_token}",
                        "X-Tenant-ID": tenant_id,
                        "Content-Type": "application/json",
                    },
                    json={
                        "jsonrpc": "2.0",
                        "id": "1",
                        "method": "tools/call",
                        "params": {
                            "name": "search",
                            "arguments": {"code": query},
                        },
                    },
                )
                if resp.status_code == 200:
                    data = resp.json().get("result", {})
                    content = data.get("content", [{}])[0].get("text", "{}")
                    parsed = json.loads(content)
                    return SearchResult(
                        matches=parsed.get("matches", []),
                        types_dts=parsed.get("types_dts", DEFAULT_SDK_DECLARATION),
                        total_matches=len(parsed.get("matches", [])),
                    )
            except Exception as e:
                logger.warning(f"Cloudflare search MCP call failed, falling back: {e}")

        return SearchResult(
            matches=[],
            types_dts=DEFAULT_SDK_DECLARATION,
            total_matches=0,
        )

    async def execute(
        self,
        code: str,
        tenant_id: str = "default_tenant",
        approval_token: str | None = None,
    ) -> ExecutionResult:
        """Call execute tool on Cloudflare Worker MCP endpoint."""
        start_time = time.time()
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                headers = {
                    "Authorization": f"Bearer {self.auth_token}",
                    "X-Tenant-ID": tenant_id,
                    "Content-Type": "application/json",
                }
                if approval_token:
                    headers["X-Approval-Token"] = approval_token

                resp = await client.post(
                    self.endpoint_url,
                    headers=headers,
                    json={
                        "jsonrpc": "2.0",
                        "id": "2",
                        "method": "tools/call",
                        "params": {
                            "name": "execute",
                            "arguments": {
                                "code": code,
                                "approval_token": approval_token,
                            },
                        },
                    },
                )
                wall_time = (time.time() - start_time) * 1000
                if resp.status_code == 200:
                    data = resp.json().get("result", {})
                    content = data.get("content", [{}])[0].get("text", "{}")
                    parsed = json.loads(content)
                    return ExecutionResult(
                        success=parsed.get("success", False),
                        result=parsed.get("result"),
                        error=parsed.get("error"),
                        calls_made=parsed.get("calls_made", []),
                        wall_time_ms=wall_time,
                        audit_hash=parsed.get("audit_hash", ""),
                    )
                else:
                    return ExecutionResult(
                        success=False,
                        error=f"Cloudflare Worker HTTP {resp.status_code}: {resp.text}",
                        wall_time_ms=wall_time,
                    )
            except Exception as e:
                return ExecutionResult(
                    success=False,
                    error=f"Cloudflare Worker connection failed: {e}",
                    wall_time_ms=(time.time() - start_time) * 1000,
                )
