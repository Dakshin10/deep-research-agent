from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class MockLLMResponse:
    def __init__(self, content: str):
        self.content = content

    def __str__(self):
        return self.content


class MockLLM:
    """
    Deterministic mock LLM for testing without network dependencies.
    Lives strictly under tests/ per system architecture requirements.
    """

    def __init__(self, role: str, config: Any = None):
        self.role = role
        self.config = config

    def invoke(self, messages: Any, **kwargs) -> MockLLMResponse:
        return MockLLMResponse(content=self._get_mock_content(messages))

    async def ainvoke(self, messages: Any, **kwargs) -> MockLLMResponse:
        return MockLLMResponse(content=self._get_mock_content(messages))

    def _get_mock_content(self, messages: Any) -> str:
        prompt_text = str(messages)
        if self.role == "classifier":
            user_query = prompt_text.split("User Query:")[-1].lower() if "User Query:" in prompt_text else prompt_text.lower()
            if any(w in user_query for w in ["hello", "how are you", "who are you", "hi "]):
                return '{"mode": "chit_chat", "confidence": 1.0, "reply": "Hello! I am your Deep Research AI assistant."}'
            elif any(w in user_query for w in ["clarify", "ambiguous", "missing"]):
                return '{"mode": "clarify", "confidence": 0.9}'
            elif any(w in user_query for w in ["competitor", "landscape", "audit", "deep", "campaign"]):
                return '{"mode": "deep", "confidence": 0.95}'
            return '{"mode": "shallow", "confidence": 0.85}'

        elif self.role == "planner":
            comps = []
            for c in ["hubspot", "salesforce", "zoho", "marketo", "activecampaign", "klaviyo"]:
                if c in prompt_text.lower():
                    comps.append(c.capitalize())
            if not comps:
                comps = ["Primary Entity", "Secondary Rival"]

            tasks = [
                {
                    "task_id": "task_market_overview",
                    "objective": "Identify market positioning and core industry benchmarks",
                    "entity": "Industry Landscape",
                    "source_hints": ["tavily", "kb_retrieve"],
                    "expected_output": "notes",
                    "depends_on": [],
                }
            ]
            for comp in comps:
                tasks.append(
                    {
                        "task_id": f"task_{comp.lower()}",
                        "objective": f"Analyze {comp} pricing, packaging tiers, and target market segment",
                        "entity": comp,
                        "source_hints": ["tavily", "crawl4ai"],
                        "expected_output": "notes+table",
                        "depends_on": ["task_market_overview"],
                    }
                )
            tasks.append(
                {
                    "task_id": "task_comparative_synthesis",
                    "objective": "Synthesize competitor feature matrix and pricing differentials",
                    "entity": "Competitive Matrix",
                    "source_hints": ["tavily", "kb_retrieve"],
                    "expected_output": "notes+chart",
                    "depends_on": [f"task_{comp.lower()}" for comp in comps],
                }
            )
            return json.dumps({"tasks": tasks})

        elif self.role == "clarifier":
            return """{
              "missing_fields": ["audience", "geography"],
              "questions": [
                "Who is your target audience?",
                "Which geographic regions should this analysis focus on?"
              ]
            }"""

        elif self.role == "verifier":
            return '{"needs_more_research": false, "extra_tasks": []}'

        elif self.role == "writer":
            return """# Executive Research Report

## Market Landscape & Overview
According to recent industry data [note_1], the market expanded significantly over the past fiscal year. 

## Competitive Analysis
Competitor solutions showed strong feature parity [note_2]. Key metrics demonstrated steady customer adoption.
"""

        elif self.role == "shallow":
            # Extract note IDs from prompt if available
            import re
            note_ids = re.findall(r"\[(note_[a-zA-Z0-9_]+)\]", prompt_text)
            n1 = note_ids[0] if note_ids else "note_s1"
            n2 = note_ids[1] if len(note_ids) > 1 else n1
            return (
                f"Based on verified research findings [{n1}], the target entity launched its flagship offering with robust market reception. "
                f"Furthermore, recent performance data indicates sustained traction across target customer segments [{n2}]."
            )

        return "Mock response for " + self.role
