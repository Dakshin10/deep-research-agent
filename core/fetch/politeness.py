from __future__ import annotations

import asyncio
import random
import time
from typing import Dict, Optional
import urllib.parse
import urllib.robotparser
import httpx


class RobotsCache:
    """Caches and checks robots.txt files per domain with TTL."""

    def __init__(self, ttl_seconds: float = 86400.0, user_agent: str = "DeepResearchBot/2.0"):
        self.ttl_seconds = ttl_seconds
        self.user_agent = user_agent
        self._parsers: Dict[str, tuple[urllib.robotparser.RobotFileParser, float]] = {}
        self._lock = asyncio.Lock()

    async def is_allowed(self, url: str, client: Optional[httpx.AsyncClient] = None) -> bool:
        """Check if robots.txt permits crawling the given URL."""
        parsed = urllib.parse.urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return True
        if parsed.scheme not in ("http", "https"):
            return True

        domain = parsed.netloc.lower()
        now = time.time()

        async with self._lock:
            cached = self._parsers.get(domain)
            if cached and (now - cached[1]) < self.ttl_seconds:
                return cached[0].can_fetch(self.user_agent, url)

        # Fetch robots.txt
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        rp = urllib.robotparser.RobotFileParser()
        try:
            if client:
                resp = await client.get(robots_url, timeout=5.0)
                if resp.status_code == 200:
                    rp.parse(resp.text.splitlines())
                else:
                    rp.allow_all = True
            else:
                async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as c:
                    resp = await c.get(robots_url, headers={"User-Agent": self.user_agent})
                    if resp.status_code == 200:
                        rp.parse(resp.text.splitlines())
                    else:
                        rp.allow_all = True
        except Exception:
            rp.allow_all = True

        async with self._lock:
            self._parsers[domain] = (rp, now)

        return rp.can_fetch(self.user_agent, url)


class TokenBucketRateLimiter:
    """Per-domain token bucket rate limiter."""

    def __init__(self, rate: float = 3.0, capacity: float = 6.0):
        self.rate = rate
        self.capacity = capacity
        # domain -> (tokens, last_refreshed)
        self._buckets: Dict[str, tuple[float, float]] = {}
        self._lock = asyncio.Lock()

    async def acquire(self, domain: str) -> None:
        """Wait until a token is available for the given domain."""
        domain = domain.lower()
        while True:
            wait_time = 0.0
            async with self._lock:
                now = time.monotonic()
                tokens, last_time = self._buckets.get(domain, (self.capacity, now))
                # Add tokens based on elapsed time
                elapsed = now - last_time
                tokens = min(self.capacity, tokens + elapsed * self.rate)

                if tokens >= 1.0:
                    self._buckets[domain] = (tokens - 1.0, now)
                    return
                else:
                    wait_time = (1.0 - tokens) / self.rate
                    self._buckets[domain] = (tokens, now)

            if wait_time > 0:
                await asyncio.sleep(wait_time)


class CircuitBreaker:
    """Per-domain circuit breaker that enters cooldown after consecutive failures."""

    def __init__(self, failure_threshold: int = 3, cooldown_seconds: float = 60.0):
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        # domain -> (consecutive_failures, open_until_monotonic)
        self._states: Dict[str, tuple[int, float]] = {}
        self._lock = asyncio.Lock()

    async def is_available(self, domain: str) -> bool:
        domain = domain.lower()
        async with self._lock:
            state = self._states.get(domain)
            if not state:
                return True
            failures, open_until = state
            now = time.monotonic()
            if open_until > now:
                return False
            # Cooldown passed, allow probe
            if failures >= self.failure_threshold:
                self._states[domain] = (self.failure_threshold - 1, 0.0)
            return True

    async def record_success(self, domain: str) -> None:
        domain = domain.lower()
        async with self._lock:
            self._states.pop(domain, None)

    async def record_failure(self, domain: str) -> None:
        domain = domain.lower()
        now = time.monotonic()
        async with self._lock:
            failures, _ = self._states.get(domain, (0, 0.0))
            failures += 1
            open_until = now + self.cooldown_seconds if failures >= self.failure_threshold else 0.0
            self._states[domain] = (failures, open_until)


async def backoff_with_jitter(attempt: int, base_delay: float = 1.0, max_delay: float = 10.0) -> None:
    """Sleep with exponential backoff and randomized jitter."""
    delay = min(max_delay, base_delay * (2 ** attempt))
    jitter = random.uniform(0.1, 0.5) * delay
    await asyncio.sleep(delay + jitter)
