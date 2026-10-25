from __future__ import annotations

import re


class PromptInjectionDefense:
    """Sanitizes and fences untrusted external data retrieved from web, tools, or documents."""

    # Patterns commonly used in prompt injection attempts
    INJECTION_PATTERNS = [
        r"(?i)ignore\s+(?:all\s+)?previous\s+instructions",
        r"(?i)disregard\s+(?:all\s+)?prior\s+instructions",
        r"(?i)you\s+are\s+now\s+(?:DAN|unrestricted|in\s+developer\s+mode)",
        r"(?i)system\s+prompt\s*:",
        r"(?i)<script[\s\S]*?</script>",
        r"(?i)assistant\s*:",
        r"(?i)new\s+role\s*:",
    ]

    @classmethod
    def sanitize(cls, text: str) -> str:
        if not text:
            return ""

        # Remove zero-width characters and control codes
        cleaned = re.sub(r"[\u200B-\u200D\uFEFF]", "", text)

        # Replace dangerous injection patterns with neutral text
        for pattern in cls.INJECTION_PATTERNS:
            cleaned = re.sub(pattern, "[FILTERED_INSTRUCTION]", cleaned)

        return cleaned.strip()

    @classmethod
    def fence(cls, content: str, source_type: str, source_url_or_id: str = "") -> str:
        sanitized = cls.sanitize(content)
        return (
            f'<untrusted_data source_type="{source_type}" source_ref="{source_url_or_id}">\n'
            f"{sanitized}\n"
            f"</untrusted_data>"
        )
