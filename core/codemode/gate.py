"""
Code Mode Gate.

Security gateway running OUTSIDE the sandbox:
- Host allowlist enforcement
- Credential injection (sandbox code never sees raw tokens)
- Execution limits (timeout, call caps, payload truncation)
- Mutation approval gate (modifying operations require valid approval token)
- Audit logging
"""

import hashlib
import json
import logging
import time
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

DEFAULT_ALLOWED_HOSTS = {
    "localhost",
    "127.0.0.1",
    "api.github.com",
    "hacker-news.firebaseio.com",
    "oauth.reddit.com",
    "export.arxiv.org",
    "api.openalex.org",
    "en.wikipedia.org",
    "api.hubspot.com",
    "analyticsdata.googleapis.com",
}

SAFE_READ_METHODS = {"GET", "HEAD", "OPTIONS"}
MAX_CALLS_PER_EXECUTION = 20
MAX_RESPONSE_BYTES = 32768  # 32 KB limit per call


class CallRecord(BaseModel):
    method: str
    url: str
    status_code: int = 200
    timestamp_ms: float = Field(default_factory=lambda: time.time() * 1000)
    duration_ms: float = 0.0
    truncated: bool = False


class AuditLogRecord(BaseModel):
    tenant_id: str
    code_hash: str
    calls: list[CallRecord] = Field(default_factory=list)
    total_calls: int = 0
    wall_time_ms: float = 0.0
    mutations_attempted: int = 0
    approved: bool = True
    created_at: float = Field(default_factory=time.time)


class SecurityGate:
    """Out-of-sandbox security supervisor for Code Mode executions."""

    def __init__(
        self,
        allowed_hosts: set[str] | None = None,
        injected_headers: dict[str, dict[str, str]] | None = None,
    ):
        self.allowed_hosts = allowed_hosts or DEFAULT_ALLOWED_HOSTS
        # Injected headers format: { host: { header_name: secret_val } }
        self.injected_headers = injected_headers or {}
        self.audit_log: list[AuditLogRecord] = []

    def check_url_allowed(self, url: str) -> bool:
        """Validate destination host against the strict allowlist."""
        try:
            parsed = urlparse(url)
            host = parsed.hostname or ""
            return host.lower() in self.allowed_hosts
        except Exception:
            return False

    def check_mutation_allowed(
        self,
        method: str,
        url: str,
        approval_token: str | None = None,
    ) -> tuple[bool, str]:
        """Verify mutating calls have an explicit approval token."""
        upper_method = method.upper()
        if upper_method in SAFE_READ_METHODS:
            return True, ""

        # Modifying method (POST, PUT, DELETE, PATCH)
        if not approval_token:
            return (
                False,
                f"Mutating operation {upper_method} on {url} blocked: requires user approval token.",
            )

        # In production, verify JWT/token signature; for now verify non-empty token
        if len(approval_token) < 8:
            return False, "Invalid or expired approval token."

        return True, ""

    def inject_credentials(self, host: str, headers: dict[str, str]) -> dict[str, str]:
        """Inject secrets into outbound request without exposing to the model."""
        out = dict(headers)
        if host in self.injected_headers:
            for k, v in self.injected_headers[host].items():
                out[k] = v
        return out

    def truncate_payload(self, data: str) -> tuple[str, bool]:
        """Truncate oversized response payloads to protect LLM context."""
        encoded = data.encode("utf-8")
        if len(encoded) > MAX_RESPONSE_BYTES:
            truncated = encoded[:MAX_RESPONSE_BYTES].decode("utf-8", errors="ignore")
            notice = f"\n\n[... Truncated: response exceeded {MAX_RESPONSE_BYTES // 1024} KB limit ...]"
            return truncated + notice, True
        return data, False

    def record_audit(
        self,
        tenant_id: str,
        code: str,
        calls: list[CallRecord],
        wall_time_ms: float,
        mutations: int,
        approved: bool,
    ) -> str:
        """Create cryptographic audit record of the execution."""
        code_hash = hashlib.sha256(code.encode("utf-8")).hexdigest()
        record = AuditLogRecord(
            tenant_id=tenant_id,
            code_hash=code_hash,
            calls=calls,
            total_calls=len(calls),
            wall_time_ms=wall_time_ms,
            mutations_attempted=mutations,
            approved=approved,
        )
        self.audit_log.append(record)
        return code_hash
