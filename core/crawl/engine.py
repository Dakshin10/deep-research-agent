from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hashlib
import os
import time
from typing import Any, Callable, Dict, List, Optional
import urllib.parse
import httpx

from core.crawl.schemas import (
    CrawlEvent,
    CrawlMode,
    CrawlRunConfig,
    CrawlRunRecord,
    CrawlRunStatus,
    FrontierItem,
    FrontierState,
)
from core.crawl.storage import RawDocumentStore
from core.crawl.store import CrawlStore
from core.fetch.base import FetchedDocument
from core.fetch.politeness import CircuitBreaker, RobotsCache, TokenBucketRateLimiter, backoff_with_jitter
from core.search.canonical import normalize_canonical_url
from core.sources.adapters.base import AdapterBrokenError, SourceAdapter
from core.sources.policy import SourcePolicyEngine
from core.sources.registry import SourceRegistry
from core.sources.schemas import RawProject


class CrawlEngine:
    """
    Bulk, resumable, incremental crawler with strict politeness and source-policy enforcement.
    Modes:
      - discover: crawls listing pages/sitemaps via adapters and populates crawl_frontier.
      - fetch: downloads and extracts projects from pending frontier items.
      - refresh: incremental re-check utilizing HTTP ETag, Last-Modified, and SHA-256 hashes.
    """

    DEFAULT_USER_AGENT = (
        "DeepResearchBot/2.0 (+https://example.com/bot; contact@deep-research.local)"
    )

    def __init__(
        self,
        store: CrawlStore,
        doc_store: Optional[RawDocumentStore] = None,
        policy_engine: Optional[SourcePolicyEngine] = None,
        robots_cache: Optional[RobotsCache] = None,
        user_agent: Optional[str] = None,
    ):
        self.store = store
        self.doc_store = doc_store or RawDocumentStore()
        self.policy = policy_engine or SourcePolicyEngine()
        self.user_agent = (
            user_agent
            or os.environ.get("CRAWL_USER_AGENT")
            or self.DEFAULT_USER_AGENT
        )
        self.robots = robots_cache or RobotsCache(user_agent=self.user_agent)
        self.rate_limiter = TokenBucketRateLimiter(rate=2.0, capacity=4.0)
        self.circuit_breaker = CircuitBreaker(failure_threshold=3, cooldown_seconds=30.0)

        # Semaphores for concurrency control
        self._domain_locks: Dict[str, asyncio.Semaphore] = {}
        self._global_lock = asyncio.Lock()

    def _get_domain_sem(self, domain: str, max_concurrent: int = 2) -> asyncio.Semaphore:
        domain = domain.lower()
        if domain not in self._domain_locks:
            self._domain_locks[domain] = asyncio.Semaphore(max_concurrent)
        return self._domain_locks[domain]

    async def run(
        self,
        config: CrawlRunConfig,
        on_project_extracted: Optional[Callable[[RawProject, FetchedDocument], Any]] = None,
    ) -> CrawlRunRecord:
        """Executes a crawl run with given config, resumable from existing frontier."""
        run_id = f"crawl_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{os.urandom(3).hex()}"
        run_record = CrawlRunRecord(
            id=run_id,
            source=config.source,
            mode=config.mode,
            status=CrawlRunStatus.RUNNING,
            since_date=config.since_date,
            limit_pages=config.limit_pages,
            config_override=config.model_dump(),
        )
        await self.store.create_crawl_run(run_record)

        await self.store.emit_event(
            CrawlEvent(
                run_id=run_id,
                event_type="crawl_started",
                payload={"source": config.source, "mode": config.mode.value, "limit": config.limit_pages},
            )
        )

        start_time = time.monotonic()
        pages_crawled = 0
        pages_skipped = 0
        pages_discovered = 0
        bytes_downloaded = 0
        errors_count = 0
        errors_by_domain: Dict[str, int] = {}

        try:
            # 1. DISCOVER PHASE
            if config.mode in (CrawlMode.DISCOVER, CrawlMode.ALL):
                adapter = SourceRegistry.get(config.source)
                if not adapter:
                    raise ValueError(f"Unknown source adapter '{config.source}'")

                try:
                    since_yr = int(config.since_date) if (config.since_date and str(config.since_date).isdigit()) else None
                    disc_res = adapter.discover(since_year=since_yr, limit=config.limit_pages)
                    urls = []
                    if hasattr(disc_res, "__aiter__"):
                        async for u in disc_res:
                            if u:
                                urls.append(u)
                    elif asyncio.iscoroutine(disc_res):
                        urls = await disc_res
                    else:
                        urls = list(disc_res)

                    frontier_items = [
                        FrontierItem(
                            id=f"cf_{hashlib.sha256(f'{config.source}:{normalize_canonical_url(u)}'.encode()).hexdigest()[:16]}",
                            url=u,
                            canonical_url=normalize_canonical_url(u),
                            source=config.source,
                            state=FrontierState.PENDING,
                            priority=10,
                        )
                        for u in urls
                    ]
                    added = await self.store.add_frontier_items(frontier_items)
                    pages_discovered += added
                    await self.store.update_crawl_run(run_id, pages_discovered=pages_discovered)
                except AdapterBrokenError as e:
                    await self.store.emit_event(
                        CrawlEvent(
                            run_id=run_id,
                            event_type="adapter_broken",
                            payload={"source": config.source, "error": str(e)},
                        )
                    )
                    raise

            # If mode was discover only, complete run now
            if config.mode == CrawlMode.DISCOVER:
                await self.store.update_crawl_run(run_id, finished=True)
                return (await self.store.get_crawl_run(run_id)) or run_record

            # 2. FETCH / REFRESH PHASE
            global_sem = asyncio.Semaphore(config.global_concurrency)

            async with httpx.AsyncClient(
                timeout=15.0,
                follow_redirects=True,
                headers={"User-Agent": self.user_agent},
            ) as client:
                while pages_crawled < config.limit_pages:
                    # Check limits
                    if bytes_downloaded >= config.max_bytes:
                        break
                    if (time.monotonic() - start_time) >= config.max_duration_seconds:
                        break

                    # Claim batch from frontier
                    batch_size = min(10, config.limit_pages - pages_crawled)
                    items = await self.store.claim_frontier_items(
                        batch_size=batch_size, source=config.source
                    )
                    if not items:
                        break  # Frontier exhausted

                    for item in items:
                        if pages_crawled >= config.limit_pages:
                            break

                        parsed_url = urllib.parse.urlparse(item.url)
                        domain = parsed_url.netloc.lower()

                        # A. Check Source Policy
                        if not self.policy.is_domain_allowed(domain):
                            await self.store.mark_frontier_failed(
                                item.id, error="Domain refused by source policy", backoff_seconds=3600
                            )
                            await self.store.emit_event(
                                CrawlEvent(
                                    run_id=run_id,
                                    event_type="page_blocked",
                                    payload={"url": item.url, "reason": "policy_denied", "domain": domain},
                                )
                            )
                            continue

                        # B. Check Circuit Breaker
                        if not await self.circuit_breaker.is_available(domain):
                            await self.store.mark_frontier_failed(
                                item.id, error="Circuit breaker open", backoff_seconds=30
                            )
                            errors_count += 1
                            errors_by_domain[domain] = errors_by_domain.get(domain, 0) + 1
                            continue

                        # C. Check Robots.txt
                        is_allowed = await self.robots.is_allowed(item.url, client=client)
                        if not is_allowed:
                            await self.store.mark_frontier_failed(
                                item.id, error="Blocked by robots.txt", backoff_seconds=86400
                            )
                            await self.store.emit_event(
                                CrawlEvent(
                                    run_id=run_id,
                                    event_type="page_blocked",
                                    payload={"url": item.url, "reason": "robots_txt", "domain": domain},
                                )
                            )
                            continue

                        # D. Robots crawl-delay
                        crawl_delay = await self.robots.get_crawl_delay(item.url)
                        if crawl_delay and crawl_delay > 0:
                            await asyncio.sleep(min(crawl_delay, 5.0))

                        # E. Acquire domain & rate limiter locks
                        domain_sem = self._get_domain_sem(domain, config.domain_concurrency)
                        async with global_sem:
                            async with domain_sem:
                                await self.rate_limiter.acquire(domain)

                                # Prepare conditional headers for refresh mode
                                req_headers = {"User-Agent": self.user_agent}
                                if config.mode in (CrawlMode.REFRESH, CrawlMode.ALL):
                                    if item.last_etag:
                                        req_headers["If-None-Match"] = item.last_etag
                                    if item.last_modified:
                                        req_headers["If-Modified-Since"] = item.last_modified

                                try:
                                    resp = await client.get(item.url, headers=req_headers)
                                    status = resp.status_code

                                    if status == 304:
                                        # Not modified! Incremental refresh skip
                                        pages_skipped += 1
                                        await self.store.mark_frontier_skipped(item.id)
                                        await self.store.emit_event(
                                            CrawlEvent(
                                                run_id=run_id,
                                                event_type="page_skipped",
                                                payload={"url": item.url, "reason": "304_not_modified"},
                                            )
                                        )
                                        continue

                                    if status == 429 or status >= 500:
                                        await self.circuit_breaker.record_failure(domain)
                                        errors_count += 1
                                        errors_by_domain[domain] = errors_by_domain.get(domain, 0) + 1
                                        await backoff_with_jitter(item.attempts)
                                        await self.store.mark_frontier_failed(
                                            item.id, error=f"HTTP {status}", backoff_seconds=60
                                        )
                                        continue

                                    if status >= 400:
                                        errors_count += 1
                                        errors_by_domain[domain] = errors_by_domain.get(domain, 0) + 1
                                        await self.store.mark_frontier_failed(
                                            item.id, error=f"HTTP {status}", backoff_seconds=3600
                                        )
                                        continue

                                    # Success
                                    await self.circuit_breaker.record_success(domain)
                                    raw_text = resp.text
                                    content_bytes = resp.content
                                    bytes_downloaded += len(content_bytes)

                                    content_hash = hashlib.sha256(content_bytes).hexdigest()
                                    etag = resp.headers.get("etag")
                                    last_mod = resp.headers.get("last-modified")

                                    # Check hash match on refresh mode
                                    if config.mode == CrawlMode.REFRESH and item.content_hash == content_hash:
                                        pages_skipped += 1
                                        await self.store.mark_frontier_skipped(item.id)
                                        continue

                                    # Store raw document
                                    self.doc_store.store_document(
                                        url=item.url,
                                        content=content_bytes,
                                        content_type=resp.headers.get("content-type", "text/html"),
                                        metadata={"etag": etag, "last_modified": last_mod},
                                    )

                                    # Wrap in FetchedDocument
                                    doc = FetchedDocument(
                                        url=item.url,
                                        final_url=str(resp.url),
                                        status=status,
                                        content_type=resp.headers.get("content-type", "text/html"),
                                        content_hash=content_hash,
                                        raw_text=raw_text,
                                    )

                                    # Parse via adapter
                                    adapter = SourceRegistry.get(item.source)
                                    if adapter:
                                        try:
                                            parse_res = adapter.parse(item.url, raw_text)
                                            raw_proj = await parse_res if asyncio.iscoroutine(parse_res) else parse_res
                                            if on_project_extracted:
                                                res = on_project_extracted(raw_proj, doc)
                                                if asyncio.iscoroutine(res):
                                                    await res
                                        except AdapterBrokenError as e:
                                            await self.store.emit_event(
                                                CrawlEvent(
                                                    run_id=run_id,
                                                    event_type="adapter_broken",
                                                    payload={"source": item.source, "url": item.url, "error": str(e)},
                                                )
                                            )

                                    # Mark completed
                                    await self.store.mark_frontier_completed(
                                        item.id,
                                        content_hash=content_hash,
                                        last_etag=etag,
                                        last_modified=last_mod,
                                    )
                                    pages_crawled += 1

                                    await self.store.emit_event(
                                        CrawlEvent(
                                            run_id=run_id,
                                            event_type="page_fetched",
                                            payload={
                                                "url": item.url,
                                                "status": status,
                                                "bytes": len(content_bytes),
                                                "content_hash": content_hash,
                                            },
                                        )
                                    )

                                except Exception as exc:
                                    await self.circuit_breaker.record_failure(domain)
                                    errors_count += 1
                                    errors_by_domain[domain] = errors_by_domain.get(domain, 0) + 1
                                    await self.store.mark_frontier_failed(
                                        item.id, error=str(exc), backoff_seconds=30
                                    )

                    # Update run progress periodically
                    await self.store.update_crawl_run(
                        run_id,
                        pages_crawled=pages_crawled,
                        pages_skipped=pages_skipped,
                        bytes_downloaded=bytes_downloaded,
                        errors_count=errors_count,
                        errors_by_domain=errors_by_domain,
                    )

            # Finish run
            await self.store.update_crawl_run(
                run_id,
                pages_crawled=pages_crawled,
                pages_skipped=pages_skipped,
                bytes_downloaded=bytes_downloaded,
                errors_count=errors_count,
                errors_by_domain=errors_by_domain,
                finished=True,
            )

            await self.store.emit_event(
                CrawlEvent(
                    run_id=run_id,
                    event_type="crawl_completed",
                    payload={
                        "pages_crawled": pages_crawled,
                        "pages_skipped": pages_skipped,
                        "bytes_downloaded": bytes_downloaded,
                        "errors": errors_count,
                    },
                )
            )

        except Exception as e:
            await self.store.update_crawl_run(
                run_id,
                status=CrawlRunStatus.FAILED,
                finished=True,
            )
            await self.store.emit_event(
                CrawlEvent(
                    run_id=run_id,
                    event_type="crawl_failed",
                    payload={"error": str(e)},
                )
            )
            raise

        return (await self.store.get_crawl_run(run_id)) or run_record
