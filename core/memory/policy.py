"""
Memory Policy & PII Guard.

Intercepts sensitive credentials, financial numbers, and health data
before they enter the knowledge graph or markdown vault.
"""

import os
import re
from typing import Tuple
import yaml

DEFAULT_BLOCKED_PATTERNS = [
    r"(?i)(?:api[_-]?key|secret|token|bearer|password|passwd|auth[_-]?token)\s*[:=]\s*[A-Za-z0-9_\-\.]{8,}",
    r"(?i)gh[pous]_[A-Za-z0-9_]{36}",
    r"(?i)sk-[A-Za-z0-9]{32,}",
    r"(?i)\b(?:\d[ -]*?){13,16}\b",
    r"(?i)\b\d{3}-\d{2}-\d{4}\b",
    r"(?i)\b(?:diagnosis|prescription|patient ID|medical record|blood pressure|dosage)\b",
]


class MemoryPolicyEnforcer:
    """Enforces privacy, secret-fencing, and data retention rules."""

    def __init__(self, config_path: str = "config/memory_policy.yaml"):
        self.blocked_regexes = []
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    cfg = yaml.safe_load(f)
                    patterns = cfg.get("blocked_patterns", DEFAULT_BLOCKED_PATTERNS)
                    self.blocked_regexes = [re.compile(p) for p in patterns]
            except Exception:
                self.blocked_regexes = [re.compile(p) for p in DEFAULT_BLOCKED_PATTERNS]
        else:
            self.blocked_regexes = [re.compile(p) for p in DEFAULT_BLOCKED_PATTERNS]

    def check_fact(self, text: str) -> Tuple[bool, str]:
        """Check if fact text contains prohibited PII or secrets."""
        for pattern in self.blocked_regexes:
            if pattern.search(text):
                return False, f"Fact contains prohibited sensitive data or credentials matching security policy."
        return True, ""
