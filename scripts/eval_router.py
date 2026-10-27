#!/usr/bin/env python3
"""
Evaluation suite for IntentClassifier across 60 varied prompts.
Measures per-class accuracy and outputs a full confusion matrix to docs/benchmarks/router.md.
"""
from __future__ import annotations

import os
import sys
from collections import defaultdict
from pathlib import Path

# Ensure project root is in sys.path
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))

from core.chat.classifier import IntentClassifier

EVAL_DATASET = [
    # 1. direct (7)
    {"prompt": "what is 15% of 2,340", "expected": "direct"},
    {"prompt": "what's 15% of 2340", "expected": "direct"},
    {"prompt": "who was the third president of the United States", "expected": "direct"},
    {"prompt": "hello there, how are you today?", "expected": "direct"},
    {"prompt": "what's the capital of France?", "expected": "direct"},
    {"prompt": "cuanto es 25 por 4", "expected": "direct"},
    {"prompt": "what is the boiling point of water at sea level?", "expected": "direct"},

    # 2. memory (7)
    {"prompt": "what did I decide about the pricing model last week", "expected": "memory"},
    {"prompt": "what do you remember about my tech stack preferences", "expected": "memory"},
    {"prompt": "did I mention which database we selected for user auth?", "expected": "memory"},
    {"prompt": "recuerdas que decidimos sobre el presupuesto", "expected": "memory"},
    {"prompt": "what was our conclusion on the remote work policy from Tuesday?", "expected": "memory"},
    {"prompt": "when did I say the launch deadline was?", "expected": "memory"},
    {"prompt": "recall our discussion on API rate limits", "expected": "memory"},

    # 3. deep_research (7)
    {"prompt": "research the latest breakthroughs in solid-state batteries", "expected": "deep_research"},
    {"prompt": "investigate technical and commercial trade-offs between LFP and NMC chemistries", "expected": "deep_research"},
    {"prompt": "deep dive into room temperature ambient superconductors claims", "expected": "deep_research"},
    {"prompt": "compare pgvector vs Pinecone vs Milvus for multi-tenant high throughput RAG", "expected": "deep_research"},
    {"prompt": "evaluate market hurdles for autonomous drone deliveries in urban areas", "expected": "deep_research"},
    {"prompt": "comprehensive benchmark analysis of open-source vision-language models", "expected": "deep_research"},
    {"prompt": "deep research on sodium-ion battery anode degradation mechanisms", "expected": "deep_research"},

    # 4. ideas (7)
    {"prompt": "find hackathon ideas for problem statement PS 26102", "expected": "ideas"},
    {"prompt": "mine winning healthcare projects from Devpost hackathons", "expected": "ideas"},
    {"prompt": "suggest 3 novel IdeaCards for climate tech carbon accounting", "expected": "ideas"},
    {"prompt": "search past hackathon winners that used LangGraph and WebSockets", "expected": "ideas"},
    {"prompt": "brainstorm startup concepts around automated code migration", "expected": "ideas"},
    {"prompt": "synthesize idea cards for accessible assistive hardware", "expected": "ideas"},
    {"prompt": "mine ideas for autonomous edge agents in manufacturing", "expected": "ideas"},

    # 5. analysis (7)
    {"prompt": "which month had the highest churn in this dataset", "expected": "analysis"},
    {"prompt": "analyze this customer cohort retention table", "expected": "analysis"},
    {"prompt": "calculate average revenue per user from the attached CSV numbers", "expected": "analysis"},
    {"prompt": "summarize the churn rate trend across Q1 through Q4", "expected": "analysis"},
    {"prompt": "evaluate correlation between onboarding drop-off and session duration in this table", "expected": "analysis"},
    {"prompt": "break down monthly subscriber growth percentages from the CSV", "expected": "analysis"},
    {"prompt": "analyze dataset distribution and find outliers in churn rate", "expected": "analysis"},

    # 6. codemode (6)
    {"prompt": "execute code in isolate to fetch all active HubSpot deals", "expected": "codemode"},
    {"prompt": "run a javascript snippet against the internal analytics API", "expected": "codemode"},
    {"prompt": "use code mode to join GA4 pageviews with HubSpot CRM leads", "expected": "codemode"},
    {"prompt": "execute JS to query api.research and extract note counts", "expected": "codemode"},
    {"prompt": "run a custom JavaScript loop over the catalog endpoints", "expected": "codemode"},
    {"prompt": "execute code to compute moving average over the telemetry stream", "expected": "codemode"},

    # 7. kb (6)
    {"prompt": "what does our uploaded employee handbook say about parental leave", "expected": "kb"},
    {"prompt": "search our internal PDF documentation for S3 bucket encryption policies", "expected": "kb"},
    {"prompt": "what are the disaster recovery steps specified in our uploaded runbook?", "expected": "kb"},
    {"prompt": "search knowledge base for compliance audit checklist", "expected": "kb"},
    {"prompt": "find section 4.2 in the uploaded architecture specification PDF", "expected": "kb"},
    {"prompt": "query internal document store for SOC2 credential rotation policy", "expected": "kb"},

    # 8. clarify (6)
    {"prompt": "do a brand audit", "expected": "clarify"},
    {"prompt": "audit our product", "expected": "clarify"},
    {"prompt": "research our competitors", "expected": "clarify"},
    {"prompt": "do market research", "expected": "clarify"},
    {"prompt": "evaluate our strategy", "expected": "clarify"},
    {"prompt": "make a comprehensive review", "expected": "clarify"},

    # 9. ui_action (7)
    {"prompt": "show my memory graph", "expected": "ui_action"},
    {"prompt": "go private", "expected": "ui_action"},
    {"prompt": "export my vault", "expected": "ui_action"},
    {"prompt": "switch to the faster model", "expected": "ui_action"},
    {"prompt": "switch to strong model", "expected": "ui_action"},
    {"prompt": "open settings", "expected": "ui_action"},
    {"prompt": "forget everything about Project X", "expected": "ui_action"},
]


