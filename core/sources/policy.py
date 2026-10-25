from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
import urllib.parse
import yaml

from core.fetch.politeness import RobotsCache


class SourcePolicyEngine:
    """
    Enforces source crawl permissions, robots.txt compliance, access methods,
    and rate limits defined in config/source_policy.yaml.
    """

    DENIED_DOMAINS = {
        "linkedin.com",
        "x.com",
        "twitter.com",
        "facebook.com",
        "instagram.com",
        "crunchbase.com",
    }

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or os.path.join("config", "source_policy.yaml")
        self._policy = self._load_policy()
        self.robots_cache = RobotsCache()

    def _load_policy(self) -> Dict[str, Any]:
        p = Path(self.config_path)
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
            except Exception:
                pass
        return {}

    def normalize_domain(self, domain_or_url: str) -> str:
        """Extract clean lowercased domain without port or trailing slashes."""
        if "://" in domain_or_url:
            parsed = urllib.parse.urlparse(domain_or_url)
            domain = parsed.netloc.lower()
        else:
            domain = domain_or_url.lower().strip().split("/")[0]

        if ":" in domain:
            domain = domain.split(":")[0]
        if domain.startswith("www."):
            domain = domain[4:]
        return domain

    def get_domain_rule(self, domain: str) -> Optional[Dict[str, Any]]:
        norm_domain = self.normalize_domain(domain)
        sites = self._policy.get("sites", {})

        # Exact match
        if norm_domain in sites:
            return sites[norm_domain]

        # Check apex domain (e.g. blog.devpost.com -> devpost.com)
        parts = norm_domain.split(".")
        if len(parts) > 2:
            apex = ".".join(parts[-2:])
            if apex in sites:
                return sites[apex]

        return None

    def is_allowed(
        self,
        domain_or_url: str,
        is_search_result: bool = False,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Check if a domain or URL is permitted for crawler extraction.
        Returns (is_allowed, reason, rule_dict).
        """
        norm_domain = self.normalize_domain(domain_or_url)

        # 1. Hard-coded DENIED domains check
        for denied in self.DENIED_DOMAINS:
            if norm_domain == denied or norm_domain.endswith(f".{denied}"):
                return (
                    False,
                    f"DENIED by policy: {norm_domain} forbids automated scraping under Terms of Service. "
                    f"Please use official APIs or manual CSV/JSON import.",
                    {"allowed": False, "rate_limit_rps": 0.0},
                )

        # 2. Configured sites check
        rule = self.get_domain_rule(norm_domain)
        if rule is not None:
            if not rule.get("allowed", False):
                return (
                    False,
                    f"DENIED by config: {norm_domain} is marked disallowed in source_policy.yaml.",
                    rule,
                )
            return (
                True,
                f"ALLOWED: {norm_domain} is authorized via {rule.get('access_method', 'html')}.",
                rule,
            )

        # 3. Default policy for unknown domains
        default_pol = self._policy.get("default_policy", {})
        if is_search_result and default_pol.get("allow_via_search_result", True):
            return (
                True,
                f"ALLOWED: {norm_domain} permitted as verified search engine result hit.",
                default_pol,
            )

        return (
            False,
            f"REFUSED: {norm_domain} is not registered in source_policy.yaml. Direct crawl is prohibited.",
            default_pol,
        )

    async def check_domain_cli(self, domain: str) -> Dict[str, Any]:
        """Runs thorough check including robots.txt inspection for CLI."""
        norm_domain = self.normalize_domain(domain)
        allowed, reason, rule = self.is_allowed(norm_domain)

        # Fetch and parse robots.txt
        robots_url = f"https://{norm_domain}/robots.txt"
        user_agent = os.environ.get("CRAWLER_USER_AGENT", "DeepResearchAgent/1.0 (+https://github.com/deep-research-agent)")
        
        can_fetch = True
        crawl_delay = None
        error_msg = None

        try:
            can_fetch = await self.robots_cache.can_fetch(f"https://{norm_domain}/", user_agent=user_agent)
            crawl_delay = await self.robots_cache.get_crawl_delay(f"https://{norm_domain}/", user_agent=user_agent)
        except Exception as e:
            error_msg = str(e)

        return {
            "domain": norm_domain,
            "policy_allowed": allowed,
            "reason": reason,
            "access_method": rule.get("access_method", "unknown"),
            "rate_limit_rps": rule.get("rate_limit_rps", 0.5),
            "max_pages_per_run": rule.get("max_pages_per_run", 50),
            "robots_respected": rule.get("robots_respected", True),
            "robots_url": robots_url,
            "robots_permits_user_agent": can_fetch,
            "crawl_delay": crawl_delay,
            "error": error_msg,
            "notes": rule.get("notes", ""),
        }


def main():
    parser = argparse.ArgumentParser(description="Source Crawl Policy Checker")
    subparsers = parser.add_subparsers(dest="command")

    check_parser = subparsers.add_parser("check", help="Check crawling policy and robots.txt for a domain")
    check_parser.add_argument("domain", help="Domain to check (e.g. devpost.com, linkedin.com)")

    args = parser.parse_args()

    if args.command == "check":
        engine = SourcePolicyEngine()
        result = asyncio.run(engine.check_domain_cli(args.domain))

        print("\n" + "=" * 60)
        print(f" SOURCE POLICY AUDIT: {result['domain']}")
        print("=" * 60)
        status_str = "ALLOWED" if result["policy_allowed"] else "DENIED / REFUSED"
        print(f"Status:             {status_str}")
        print(f"Reason:             {result['reason']}")
        print(f"Access Method:      {result['access_method']}")
        print(f"Rate Limit:         {result['rate_limit_rps']} req/sec")
        print(f"Max Pages/Run:      {result['max_pages_per_run']}")
        print(f"Robots.txt URL:     {result['robots_url']}")
        print(f"Robots Allows Us:   {result['robots_permits_user_agent']}")
        if result["crawl_delay"]:
            print(f"Crawl Delay:        {result['crawl_delay']} seconds")
        if result["notes"]:
            print(f"Policy Notes:       {result['notes']}")
        print("=" * 60 + "\n")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
