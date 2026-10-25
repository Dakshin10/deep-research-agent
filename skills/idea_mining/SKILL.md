---
name: idea_mining
description: Crawls, extracts, clusters, and analyzes startup launches, hackathon projects, and winning entries with verified evidence and originality scoring.
role: researcher
domain: idea_mining
---

# Idea Mining Skill

## Objective
Extract structured `IdeaRecord` entries from hackathon showcases, startup directories, and launch posts. Every factual attribute (problem, solution, tech stack, team size, prize/placement, traction) must be backed by an exact location excerpt verified against the source text.

## Verification Hard Rules
1. Never guess or fabricate prizes, rankings, or placements. If not explicitly verified in the text, placement must be set to `none`.
2. Do not store personal identifying information (PII) such as emails, phone numbers, or private handles.
3. Every quantitative claim (revenue, user count, upvotes) must cite the exact char offset or section heading.
