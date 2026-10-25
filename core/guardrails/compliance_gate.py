from __future__ import annotations

import os
import re
import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ComplianceViolation(BaseModel):
    rule_id: str
    description: str
    severity: str  # "low", "medium", "high"
    matched_text: str
    action: str  # "flag", "rewrite", "block"


class ComplianceGateResult(BaseModel):
    passed: bool
    violations: List[ComplianceViolation] = Field(default_factory=list)
    delivery_blocked: bool = False
    flagged_for_human_review: bool = False
    sanitized_text: str = ""
    rewrite_count: int = 0


class ComplianceGate:
    """
    Evaluates report drafts against global and tenant-specific compliance rules.
    Catches unsubstantiated claims, competitor disparagement, and confidential terminology.
    Enforces rewrite loops and blocks delivery on unresolved high-severity violations.
    """

    def __init__(
        self,
        tenant_id: str,
        config_dir: Optional[str] = None,
    ):
        self.tenant_id = tenant_id
        if config_dir is None:
            base_dir = Path(__file__).resolve().parent.parent.parent
            config_dir = str(base_dir / "config" / "compliance")
        self.config_dir = config_dir
        self.global_rules: List[Dict[str, Any]] = []
        self.tenant_rules: List[Dict[str, Any]] = []
        self._load_rules()

    def _load_rules(self):
        # 1. Global rules
        global_path = os.path.join(self.config_dir, "global_rules.yaml")
        if os.path.exists(global_path):
            with open(global_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                self.global_rules = data.get("rules", [])

        # 2. Tenant rules
        tenant_path = os.path.join(self.config_dir, "tenant_rules.yaml")
        if os.path.exists(tenant_path):
            with open(tenant_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                self.tenant_rules = data.get("tenants", {}).get(self.tenant_id, {}).get("rules", [])

    def evaluate(self, text: str, max_rewrites: int = 1) -> ComplianceGateResult:
        current_text = text
        rewrite_count = 0

        # Run evaluation and attempt up to max_rewrites rewrite loops
        while True:
            violations = self._find_violations(current_text)
            if not violations:
                return ComplianceGateResult(
                    passed=True,
                    violations=[],
                    delivery_blocked=False,
                    sanitized_text=current_text,
                    rewrite_count=rewrite_count,
                )

            # Check if any high-severity violations exist
            has_high = any(v.severity == "high" for v in violations)

            if rewrite_count < max_rewrites:
                # Execute rewrite loop: rewrite/sanitize violations
                current_text = self._apply_rewrites(current_text, violations)
                rewrite_count += 1
                continue

            # If violations remain after rewrite loop:
            delivery_blocked = has_high
            return ComplianceGateResult(
                passed=False,
                violations=violations,
                delivery_blocked=delivery_blocked,
                flagged_for_human_review=True,
                sanitized_text=current_text,
                rewrite_count=rewrite_count,
            )

    def _find_violations(self, text: str) -> List[ComplianceViolation]:
        violations: List[ComplianceViolation] = []
        all_rules = self.global_rules + self.tenant_rules

        for rule in all_rules:
            patterns = rule.get("patterns", [])
            for pat in patterns:
                matches = re.finditer(pat, text)
                for m in matches:
                    violations.append(
                        ComplianceViolation(
                            rule_id=rule.get("id", "rule"),
                            description=rule.get("description", ""),
                            severity=rule.get("severity", "medium"),
                            matched_text=m.group(0),
                            action=rule.get("action", "flag"),
                        )
                    )
        return violations

    def _apply_rewrites(self, text: str, violations: List[ComplianceViolation]) -> str:
        rewritten = text
        for v in violations:
            if v.action in ["rewrite", "flag"]:
                # Replace banned claim with compliant phrasing
                rewritten = rewritten.replace(v.matched_text, "[Compliant verified metric]")
        return rewritten
