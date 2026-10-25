---
name: data_table_analysis
description: Computes exact marketing campaign KPIs (CTR, CPC, CPA, ROAS, conversion rate) from structured CSV data using Python in a sandboxed runtime.
role: analyst
---

# Data Table Analysis Skill

## Objective
Analyze structured tabular data (CSV/Excel) to extract precise quantitative metrics. Never estimate or hallucinate mathematical figures; compute them deterministically.

## Execution Pattern
1. Read the input dataset using `pandas`.
2. Clean column names and convert string metrics (e.g. "$1,200", "4.5%") into floats.
3. Compute derived metrics:
   - **CTR (%)**: `(clicks / impressions) * 100`
   - **CPC ($)**: `spend / clicks`
   - **Conversion Rate (%)**: `(conversions / clicks) * 100`
   - **CPA ($)**: `spend / conversions`
   - **ROAS**: `revenue / spend`
4. Output a summary JSON file named `computed_metrics.json` containing exact rounded statistics.
