"""
CodeModeBackend protocol.

Defines the interface for Code Mode execution environments:
- CloudflareBackend: production execution using Cloudflare Workers Dynamic Worker isolates
- LocalBackend: local sandboxed runner using subprocess Node.js with network isolation and HTTP gate
"""

from typing import Any, Protocol, runtime_checkable
from pydantic import BaseModel, Field


class SearchResult(BaseModel):
    """Result of searching the API catalog."""
    matches: list[dict[str, Any]] = Field(default_factory=list)
    types_dts: str = ""
    total_matches: int = 0


class ExecutionResult(BaseModel):
    """Result of executing JavaScript code in the isolate."""
    success: bool
    result: Any = None
    error: str | None = None
    calls_made: list[dict[str, Any]] = Field(default_factory=list)
    wall_time_ms: float = 0.0
    cpu_time_ms: float = 0.0
    truncated: bool = False
    audit_hash: str = ""


@runtime_checkable
class CodeModeBackend(Protocol):
    """Interface for Code Mode execution backend."""

    async def search(self, query: str, tenant_id: str = "default_tenant") -> SearchResult:
        """Search the API catalog and types for matching operations."""
        ...

    async def execute(
        self,
        code: str,
        tenant_id: str = "default_tenant",
        approval_token: str | None = None,
    ) -> ExecutionResult:
        """Execute sandboxed JavaScript against the bound API SDK."""
        ...
