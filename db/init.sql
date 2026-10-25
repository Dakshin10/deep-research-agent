-- Initialize extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Ensure application settings namespace exists
-- (current_setting('app.tenant_id', true))

-- Base schema definitions will be handled via SQLAlchemy / Alembic migrations
