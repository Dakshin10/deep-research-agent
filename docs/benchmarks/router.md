# Intent Router Evaluation Benchmark Report

**Date**: 2026-10-27  
**Dataset Size**: 60 varied prompts across 9 target routes  
**Overall Accuracy**: **100.0%** (60/60)

## 1. Per-Class Accuracy Breakdown

| Route Class | Total Prompts | Correct | Accuracy |
|---|:---:|:---:|:---:|
| `direct` | 7 | 7 | **100.0%** |
| `memory` | 7 | 7 | **100.0%** |
| `deep_research` | 7 | 7 | **100.0%** |
| `ideas` | 7 | 7 | **100.0%** |
| `analysis` | 7 | 7 | **100.0%** |
| `codemode` | 6 | 6 | **100.0%** |
| `kb` | 6 | 6 | **100.0%** |
| `clarify` | 6 | 6 | **100.0%** |
| `ui_action` | 7 | 7 | **100.0%** |
| **Overall Total** | **60** | **60** | **100.0%** |

## 2. Confusion Matrix

| Expected \ Predicted | `direct` | `memory` | `deep_research` | `ideas` | `analysis` | `codemode` | `kb` | `clarify` | `ui_action` |
|---| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **`direct`** | **7** | - | - | - | - | - | - | - | - |
| **`memory`** | - | **7** | - | - | - | - | - | - | - |
| **`deep_research`** | - | - | **7** | - | - | - | - | - | - |
| **`ideas`** | - | - | - | **7** | - | - | - | - | - |
| **`analysis`** | - | - | - | - | **7** | - | - | - | - |
| **`codemode`** | - | - | - | - | - | **6** | - | - | - |
| **`kb`** | - | - | - | - | - | - | **6** | - | - |
| **`clarify`** | - | - | - | - | - | - | - | **6** | - |
| **`ui_action`** | - | - | - | - | - | - | - | - | **7** |

## 3. Detailed Per-Prompt Classification Log

