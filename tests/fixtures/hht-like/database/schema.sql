-- Database Schema for HHT-Like Fixture
-- IMPLEMENTS REQUIREMENTS:
--   REQ-p00001: User Authentication
--   REQ-d00001: Authentication Module
--   REQ-p00003: Audit Logging
--   REQ-d00003: Audit Trail Implementation

-- Users table
-- Implements: REQ-p00001, REQ-d00001
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    last_login TIMESTAMPTZ,
    failed_attempts INTEGER DEFAULT 0,
    locked_until TIMESTAMPTZ
);

-- Audit log table
-- Implements: REQ-p00003, REQ-d00003
CREATE TABLE audit_log (
    id BIGSERIAL PRIMARY KEY,
    event_type TEXT NOT NULL,
    user_id UUID REFERENCES users(id),
    resource_type TEXT,
    resource_id TEXT,
    action TEXT NOT NULL,
    metadata JSONB,
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    hash TEXT NOT NULL,
    previous_hash TEXT
);

-- Create index for audit queries
CREATE INDEX idx_audit_log_user_id ON audit_log(user_id);
CREATE INDEX idx_audit_log_event_type ON audit_log(event_type);
CREATE INDEX idx_audit_log_created_at ON audit_log(created_at);

-- Trigger function for hash chain
-- Implements: REQ-d00003
CREATE OR REPLACE FUNCTION audit_hash_chain()
RETURNS TRIGGER AS $$
DECLARE
    prev_hash TEXT;
    new_hash TEXT;
BEGIN
    -- Get previous hash
    SELECT hash INTO prev_hash
    FROM audit_log
    ORDER BY id DESC
    LIMIT 1;

    -- Calculate new hash
    NEW.previous_hash := COALESCE(prev_hash, 'genesis');
    NEW.hash := encode(
        sha256(
            (NEW.event_type || NEW.user_id || NEW.action || NEW.created_at || NEW.previous_hash)::bytea
        ),
        'hex'
    );

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_log_hash_chain
    BEFORE INSERT ON audit_log
    FOR EACH ROW
    EXECUTE FUNCTION audit_hash_chain();
