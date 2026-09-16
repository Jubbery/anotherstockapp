-- 0004_bars_daily_partitions.sql
--
-- Yearly partitions for bars_daily. Covers 2015-2030: ten years of history
-- (§6.1) plus headroom.
--
-- There is deliberately NO default partition. A default would silently absorb
-- rows whose session_date falls outside every declared range -- which in practice
-- means a parsing bug that produced a year like 0202 or 2202. Without it the
-- insert fails loudly and ingest records a reject (R-6.6.a). The cost is that
-- someone must add partitions before 2031; the maintenance check in
-- data_quality (§6.7) warns when fewer than two years of headroom remain.

BEGIN;

CREATE TABLE IF NOT EXISTS bars_daily_2015 PARTITION OF bars_daily
    FOR VALUES FROM ('2015-01-01') TO ('2016-01-01');
CREATE TABLE IF NOT EXISTS bars_daily_2016 PARTITION OF bars_daily
    FOR VALUES FROM ('2016-01-01') TO ('2017-01-01');
CREATE TABLE IF NOT EXISTS bars_daily_2017 PARTITION OF bars_daily
    FOR VALUES FROM ('2017-01-01') TO ('2018-01-01');
CREATE TABLE IF NOT EXISTS bars_daily_2018 PARTITION OF bars_daily
    FOR VALUES FROM ('2018-01-01') TO ('2019-01-01');
CREATE TABLE IF NOT EXISTS bars_daily_2019 PARTITION OF bars_daily
    FOR VALUES FROM ('2019-01-01') TO ('2020-01-01');
CREATE TABLE IF NOT EXISTS bars_daily_2020 PARTITION OF bars_daily
    FOR VALUES FROM ('2020-01-01') TO ('2021-01-01');
CREATE TABLE IF NOT EXISTS bars_daily_2021 PARTITION OF bars_daily
    FOR VALUES FROM ('2021-01-01') TO ('2022-01-01');
CREATE TABLE IF NOT EXISTS bars_daily_2022 PARTITION OF bars_daily
    FOR VALUES FROM ('2022-01-01') TO ('2023-01-01');
CREATE TABLE IF NOT EXISTS bars_daily_2023 PARTITION OF bars_daily
    FOR VALUES FROM ('2023-01-01') TO ('2024-01-01');
CREATE TABLE IF NOT EXISTS bars_daily_2024 PARTITION OF bars_daily
    FOR VALUES FROM ('2024-01-01') TO ('2025-01-01');
CREATE TABLE IF NOT EXISTS bars_daily_2025 PARTITION OF bars_daily
    FOR VALUES FROM ('2025-01-01') TO ('2026-01-01');
CREATE TABLE IF NOT EXISTS bars_daily_2026 PARTITION OF bars_daily
    FOR VALUES FROM ('2026-01-01') TO ('2027-01-01');
CREATE TABLE IF NOT EXISTS bars_daily_2027 PARTITION OF bars_daily
    FOR VALUES FROM ('2027-01-01') TO ('2028-01-01');
CREATE TABLE IF NOT EXISTS bars_daily_2028 PARTITION OF bars_daily
    FOR VALUES FROM ('2028-01-01') TO ('2029-01-01');
CREATE TABLE IF NOT EXISTS bars_daily_2029 PARTITION OF bars_daily
    FOR VALUES FROM ('2029-01-01') TO ('2030-01-01');
CREATE TABLE IF NOT EXISTS bars_daily_2030 PARTITION OF bars_daily
    FOR VALUES FROM ('2030-01-01') TO ('2031-01-01');

-- R-16.4.a: RLS is NOT inherited by partitions. A policy on the parent applies
-- only to queries that name the parent; `SELECT * FROM bars_daily_2026` bypasses
-- it entirely. Every partition therefore needs its own default-deny, or the
-- parent's protection is decorative.
--
-- Found by tests/integration/test_migrations.py::test_row_level_security_is_
-- enabled_on_every_table, which walks pg_class rather than trusting the DDL.
DO $$
DECLARE
    part text;
BEGIN
    FOR part IN
        SELECT c.relname
        FROM pg_class c
        JOIN pg_inherits i ON i.inhrelid = c.oid
        JOIN pg_class parent ON parent.oid = i.inhparent
        WHERE parent.relname = 'bars_daily'
    LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', part);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', part);
    END LOOP;
END $$;

-- Stage A reads a recent window across the whole universe, so the partition's
-- own (symbol, session_date) primary key is not enough: a date-leading index
-- serves the "every symbol, last 20 sessions" scan.
CREATE INDEX IF NOT EXISTS bars_daily_session_date_idx
    ON bars_daily (session_date, symbol);

COMMIT;
