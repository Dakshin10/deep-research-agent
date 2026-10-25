-- PostgreSQL Schema for Phase 3 Idea Miner Idea Records & pgvector Hybrid Index

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS idea_records (
    id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64),
    name VARCHAR(255) NOT NULL,
    one_liner TEXT,
    problem TEXT,
    solution TEXT,
    target_users TEXT,
    domain_tags JSONB DEFAULT '[]'::jsonb,
    tech_stack JSONB DEFAULT '[]'::jsonb,
    business_model TEXT,
    stage VARCHAR(32) NOT NULL DEFAULT 'prototype',
    traction TEXT,
    source_kind VARCHAR(32) NOT NULL DEFAULT 'hackathon',
    event_name VARCHAR(255),
    year INT,
    placement VARCHAR(32) NOT NULL DEFAULT 'none',
    team_size INT,
    links JSONB DEFAULT '{}'::jsonb,
    first_seen_url TEXT NOT NULL,
    all_source_urls JSONB DEFAULT '[]'::jsonb,
    confidence FLOAT NOT NULL DEFAULT 1.0,
    evidence JSONB DEFAULT '{}'::jsonb,
    embedding vector(384),
    tsv_body tsvector GENERATED ALWAYS AS (
        to_tsvector('english', coalesce(name, '') || ' ' || coalesce(one_liner, '') || ' ' || coalesce(problem, '') || ' ' || coalesce(solution, '') || ' ' || coalesce(target_users, ''))
    ) STORED,
    merged_into_id VARCHAR(64),
    merge_history JSONB DEFAULT '[]'::jsonb,
    extracted_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Row-Level Security: shared public records visible to all; private tenant records isolated
ALTER TABLE idea_records ENABLE ROW LEVEL SECURITY;

CREATE POLICY idea_records_tenant_isolation ON idea_records
    USING (tenant_id IS NULL OR tenant_id = current_setting('app.tenant_id', true));

CREATE INDEX IF NOT EXISTS idx_idea_records_tenant ON idea_records (tenant_id);
CREATE INDEX IF NOT EXISTS idx_idea_records_name ON idea_records (name);
CREATE INDEX IF NOT EXISTS idx_idea_records_year ON idea_records (year);
CREATE INDEX IF NOT EXISTS idx_idea_records_placement ON idea_records (placement);
CREATE INDEX IF NOT EXISTS idx_idea_records_tsv ON idea_records USING gin (tsv_body);
CREATE INDEX IF NOT EXISTS idx_idea_records_embedding ON idea_records USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Merge Audit Trail
CREATE TABLE IF NOT EXISTS idea_merges (
    id VARCHAR(64) PRIMARY KEY,
    surviving_id VARCHAR(64) NOT NULL REFERENCES idea_records(id) ON DELETE CASCADE,
    merged_id VARCHAR(64) NOT NULL,
    reason TEXT NOT NULL,
    snapshot_json JSONB NOT NULL,
    merged_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
