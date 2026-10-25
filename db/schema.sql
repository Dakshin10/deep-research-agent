-- PostgreSQL Schema with Row-Level Security (RLS) for Deep Researcher

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Jobs Table
CREATE TABLE IF NOT EXISTS jobs (
    id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    query TEXT NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    mode VARCHAR(32) NOT NULL DEFAULT 'deep',
    confidence FLOAT DEFAULT 1.0,
    brief JSONB,
    plan JSONB,
    report TEXT,
    budget JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

ALTER TABLE jobs ENABLE ROW LEVEL SECURITY;
CREATE POLICY jobs_tenant_isolation ON jobs
    USING (tenant_id = current_setting('app.tenant_id', true));

-- 2. Research Notes Table
CREATE TABLE IF NOT EXISTS research_notes (
    id VARCHAR(64) PRIMARY KEY,
    job_id VARCHAR(64) NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    tenant_id VARCHAR(64) NOT NULL,
    claim TEXT NOT NULL,
    source_type VARCHAR(32) NOT NULL DEFAULT 'web',
    source_url TEXT,
    document_id VARCHAR(64),
    excerpt TEXT NOT NULL,
    confidence FLOAT DEFAULT 0.9,
    task_id VARCHAR(64) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

ALTER TABLE research_notes ENABLE ROW LEVEL SECURITY;
CREATE POLICY notes_tenant_isolation ON research_notes
    USING (tenant_id = current_setting('app.tenant_id', true));

-- Research Notes Phase 3 Location Columns Migration
ALTER TABLE research_notes ADD COLUMN IF NOT EXISTS url TEXT;
ALTER TABLE research_notes ADD COLUMN IF NOT EXISTS canonical_url TEXT;
ALTER TABLE research_notes ADD COLUMN IF NOT EXISTS title TEXT;
ALTER TABLE research_notes ADD COLUMN IF NOT EXISTS source_family VARCHAR(64);
ALTER TABLE research_notes ADD COLUMN IF NOT EXISTS provider VARCHAR(64);
ALTER TABLE research_notes ADD COLUMN IF NOT EXISTS retrieved_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE research_notes ADD COLUMN IF NOT EXISTS content_hash VARCHAR(64);
ALTER TABLE research_notes ADD COLUMN IF NOT EXISTS char_start INT;
ALTER TABLE research_notes ADD COLUMN IF NOT EXISTS char_end INT;
ALTER TABLE research_notes ADD COLUMN IF NOT EXISTS page_no INT;
ALTER TABLE research_notes ADD COLUMN IF NOT EXISTS heading_path JSONB DEFAULT '[]'::jsonb;
ALTER TABLE research_notes ADD COLUMN IF NOT EXISTS text_fragment_url TEXT;
ALTER TABLE research_notes ADD COLUMN IF NOT EXISTS video_timestamp_url TEXT;
ALTER TABLE research_notes ADD COLUMN IF NOT EXISTS archive_url TEXT;
ALTER TABLE research_notes ADD COLUMN IF NOT EXISTS is_verified BOOLEAN DEFAULT FALSE;

-- 3. Artifacts Table
CREATE TABLE IF NOT EXISTS artifacts (
    id VARCHAR(64) PRIMARY KEY,
    job_id VARCHAR(64) NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    tenant_id VARCHAR(64) NOT NULL,
    artifact_type VARCHAR(32) NOT NULL,
    title VARCHAR(255) NOT NULL,
    file_path TEXT,
    content TEXT,
    metadata_json JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

ALTER TABLE artifacts ENABLE ROW LEVEL SECURITY;
CREATE POLICY artifacts_tenant_isolation ON artifacts
    USING (tenant_id = current_setting('app.tenant_id', true));

-- 4. Run Events Table
CREATE TABLE IF NOT EXISTS run_events (
    id VARCHAR(64) PRIMARY KEY,
    job_id VARCHAR(64) NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    tenant_id VARCHAR(64) NOT NULL,
    event_type VARCHAR(64) NOT NULL,
    payload_json JSONB DEFAULT '{}'::jsonb,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

ALTER TABLE run_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY events_tenant_isolation ON run_events
    USING (tenant_id = current_setting('app.tenant_id', true));

-- 5. Documents Table
CREATE TABLE IF NOT EXISTS documents (
    id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64),
    filename VARCHAR(255) NOT NULL,
    file_type VARCHAR(32) NOT NULL,
    file_path TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
CREATE POLICY documents_tenant_isolation ON documents
    USING (tenant_id IS NULL OR tenant_id = current_setting('app.tenant_id', true));

-- 6. Document Chunks Table with Vector Support
CREATE TABLE IF NOT EXISTS document_chunks (
    id VARCHAR(64) PRIMARY KEY,
    document_id VARCHAR(64) NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    tenant_id VARCHAR(64),
    chunk_index INT NOT NULL,
    text TEXT NOT NULL,
    embedding vector(384),
    metadata_json JSONB DEFAULT '{}'::jsonb
);

ALTER TABLE document_chunks ENABLE ROW LEVEL SECURITY;
CREATE POLICY chunks_tenant_isolation ON document_chunks
    USING (tenant_id IS NULL OR tenant_id = current_setting('app.tenant_id', true));

CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON document_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- 7. Fetched Documents Cache Table
CREATE TABLE IF NOT EXISTS fetched_documents_cache (
    id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    canonical_url TEXT NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    final_url TEXT NOT NULL,
    status INT NOT NULL,
    content_type VARCHAR(128) NOT NULL,
    title TEXT,
    raw_text TEXT NOT NULL,
    sections_json JSONB DEFAULT '[]'::jsonb,
    pages_json JSONB DEFAULT '[]'::jsonb,
    timestamps_json JSONB DEFAULT '[]'::jsonb,
    fetched_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT uq_tenant_url_hash UNIQUE (tenant_id, canonical_url, content_hash)
);

ALTER TABLE fetched_documents_cache ENABLE ROW LEVEL SECURITY;
CREATE POLICY fetched_docs_tenant_isolation ON fetched_documents_cache
    USING (tenant_id = current_setting('app.tenant_id', true));

CREATE INDEX IF NOT EXISTS idx_fetched_docs_lookup ON fetched_documents_cache (tenant_id, canonical_url);
