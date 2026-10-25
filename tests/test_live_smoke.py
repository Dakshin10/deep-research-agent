from __future__ import annotations

import os
import subprocess
import tempfile
import shutil
import pytest
from core.models.router import ModelRouter
from core.tools.search import TavilySearchProvider, ExaSearchProvider
from core.tools.fetch import PageFetchService
from core.tools.mcp_wrapper import ReadOnlyMCPClient
from core.sandbox.client import DockerSandboxClient, E2BSandboxClient


def is_docker_running() -> bool:
    try:
        res = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        return res.returncode == 0
    except Exception:
        return False


# -------------------------------------------------------------------------
# 1. Groq Model via ModelRouter
# -------------------------------------------------------------------------
@pytest.mark.live
@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.environ.get("GROQ_API_KEY") or os.environ.get("GROQ_API_KEY", "").startswith("your_"),
    reason="GROQ_API_KEY not configured in environment",
)
async def test_live_groq_through_model_router():
    router = ModelRouter(force_mock=False)
    model = router.get_model("classifier")
    response = await model.ainvoke("Classify: What are the best marketing automation platforms for 2025?")
    content = response.content if hasattr(response, "content") else str(response)
    assert len(content) > 0
    assert not content.startswith("Mock response")


# -------------------------------------------------------------------------
# 2. Gemini Model via ModelRouter
# -------------------------------------------------------------------------
@pytest.mark.live
@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.environ.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY", "").startswith("your_"),
    reason="GEMINI_API_KEY not configured in environment",
)
async def test_live_gemini_through_model_router():
    router = ModelRouter(force_mock=False)
    model = router.get_model("planner")
    response = await model.ainvoke("Create a 2-step research plan for competitive benchmarking.")
    content = response.content if hasattr(response, "content") else str(response)
    assert len(content) > 0
    assert not content.startswith("Mock response")


# -------------------------------------------------------------------------
# 3. Tavily Live Search
# -------------------------------------------------------------------------
@pytest.mark.live
@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.environ.get("TAVILY_API_KEY") or os.environ.get("TAVILY_API_KEY", "").startswith("your_"),
    reason="TAVILY_API_KEY not configured in environment",
)
async def test_live_tavily_search():
    provider = TavilySearchProvider()
    results = await provider.asearch("B2B SaaS average conversion rate 2025", max_results=2)
    assert len(results) > 0
    assert results[0].is_fallback is False, "Tavily search returned fallback data despite live test!"
    assert len(results[0].content) > 0


# -------------------------------------------------------------------------
# 4. Exa Live Neural Search
# -------------------------------------------------------------------------
@pytest.mark.live
@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.environ.get("EXA_API_KEY") or os.environ.get("EXA_API_KEY", "").startswith("your_"),
    reason="EXA_API_KEY not configured in environment",
)
async def test_live_exa_search():
    provider = ExaSearchProvider()
    results = await provider.asearch("Marketing analytics benchmarks", max_results=2)
    assert len(results) > 0
    assert results[0].is_fallback is False, "Exa search returned fallback data despite live test!"
    assert len(results[0].content) > 0


# -------------------------------------------------------------------------
# 5. crawl4ai Public Page Fetch
# -------------------------------------------------------------------------
@pytest.mark.live
@pytest.mark.asyncio
async def test_live_crawl4ai_fetch_public_page():
    fetcher = PageFetchService(max_chars=2000)
    markdown = await fetcher.fetch_markdown("https://example.com")
    assert "documentation examples" in markdown or "example" in markdown.lower()
    assert len(markdown) > 0


# -------------------------------------------------------------------------
# 6. analytics-mcp over stdio
# -------------------------------------------------------------------------
@pytest.mark.live
@pytest.mark.asyncio
async def test_live_analytics_mcp_over_stdio():
    client = ReadOnlyMCPClient(tenant_id="tenant_live_test")
    allowed = client.list_allowed_tools("ga4")
    assert "run_report" in allowed

    # Valid read-only call
    res = await client.call_tool(
        server="ga4",
        tool_name="run_report",
        arguments={"metrics": ["sessions"], "dateRanges": [{"startDate": "30daysAgo", "endDate": "today"}]},
    )
    assert res.read_only is True

    # Mutating tool call MUST be blocked
    with pytest.raises(PermissionError, match="Security violation"):
        await client.call_tool(
            server="ga4",
            tool_name="delete_property",
            arguments={"propertyId": "12345"},
        )


# -------------------------------------------------------------------------
# 7. mcp-hubspot over stdio with read-only allow-list
# -------------------------------------------------------------------------
@pytest.mark.live
@pytest.mark.asyncio
async def test_live_hubspot_mcp_read_only_allowlist():
    client = ReadOnlyMCPClient(tenant_id="tenant_live_test")
    allowed = client.list_allowed_tools("hubspot")
    assert "search_companies" in allowed
    assert "create_company" not in allowed

    # Read-only query execution
    res = await client.call_tool(
        server="hubspot",
        tool_name="search_companies",
        arguments={"query": "Acme"},
    )
    assert res.read_only is True
    assert res.tool_name == "search_companies"

    # Mutating operation MUST raise PermissionError
    with pytest.raises(PermissionError, match="Security violation.*NOT allow-listed for read-only access"):
        await client.call_tool(
            server="hubspot",
            tool_name="create_company",
            arguments={"name": "Malicious Corp", "domain": "malicious.com"},
        )

    with pytest.raises(PermissionError):
        await client.call_tool(
            server="hubspot",
            tool_name="delete_deal",
            arguments={"deal_id": "999"},
        )


# -------------------------------------------------------------------------
# 8. E2B Sandbox Execution
# -------------------------------------------------------------------------
@pytest.mark.live
@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.environ.get("E2B_API_KEY") or os.environ.get("E2B_API_KEY", "").startswith("your_"),
    reason="E2B_API_KEY not configured in environment",
)
async def test_live_e2b_sandbox():
    client = E2BSandboxClient()
    code = "x = 42 * 10\nprint(f'Computed Result: {x}')"
    res = await client.aexecute(code=code)
    assert res.exit_code == 0
    assert "420" in res.stdout


# -------------------------------------------------------------------------
# 9. Docker Sandbox with --network none (Assert outbound request fails)
# -------------------------------------------------------------------------
@pytest.mark.live
@pytest.mark.asyncio
@pytest.mark.skipif(not is_docker_running(), reason="Docker daemon is not running")
async def test_live_docker_sandbox_network_none_blocks_outbound():
    """
    Executes Python script in Docker with --network none and asserts that an
    outbound network connection attempt is rejected.
    """
    temp_dir = tempfile.mkdtemp(prefix="docker_live_test_")
    try:
        script_code = """
import urllib.request
try:
    urllib.request.urlopen('https://example.com', timeout=3)
    print('NETWORK_SUCCESS')
except Exception as e:
    print('NETWORK_FAILED: ' + type(e).__name__)
    exit(42)
"""
        with open(os.path.join(temp_dir, "test_net.py"), "w") as f:
            f.write(script_code)

        cmd = [
            "docker", "run", "--rm",
            "--network", "none",
            "-v", f"{temp_dir}:/workspace",
            "-w", "/workspace",
            "python:3.11-slim",
            "python", "test_net.py",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        # Must fail with exit code 42 because outbound network is disabled
        assert proc.returncode == 42
        assert "NETWORK_FAILED" in proc.stdout
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
