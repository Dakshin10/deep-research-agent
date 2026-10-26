-- ============================================================================
-- Unified Chat Persistence Schema with Multi-Tenancy & Row-Level Security
-- ============================================================================

CREATE TABLE IF NOT EXISTS conversations (
    id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    title VARCHAR(255) NOT NULL DEFAULT 'New Research Chat',
    active_branch_leaf_id VARCHAR(64),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_conversations_tenant_updated
    ON conversations (tenant_id, updated_at DESC);

-- Enable RLS
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversations FORCE ROW LEVEL SECURITY;

CREATE POLICY conversations_tenant_isolation ON conversations
    FOR ALL
    USING (tenant_id = current_setting('app.tenant_id', true));

-- ----------------------------------------------------------------------------
-- Messages Table (Supports Tree Branching)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS messages (
    id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    conversation_id VARCHAR(64) NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    parent_id VARCHAR(64),
    role VARCHAR(32) NOT NULL,
    content TEXT NOT NULL,
    citations JSONB NOT NULL DEFAULT '[]'::jsonb,
    artifacts JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation_parent
    ON messages (conversation_id, parent_id, created_at ASC);

ALTER TABLE messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages FORCE ROW LEVEL SECURITY;

CREATE POLICY messages_tenant_isolation ON messages
    FOR ALL
    USING (tenant_id = current_setting('app.tenant_id', true));

-- ----------------------------------------------------------------------------
-- Message Parts Table (Structured parts: tool_call, code_execution, etc.)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS message_parts (
    id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    message_id VARCHAR(64) NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    part_type VARCHAR(64) NOT NULL,
    content TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    ordinal_index INT NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_message_parts_message
    ON message_parts (message_id, ordinal_index ASC);

ALTER TABLE message_parts ENABLE ROW LEVEL SECURITY;
ALTER TABLE message_parts FORCE ROW LEVEL SECURITY;

CREATE POLICY message_parts_tenant_isolation ON message_parts
    FOR ALL
    USING (tenant_id = current_setting('app.tenant_id', true));

-- ----------------------------------------------------------------------------
-- Attachments Table
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS attachments (
    id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    message_id VARCHAR(64) REFERENCES messages(id) ON DELETE CASCADE,
    file_name VARCHAR(255) NOT NULL,
    mime_type VARCHAR(128) NOT NULL,
    size_bytes BIGINT NOT NULL DEFAULT 0,
    minio_path TEXT NOT NULL,
    extracted_text TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE attachments ENABLE ROW LEVEL SECURITY;
ALTER TABLE attachments FORCE ROW LEVEL SECURITY;

CREATE POLICY attachments_tenant_isolation ON attachments
    FOR ALL
    USING (tenant_id = current_setting('app.tenant_id', true));

-- ----------------------------------------------------------------------------
-- Turn Feedback Table
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS turn_feedback (
    id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    message_id VARCHAR(64) NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    rating VARCHAR(16) NOT NULL, -- thumbs_up, thumbs_down
    feedback_text TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE turn_feedback ENABLE ROW LEVEL SECURITY;
ALTER TABLE turn_feedback FORCE ROW LEVEL SECURITY;

CREATE POLICY turn_feedback_tenant_isolation ON turn_feedback
    FOR ALL
    USING (tenant_id = current_setting('app.tenant_id', true));
