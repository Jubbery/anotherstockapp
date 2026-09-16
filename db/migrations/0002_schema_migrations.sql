-- 0002_schema_migrations.sql
--
-- Applied-migration ledger. Forward-only: this table records what ran and when,
-- and there is no `down` column because there are no down migrations (R-C.a).
-- Rolling a schema backwards against a database holding position state is not a
-- recovery procedure; restoring from a verified backup is (R-16.4.d).

BEGIN;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version     text        PRIMARY KEY,
    applied_at  timestamptz NOT NULL DEFAULT now(),
    checksum    text        NOT NULL,
    applied_by  text        NOT NULL DEFAULT current_user
);

COMMENT ON COLUMN schema_migrations.checksum IS
    'SHA-256 of the migration file as applied. A mismatch on a later run means a '
    'released migration was edited, which is forbidden (R-C.a).';

ALTER TABLE schema_migrations ENABLE ROW LEVEL SECURITY;
ALTER TABLE schema_migrations FORCE ROW LEVEL SECURITY;

COMMIT;
