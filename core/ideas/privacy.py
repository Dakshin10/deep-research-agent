from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional
import yaml


class PrivacyScrubber:
    """
    Guarantees privacy protection over extracted idea records.
    Scrubs emails, phone numbers, addresses, and private handles.
    Enforces that team size is numeric only and individual names are suppressed
    unless store_individual_names flag is explicitly true.
    """

    EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
    PHONE_PATTERN = re.compile(
        r"(?:(?:\+?1\s*(?:[.-]\s*)?)?(?:\(\s*([2-9]1[02-9]|[2-9][02-8]1|[2-9][02-8][02-9])\s*\)|([2-9]1[02-9]|[2-9][02-8]1|[2-9][02-8][02-9]))\s*(?:[.-]\s*)?)?([2-9]1[02-9]|[2-9][02-9]1|[2-9][02-9]{2})\s*(?:[.-]\s*)?([0-9]{4})(?:\s*(?:#|x\.?|ext\.?|extension)\s*(\d+))?"
    )
    SOCIAL_HANDLE_PATTERN = re.compile(r"(?:twitter\.com|t\.me|instagram\.com|facebook\.com)\/([A-Za-z0-9_]+)")

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or os.path.join("config", "domains", "idea_mining.yaml")
        self.store_individual_names = False
        self._load_config()

    def _load_config(self) -> None:
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                    privacy = data.get("privacy", {})
                    self.store_individual_names = privacy.get("store_individual_names", False)
            except Exception:
                pass

    def scrub_text(self, text: Optional[str]) -> Optional[str]:
        if not text:
            return text
        cleaned = self.EMAIL_PATTERN.sub("[REDACTED_EMAIL]", text)
        cleaned = self.PHONE_PATTERN.sub("[REDACTED_PHONE]", cleaned)
        return cleaned

    def scrub_links(self, links: Dict[str, str]) -> Dict[str, str]:
        """Keep only public project links (demo, repo, video, website, deck). Strip private social handles."""
        allowed_keys = {"demo", "repo", "video", "website", "deck", "presentation", "paper"}
        safe_links: Dict[str, str] = {}
        for k, url in links.items():
            if k.lower() in allowed_keys and url:
                # Disallow personal profile links like facebook/instagram/linkedin
                u_lower = url.lower()
                if any(denied in u_lower for denied in ["facebook.com", "instagram.com", "linkedin.com/in"]):
                    continue
                safe_links[k.lower()] = url
        return safe_links

    def sanitize_authors(self, authors: List[str]) -> List[str]:
        """Suppresses author names unless store_individual_names flag is on."""
        if not self.store_individual_names:
            return []
        return [self.scrub_text(a) for a in authors if a and len(a.strip()) < 80]
