"""
Code Mode Repair Loop.

Interprets JavaScript runtime and syntax errors, constructs concise
feedback prompts, and supports self-healing execution attempts.
"""

from typing import Any
from core.codemode.backend import CodeModeBackend, ExecutionResult


class CodeRepairLoop:
    """Self-healing loop for Code Mode script execution."""

    def __init__(self, backend: CodeModeBackend, max_retries: int = 2):
        self.backend = backend
        self.max_retries = max_retries

    async def execute_with_repair(
        self,
        code: str,
        tenant_id: str = "default_tenant",
        approval_token: str | None = None,
        llm_fixer_callback: Any = None,
    ) -> ExecutionResult:
        """Execute code, feeding back errors to the model if it fails."""
        current_code = code

        for attempt in range(self.max_retries + 1):
            result = await self.backend.execute(
                code=current_code,
                tenant_id=tenant_id,
                approval_token=approval_token,
            )

            if result.success or attempt == self.max_retries or not llm_fixer_callback:
                return result

            # Construct targeted repair prompt for model
            error_diagnostic = (
                f"Your JavaScript code failed with error:\n```\n{result.error}\n```\n"
                f"Original code:\n```javascript\n{current_code}\n```\n"
                f"Please fix the syntax or API usage error. Return ONLY the corrected JavaScript block."
            )

            try:
                fixed_code = await llm_fixer_callback(error_diagnostic)
                if fixed_code and fixed_code.strip() != current_code.strip():
                    current_code = fixed_code.strip()
                else:
                    return result
            except Exception:
                return result

        return result
