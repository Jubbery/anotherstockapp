-- 0001_audit_log.sql
--
-- The audit log comes first, before any table it audits, because R-3.7.a makes
-- it a participant in every money-, position-, and authorization-changing
-- transaction. A schema where the audit table arrives later is a schema where
-- some writes were, for a while, unaudited.
--
-- Spec: MASTER_SPEC §17.4, R-3.7.a, R-3.7.b, Appendix C.
-- Migrations are forward-only. A correction is a new migration, never an edit
-- to a released one (R-C.a).

BEGIN;

CREATE TABLE IF NOT EXISTS audit_log (
    id              bigserial PRIMARY KEY,
    occurred_at     timestamptz NOT NULL DEFAULT now(),

    -- Who acted. 'engine' | 'api' | 'worker' | 'operator'
    -- | 'webhook:telegram' | 'webhook:twilio' | 'deadman'
    actor           text        NOT NULL,
    actor_detail    text,

    -- What happened, and to what.
    action          text        NOT NULL,
    entity_type     text,
    entity_id       text,
    before          jsonb,
    after           jsonb,
    reason          text,

    -- Provenance. R-17.1.b: correlation_id threads scan -> rank -> intent ->
    -- risk decision -> order -> fill -> PnL, so one trade is one query.
    correlation_id  text,
    request_ip      inet,

    -- R-11.1.d: every record says which account it belongs to. An audit row
    -- that does not distinguish paper from live is not much of an audit row.
    environment     text        NOT NULL,
    git_sha         text        NOT NULL,
    config_hash     text        NOT NULL,

    CONSTRAINT audit_log_environment_known
        CHECK (environment IN ('paper', 'live'))
);

COMMENT ON TABLE audit_log IS
    'Append-only. R-3.7.b. Written in the same transaction as the change it '
    'describes (R-3.7.a) -- if the audit write fails, the money write rolls back.';

CREATE INDEX IF NOT EXISTS audit_log_occurred_at_idx
    ON audit_log (occurred_at DESC);
CREATE INDEX IF NOT EXISTS audit_log_entity_idx
    ON audit_log (entity_type, entity_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS audit_log_correlation_idx
    ON audit_log (correlation_id)
    WHERE correlation_id IS NOT NULL;

-- ---------------------------------------------------------------------------
-- R-3.7.b: append-only, enforced for ALL roles including the table owner.
--
-- A BEFORE ... FOR EACH STATEMENT trigger fires even when the statement matches
-- no rows, so `DELETE FROM audit_log WHERE false` is refused too. That matters:
-- a permission model can be changed by anyone holding the service role key, and
-- this cannot.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION audit_log_is_append_only()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION
        'audit_log is append-only (MASTER_SPEC R-3.7.b); % rejected', TG_OP
        USING ERRCODE = 'restrict_violation';
END;
$$;

DROP TRIGGER IF EXISTS audit_log_no_update ON audit_log;
CREATE TRIGGER audit_log_no_update
    BEFORE UPDATE ON audit_log
    FOR EACH STATEMENT
    EXECUTE FUNCTION audit_log_is_append_only();

DROP TRIGGER IF EXISTS audit_log_no_delete ON audit_log;
CREATE TRIGGER audit_log_no_delete
    BEFORE DELETE ON audit_log
    FOR EACH STATEMENT
    EXECUTE FUNCTION audit_log_is_append_only();

DROP TRIGGER IF EXISTS audit_log_no_truncate ON audit_log;
CREATE TRIGGER audit_log_no_truncate
    BEFORE TRUNCATE ON audit_log
    FOR EACH STATEMENT
    EXECUTE FUNCTION audit_log_is_append_only();

-- R-16.4.a: RLS on every table. The anon role reaches nothing; the backend uses
-- the service role. No policy is created here, so the default deny stands.
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log FORCE ROW LEVEL SECURITY;

COMMIT;
