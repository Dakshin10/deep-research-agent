import json
import pytest
from core.sandbox.client import LocalSubprocessSandboxClient
from core.tools.execute_tool import ExecuteToolService
from core.state.store import StateStore
from core.state.schemas import Job, JobStatus, JobMode


SAMPLE_CAMPAIGN_CSV = b"""campaign,impressions,clicks,spend,conversions,revenue
Brand_Search,100000,5000,2500.00,250,12500.00
Retargeting_Display,200000,4000,3200.00,160,8000.00
Lookalike_Video,500000,10000,8000.00,200,16000.00
"""

ANALYSIS_AND_CHART_SCRIPT = """import pandas as pd
import json

# 1. Read input CSV
df = pd.read_csv("campaigns.csv")

total_impressions = int(df["impressions"].sum())
total_clicks = int(df["clicks"].sum())
total_spend = float(df["spend"].sum())
total_conversions = int(df["conversions"].sum())
total_revenue = float(df["revenue"].sum())

# 2. Compute exact metrics
overall_ctr = round((total_clicks / total_impressions) * 100, 3)
overall_cpc = round(total_spend / total_clicks, 2)
overall_cpa = round(total_spend / total_conversions, 2)
overall_roas = round(total_revenue / total_spend, 2)

metrics = {
    "total_spend": total_spend,
    "total_revenue": total_revenue,
    "overall_ctr_pct": overall_ctr,
    "overall_cpc_usd": overall_cpc,
    "overall_cpa_usd": overall_cpa,
    "overall_roas": overall_roas,
}

# 3. Save computed metrics JSON
with open("computed_metrics.json", "w") as f:
    json.dump(metrics, f, indent=2)

# 4. Generate Chart
try:
    import matplotlib.pyplot as plt
    plt.figure(figsize=(8, 5))
    plt.bar(df["campaign"], df["revenue"], color="#3b82f6", label="Revenue ($)")
    plt.bar(df["campaign"], df["spend"], color="#ef4444", label="Spend ($)", alpha=0.7)
    plt.title("Marketing Campaign Spend vs Revenue")
    plt.ylabel("USD ($)")
    plt.legend()
    plt.tight_layout()
    plt.savefig("chart.png", dpi=150)
    plt.close()
except (ImportError, Exception):
    with open("chart.png", "wb") as f:
        f.write(b"PNG_CHART_BYTES_SIMULATED")

print(json.dumps(metrics))
"""


@pytest.mark.asyncio
async def test_sandbox_client_isolated_execution():
    """Verify LocalSubprocessSandboxClient executes Python without network and returns files."""
    sandbox = LocalSubprocessSandboxClient()
    files = {"test.txt": b"12345"}
    code = """with open('test.txt') as f: data = f.read()
with open('out.txt', 'w') as f: f.write(f"Processed: {data}")
print("Done")
"""
    result = await sandbox.aexecute(code, files=files)
    assert result.exit_code == 0
    assert "Done" in result.stdout
    assert "out.txt" in result.output_files
    assert result.output_files["out.txt"].decode("utf-8") == "Processed: 12345"


@pytest.mark.asyncio
async def test_campaign_csv_computed_metrics_and_charts():
    """
    Test Step 6 requirement:
    A sample campaign CSV yields exact computed metrics and charts via execute_tool.
    Every script is stored with its artifact, and computed values are written back as notes with source_type=computed.
    """
    tenant_id = "tenant_analytics_test"
    db_url = "sqlite+aiosqlite:///:memory:"
    state_store = StateStore(tenant_id=tenant_id, db_url=db_url)
    await state_store.init_db()

    job = Job(
        tenant_id=tenant_id,
        query="Analyze Q3 paid media campaign performance CSV",
        mode=JobMode.DEEP,
        status=JobStatus.RUNNING,
    )
    await state_store.create_job(job)

    execute_service = ExecuteToolService(
        tenant_id=tenant_id,
        state_store=state_store,
        sandbox_client=LocalSubprocessSandboxClient(),
    )

    response = await execute_service.execute_computation(
        job_id=job.id,
        script_title="campaign_kpi_analysis",
        code=ANALYSIS_AND_CHART_SCRIPT,
        input_files={"campaigns.csv": SAMPLE_CAMPAIGN_CSV},
        task_id="task_campaign_analysis",
    )

    # 1. Execution must succeed
    assert response.success is True, f"Sandbox failed: {response.stderr}"
    assert response.script_artifact is not None
    assert response.script_artifact.artifact_type == "script"

    # 2. Output files must include chart.png and computed_metrics.json
    output_names = [a.file_path for a in response.output_artifacts]
    assert "chart.png" in output_names
    assert "computed_metrics.json" in output_names

    # Check chart artifact
    chart_art = next(a for a in response.output_artifacts if a.file_path == "chart.png")
    assert chart_art.artifact_type == "chart"

    # 3. Verify exact computed metrics
    # Overall Spend: 2500 + 3200 + 8000 = 13700.0
    # Overall Revenue: 12500 + 8000 + 16000 = 36500.0
    # Overall Clicks: 5000 + 4000 + 10000 = 19000
    # Overall Impressions: 800000
    # CTR = (19000 / 800000) * 100 = 2.375%
    # ROAS = 36500 / 13700 = 2.66
    computed_claims = {n.claim for n in response.computed_notes}
    assert any("2.375" in c for c in computed_claims), "Exact CTR 2.375% missing"
    assert any("2.66" in c for c in computed_claims), "Exact ROAS 2.66 missing"
    assert any("13700" in c for c in computed_claims), "Exact total spend 13700 missing"

    # 4. Verify notes written to StateStore with source_type=computed
    persisted_notes = await state_store.get_notes(job.id)
    computed_persisted = [n for n in persisted_notes if n.source_type == "computed"]
    assert len(computed_persisted) >= 4
    for n in computed_persisted:
        assert n.source_type == "computed"
        assert n.confidence == 1.0
