---
name: idea-analysis
description: Sandboxed statistical analysis engine for startup and hackathon project ideas. Provides HDBSCAN/KMeans semantic clustering, category win rates, winner feature patterns, and whitespace gap detection.
---

# Idea Analysis Engine Skill

This skill provides data-driven statistical analysis over extracted `IdeaRecord`s.

## Capabilities

1. **Clustering (`clustering.py`)**:
   - Groups project embeddings into semantic clusters via KMeans/cosine distance.
   - Computes centroids, identifies closest representative projects, and labels top domain/tech tags.
   - Always reports cluster size and overall sample size `N`.

2. **Trends & Saturation (`trends.py`)**:
   - Tracks project volumes and empirical win rates across domains, tech stacks, and years.
   - Automatically segments categories into:
     - **Saturated**: High entry volume, below-median win rate.
     - **Underexplored**: Lower competition, above-median win rate.
   - States sample size `N` on all outputs.

3. **Winner Patterns (`winner_patterns.py`)**:
   - Compares winners (winners, runner-ups, track prizes) against non-winners on verifiable attributes:
     - Demo URL presence
     - Video pitch presence
     - Mean team size
     - Problem description length / specificity
   - **Critical Constraint**: Always uses statistically defensible language, reports sample sizes, and includes explicit caution notes that correlation does not imply causation.

4. **Whitespace Gap Detection (`whitespace.py`)**:
   - Given a target problem statement or hackathon track brief, computes distance across the embedding space.
   - Identifies nearest existing projects with verified locations to avoid re-inventing the wheel.
   - Pinpoints unbuilt combinations of (Domain x Tech Stack) with 0 or minimal prior art.
   - Calculates a `novelty_score = 1.0 - max_similarity`.

5. **Unified Reporting (`engine.py`)**:
   - `IdeaAnalysisEngine.generate_full_analysis()` outputs markdown summaries and optional matplotlib chart visualizations.
