from __future__ import annotations

import argparse
import asyncio
import os
import sys

from core.crawl.engine import CrawlEngine
from core.crawl.schemas import CrawlMode, CrawlRunConfig
from core.crawl.storage import RawDocumentStore
from core.crawl.store import CrawlStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Idea Miner Crawl Engine CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run crawler for a source")
    run_parser.add_argument("--source", type=str, required=True, help="Source adapter ID (e.g. devpost, yc)")
    run_parser.add_argument("--mode", type=str, default="all", choices=["discover", "fetch", "refresh", "all"], help="Crawl mode")
    run_parser.add_argument("--since", type=str, default=None, help="Crawl since year/date (e.g. 2022)")
    run_parser.add_argument("--limit", type=int, default=500, help="Max pages to crawl")
    run_parser.add_argument("--db-url", type=str, default=None, help="PostgreSQL or SQLite DB URL")
    run_parser.add_argument("--data-dir", type=str, default=None, help="Raw document storage directory")

    return parser


async def main_async() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "run":
        db_url = args.db_url or os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///crawl.db")
        store = CrawlStore(db_url=db_url)
        await store.init_db()

        doc_store = RawDocumentStore(base_dir=args.data_dir)
        engine = CrawlEngine(store=store, doc_store=doc_store)

        config = CrawlRunConfig(
            source=args.source,
            mode=CrawlMode(args.mode),
            since_date=args.since,
            limit_pages=args.limit,
        )

        print(f"🚀 Starting crawl run for source '{args.source}' (mode={args.mode}, since={args.since}, limit={args.limit})...")
        run_record = await engine.run(config)
        print("✅ Crawl run completed!")
        print(f"   Run ID: {run_record.id}")
        print(f"   Status: {run_record.status.value}")
        print(f"   Pages Discovered: {run_record.pages_discovered}")
        print(f"   Pages Crawled: {run_record.pages_crawled}")
        print(f"   Pages Skipped: {run_record.pages_skipped}")
        print(f"   Bytes Downloaded: {run_record.bytes_downloaded}")
        print(f"   Errors: {run_record.errors_count}")
        return 0

    return 1


def main() -> None:
    code = asyncio.run(main_async())
    sys.exit(code)


if __name__ == "__main__":
    main()
