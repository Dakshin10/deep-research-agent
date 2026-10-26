"""
Unit and security tests for Code Mode Security Gate.
"""

import pytest
from core.codemode.gate import CallRecord, SecurityGate, MAX_RESPONSE_BYTES


def test_host_allowlist_allowed_hosts():
    gate = SecurityGate(allowed_hosts={"api.github.com", "localhost", "127.0.0.1"})

    assert gate.check_url_allowed("https://api.github.com/repos/test") is True
    assert gate.check_url_allowed("http://localhost:8000/api") is True
    assert gate.check_url_allowed("http://127.0.0.1:8080/v1") is True


def test_host_allowlist_blocks_unauthorized_hosts_and_ssrf():
    gate = SecurityGate(allowed_hosts={"api.github.com", "localhost"})

    # Unauthorized public hosts
    assert gate.check_url_allowed("https://malicious-site.com/steal") is False
    assert gate.check_url_allowed("https://evil.com/webhook") is False

    # SSRF / Cloud metadata endpoint
    assert gate.check_url_allowed("http://169.254.169.254/latest/meta-data/") is False
    assert gate.check_url_allowed("http://10.0.0.1/admin") is False
    assert gate.check_url_allowed("file:///etc/passwd") is False


def test_credential_injection_masks_secrets():
    gate = SecurityGate(
        injected_headers={
            "api.github.com": {"Authorization": "token secret_gh_pat_12345"},
            "api.hubspot.com": {"X-HubSpot-Key": "secret_hs_token_999"},
        }
    )

    client_headers = {"User-Agent": "DeepResearchAgent"}
    injected = gate.inject_credentials("api.github.com", client_headers)

    assert injected["Authorization"] == "token secret_gh_pat_12345"
    assert injected["User-Agent"] == "DeepResearchAgent"
    # Ensure original dict was not mutated
    assert "Authorization" not in client_headers


def test_mutation_approval_gate():
    gate = SecurityGate()

    # Read methods (GET) are always permitted
    allowed_get, _ = gate.check_mutation_allowed("GET", "https://api.github.com/repos")
    assert allowed_get is True

    # Mutating methods (POST/DELETE) without token are blocked
    allowed_post, reason = gate.check_mutation_allowed("POST", "https://api.github.com/repos/create")
    assert allowed_post is False
    assert "blocked: requires user approval token" in reason

    # With invalid/short token: blocked
    allowed_bad_token, reason = gate.check_mutation_allowed(
        "POST", "https://api.github.com/repos/create", approval_token="short"
    )
    assert allowed_bad_token is False

    # With valid token: permitted
    allowed_valid, _ = gate.check_mutation_allowed(
        "POST", "https://api.github.com/repos/create", approval_token="appr_token_valid_998877"
    )
    assert allowed_valid is True


def test_payload_truncation():
    gate = SecurityGate()

    # Small response passes unmodified
    small_data = "Hello, world!"
    res, truncated = gate.truncate_payload(small_data)
    assert res == small_data
    assert truncated is False

    # Oversized response (> 32 KB) is cleanly truncated
    oversized_data = "X" * (MAX_RESPONSE_BYTES + 5000)
    res, truncated = gate.truncate_payload(oversized_data)
    assert truncated is True
    assert len(res) < len(oversized_data)
    assert "Truncated: response exceeded" in res


def test_audit_logging():
    gate = SecurityGate()
    calls = [
        CallRecord(method="api.research.deep", url="api://research/deep", status_code=200),
        CallRecord(method="api.web.search", url="https://searxng.internal/search", status_code=200),
    ]

    code = "const r = await api.research.deep({ query: 'quantum' }); return r;"
    audit_hash = gate.record_audit(
        tenant_id="tenant_alpha",
        code=code,
        calls=calls,
        wall_time_ms=142.5,
        mutations=0,
        approved=True,
    )

    assert len(audit_hash) == 64  # SHA-256
    assert len(gate.audit_log) == 1
    log = gate.audit_log[0]
    assert log.tenant_id == "tenant_alpha"
    assert log.total_calls == 2
    assert log.approved is True
