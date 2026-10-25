-- PostgreSQL Schema for Phase 2 Idea Miner Crawler

CREATE TABLE IF NOT EXISTS crawl_sources (
    source_id VARCHAR(64) PRIMARY KEY,
    domain VARCHAR(255) NOT NULL,
    name VARCHAR(128) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    config_json JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS crawl_frontier (
    id VARCHAR(64) PRIMARY KEY,
    url TEXT NOT NULL,
    canonical_url TEXT NOT NULL,
    source VARCHAR(64) NOT NULL,
    state VARCHAR(32) NOT NULL DEFAULT 'pending',
    priority INT NOT NULL DEFAULT 10,
    attempts INT NOT NULL DEFAULT 0,
    max_attempts INT NOT NULL DEFAULT 3,
    next_attempt_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_etag VARCHAR(128),
    last_modified VARCHAR(128),
    content_hash VARCHAR(64),
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT uq_crawl_frontier_source_url UNIQUE (source, canonical_url)
);

CREATE INDEX IF NOT EXISTS idx_crawl_frontier_claim ON crawl_frontier (state, next_attempt_at, priority DESC);
CREATE INDEX IF NOT EXISTS idx_crawl_frontier_source ON crawl_frontier (source, state);

CREATE TABLE IF NOT EXISTS crawl_runs (
    id VARCHAR(64) PRIMARY KEY,
    source VARCHAR(64) NOT NULL,
    mode VARCHAR(32) NOT NULL DEFAULT 'all',
    status VARCHAR(32) NOT NULL DEFAULT 'running',
    since_date VARCHAR(32),
    limit_pages INT DEFAULT 1000,
    pages_discovered INT DEFAULT 0,
    pages_crawled INT DEFAULT 0,
    pages_skipped INT DEFAULT 0,
    bytes_downloaded BIGINT DEFAULT 0,
    errors_count INT DEFAULT 0,
    errors_by_domain JSONB DEFAULT '{}'::jsonb,
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    finished_at TIMESTAMP WITH TIME ZONE,
    config_override JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_crawl_runs_source ON crawl_runs (source, status);