def run_benchmark():
    classifier = IntentClassifier()
    classes = ["direct", "memory", "deep_research", "ideas", "analysis", "codemode", "kb", "clarify", "ui_action"]

    confusion_matrix = defaultdict(lambda: defaultdict(int))
    class_totals = defaultdict(int)
    class_correct = defaultdict(int)

    results = []

    for item in EVAL_DATASET:
        prompt = item["prompt"]
        expected = item["expected"]
        class_totals[expected] += 1

        route, conf, meta = classifier.classify(prompt)
        confusion_matrix[expected][route] += 1

        is_match = (route == expected)
        if is_match:
            class_correct[expected] += 1

        results.append({
            "prompt": prompt,
            "expected": expected,
            "predicted": route,
            "confidence": conf,
            "match": is_match,
        })

    total_prompts = len(EVAL_DATASET)
    total_correct = sum(class_correct.values())
    overall_accuracy = (total_correct / total_prompts) * 100.0

    print(f"\n=======================================================")
    print(f" ROUTER EVALUATION BENCHMARK: {total_correct}/{total_prompts} ({overall_accuracy:.1f}%)")
    print(f"=======================================================\n")

    markdown = []
    markdown.append("# Intent Router Evaluation Benchmark Report\n")
    markdown.append(f"**Date**: 2026-10-27  ")
    markdown.append(f"**Dataset Size**: {total_prompts} varied prompts across 9 target routes  ")
    markdown.append(f"**Overall Accuracy**: **{overall_accuracy:.1f}%** ({total_correct}/{total_prompts})\n")

    markdown.append("## 1. Per-Class Accuracy Breakdown\n")
    markdown.append("| Route Class | Total Prompts | Correct | Accuracy |")
    markdown.append("|---|:---:|:---:|:---:|")

    for c in classes:
        tot = class_totals[c]
        cor = class_correct[c]
        acc = (cor / tot * 100.0) if tot > 0 else 0.0
        markdown.append(f"| `{c}` | {tot} | {cor} | **{acc:.1f}%** |")
        print(f"Class '{c}': {cor}/{tot} ({acc:.1f}%)")

    markdown.append(f"| **Overall Total** | **{total_prompts}** | **{total_correct}** | **{overall_accuracy:.1f}%** |\n")

    markdown.append("## 2. Confusion Matrix\n")
    header = "| Expected \\ Predicted | " + " | ".join([f"`{c}`" for c in classes]) + " |"
    sep = "|---| " + " | ".join([":---:" for _ in classes]) + " |"
    markdown.append(header)
    markdown.append(sep)

    for exp in classes:
        row = [f"**`{exp}`**"]
        for pred in classes:
            cnt = confusion_matrix[exp][pred]
            cell = str(cnt) if cnt > 0 else "-"
            if exp == pred and cnt > 0:
                cell = f"**{cell}**"
            row.append(cell)
        markdown.append("| " + " | ".join(row) + " |")

    markdown.append("\n## 3. Detailed Per-Prompt Classification Log\n")
    markdown.append("| # | Prompt | Expected | Predicted | Conf | Status |")
    markdown.append("|:---:|---|:---:|:---:|:---:|:---:|")

    for i, r in enumerate(results, 1):
        status = "✅ PASS" if r["match"] else "❌ FAIL"
        markdown.append(f"| {i} | \"{r['prompt']}\" | `{r['expected']}` | `{r['predicted']}` | {r['confidence']:.2f} | {status} |")

    out_path = root_dir / "docs" / "benchmarks" / "router.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(markdown), encoding="utf-8")
    print(f"\nReport written to: {out_path}\n")


if __name__ == "__main__":
    run_benchmark()
