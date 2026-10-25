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
