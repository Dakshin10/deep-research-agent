---
name: chart_generation
description: Generates clean, publication-ready visual charts (bar charts, line trends, scatter plots) from analyzed tabular data using matplotlib.
role: analyst
---

# Chart Generation Skill

## Objective
Convert tabular performance and competitor comparison metrics into polished PNG chart artifacts saved in the sandbox execution directory.

## Design Rules
1. Use minimalist, modern styling (`plt.style.use('seaborn-v0_8-whitegrid')` or clean whitegrid).
2. Set high resolution (`dpi=300`).
3. Add clear axis titles, units ($, %, count), and explicit data labels on bars.
4. Save the figure to `chart.png`.