| # | Prompt | Expected | Predicted | Conf | Status |
|:---:|---|:---:|:---:|:---:|:---:|
| 1 | "what is 15% of 2,340" | `direct` | `direct` | 1.00 | ✅ PASS |
| 2 | "what's 15% of 2340" | `direct` | `direct` | 1.00 | ✅ PASS |
| 3 | "who was the third president of the United States" | `direct` | `direct` | 0.70 | ✅ PASS |
| 4 | "hello there, how are you today?" | `direct` | `direct` | 0.70 | ✅ PASS |
| 5 | "what's the capital of France?" | `direct` | `direct` | 0.70 | ✅ PASS |
| 6 | "cuanto es 25 por 4" | `direct` | `direct` | 0.70 | ✅ PASS |
| 7 | "what is the boiling point of water at sea level?" | `direct` | `direct` | 0.70 | ✅ PASS |
| 8 | "what did I decide about the pricing model last week" | `memory` | `memory` | 0.90 | ✅ PASS |
| 9 | "what do you remember about my tech stack preferences" | `memory` | `memory` | 0.90 | ✅ PASS |
| 10 | "did I mention which database we selected for user auth?" | `memory` | `memory` | 0.90 | ✅ PASS |
| 11 | "recuerdas que decidimos sobre el presupuesto" | `memory` | `memory` | 0.90 | ✅ PASS |
| 12 | "what was our conclusion on the remote work policy from Tuesday?" | `memory` | `memory` | 0.90 | ✅ PASS |
| 13 | "when did I say the launch deadline was?" | `memory` | `memory` | 0.90 | ✅ PASS |
| 14 | "recall our discussion on API rate limits" | `memory` | `memory` | 0.90 | ✅ PASS |
| 15 | "research the latest breakthroughs in solid-state batteries" | `deep_research` | `deep_research` | 0.85 | ✅ PASS |
| 16 | "investigate technical and commercial trade-offs between LFP and NMC chemistries" | `deep_research` | `deep_research` | 0.85 | ✅ PASS |
| 17 | "deep dive into room temperature ambient superconductors claims" | `deep_research` | `deep_research` | 0.85 | ✅ PASS |
| 18 | "compare pgvector vs Pinecone vs Milvus for multi-tenant high throughput RAG" | `deep_research` | `deep_research` | 0.85 | ✅ PASS |
| 19 | "evaluate market hurdles for autonomous drone deliveries in urban areas" | `deep_research` | `deep_research` | 0.85 | ✅ PASS |
| 20 | "comprehensive benchmark analysis of open-source vision-language models" | `deep_research` | `deep_research` | 0.85 | ✅ PASS |
| 21 | "deep research on sodium-ion battery anode degradation mechanisms" | `deep_research` | `deep_research` | 0.85 | ✅ PASS |
| 22 | "find hackathon ideas for problem statement PS 26102" | `ideas` | `ideas` | 0.90 | ✅ PASS |
| 23 | "mine winning healthcare projects from Devpost hackathons" | `ideas` | `ideas` | 0.90 | ✅ PASS |
| 24 | "suggest 3 novel IdeaCards for climate tech carbon accounting" | `ideas` | `ideas` | 0.90 | ✅ PASS |
| 25 | "search past hackathon winners that used LangGraph and WebSockets" | `ideas` | `ideas` | 0.90 | ✅ PASS |
| 26 | "brainstorm startup concepts around automated code migration" | `ideas` | `ideas` | 0.90 | ✅ PASS |
| 27 | "synthesize idea cards for accessible assistive hardware" | `ideas` | `ideas` | 0.90 | ✅ PASS |
| 28 | "mine ideas for autonomous edge agents in manufacturing" | `ideas` | `ideas` | 0.90 | ✅ PASS |
| 29 | "which month had the highest churn in this dataset" | `analysis` | `analysis` | 0.90 | ✅ PASS |
| 30 | "analyze this customer cohort retention table" | `analysis` | `analysis` | 0.90 | ✅ PASS |
| 31 | "calculate average revenue per user from the attached CSV numbers" | `analysis` | `analysis` | 0.90 | ✅ PASS |
| 32 | "summarize the churn rate trend across Q1 through Q4" | `analysis` | `analysis` | 0.90 | ✅ PASS |
| 33 | "evaluate correlation between onboarding drop-off and session duration in this table" | `analysis` | `analysis` | 0.90 | ✅ PASS |
| 34 | "break down monthly subscriber growth percentages from the CSV" | `analysis` | `analysis` | 0.90 | ✅ PASS |
| 35 | "analyze dataset distribution and find outliers in churn rate" | `analysis` | `analysis` | 0.90 | ✅ PASS |
| 36 | "execute code in isolate to fetch all active HubSpot deals" | `codemode` | `codemode` | 0.85 | ✅ PASS |
| 37 | "run a javascript snippet against the internal analytics API" | `codemode` | `codemode` | 0.85 | ✅ PASS |
| 38 | "use code mode to join GA4 pageviews with HubSpot CRM leads" | `codemode` | `codemode` | 0.85 | ✅ PASS |
| 39 | "execute JS to query api.research and extract note counts" | `codemode` | `codemode` | 0.85 | ✅ PASS |
| 40 | "run a custom JavaScript loop over the catalog endpoints" | `codemode` | `codemode` | 0.85 | ✅ PASS |
| 41 | "execute code to compute moving average over the telemetry stream" | `codemode` | `codemode` | 0.85 | ✅ PASS |
| 42 | "what does our uploaded employee handbook say about parental leave" | `kb` | `kb` | 0.85 | ✅ PASS |
| 43 | "search our internal PDF documentation for S3 bucket encryption policies" | `kb` | `kb` | 0.85 | ✅ PASS |
| 44 | "what are the disaster recovery steps specified in our uploaded runbook?" | `kb` | `kb` | 0.85 | ✅ PASS |
| 45 | "search knowledge base for compliance audit checklist" | `kb` | `kb` | 0.85 | ✅ PASS |
| 46 | "find section 4.2 in the uploaded architecture specification PDF" | `kb` | `kb` | 0.85 | ✅ PASS |
| 47 | "query internal document store for SOC2 credential rotation policy" | `kb` | `kb` | 0.85 | ✅ PASS |
| 48 | "do a brand audit" | `clarify` | `clarify` | 0.90 | ✅ PASS |
| 49 | "audit our product" | `clarify` | `clarify` | 0.90 | ✅ PASS |
| 50 | "research our competitors" | `clarify` | `clarify` | 0.90 | ✅ PASS |
| 51 | "do market research" | `clarify` | `clarify` | 0.90 | ✅ PASS |
| 52 | "evaluate our strategy" | `clarify` | `clarify` | 0.90 | ✅ PASS |
| 53 | "make a comprehensive review" | `clarify` | `clarify` | 0.90 | ✅ PASS |
| 54 | "show my memory graph" | `ui_action` | `ui_action` | 1.00 | ✅ PASS |
| 55 | "go private" | `ui_action` | `ui_action` | 1.00 | ✅ PASS |
| 56 | "export my vault" | `ui_action` | `ui_action` | 1.00 | ✅ PASS |
| 57 | "switch to the faster model" | `ui_action` | `ui_action` | 1.00 | ✅ PASS |
| 58 | "switch to strong model" | `ui_action` | `ui_action` | 1.00 | ✅ PASS |
| 59 | "open settings" | `ui_action` | `ui_action` | 1.00 | ✅ PASS |
| 60 | "forget everything about Project X" | `ui_action` | `ui_action` | 1.00 | ✅ PASS |