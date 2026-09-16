-- 0005_instrument_identity.sql
--
-- A ticker is not an identity. Migrations 0003/0004 used `symbol` as the primary
-- key throughout, which assumes a ticker names one company for all time. It does
-- not, and the two failure modes point in opposite directions:
--
--   * A TICKER CHANGE splits one company across two keys. FB became META in June
--     2022. Keyed by symbol, a 60-day feature window spanning that date sees two
--     securities each with a 30-day history, and the momentum and volatility
--     features computed over them are wrong.
--
--   * A TICKER REUSE joins two companies under one key. When a company delists,
--     its ticker returns to the pool and is often reassigned. Keyed by symbol,
--     the dead company's price history and the new company's are one continuous
--     series -- with a discontinuity at the handover that looks exactly like a
--     tradeable gap.
--
-- Neither produces an error. Both produce features, and the second produces
-- *attractive* features, which is the signature of the bug class §9.1 exists to
-- catch.
--
-- This migration introduces a surrogate key (`instruments.instrument_id`) and a
-- point-in-time mapping from ticker to instrument (`symbol_mappings`), and
-- repoints every table that carried a bare symbol.
--
-- Prompted by the Alpaca MCP tool schema, which exposes an `asof` parameter for
-- "point-in-time symbol mapping ... useful for backtesting with historical
-- ticker changes" -- i.e. the vendor considers this a real hazard too.
--
-- Spec: MASTER_SPEC R-6.4.h, §6.4.5, Appendix C.

BEGIN;

-- Required for the exclusion constraint below: it mixes an equality test on a
-- text column with an overlap test on a range, which plain GiST cannot index.
CREATE EXTENSION IF NOT EXISTS btree_gist;

-- ===========================================================================
-- Guard: refuse to rekey bar tables that already hold data
-- ===========================================================================
--
-- Three states, and they need different answers:
--
--   * Already migrated (instrument_id present) -> no-op, succeed. A retried
--     deploy must not fail.
--   * Not migrated, tables empty            -> migrate. The normal path.
--   * Not migrated, tables populated        -> refuse. Rekeying live bars is a
--     data migration with a verification step, and a silent partial rekey would
--     leave half the history unreachable.

DO $$
DECLARE
    already_migrated boolean;
    daily_rows bigint;
    minute_rows bigint;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'bars_daily' AND column_name = 'instrument_id'
    ) INTO already_migrated;

    IF already_migrated THEN
        RETURN;
    END IF;

    EXECUTE 'SELECT count(*) FROM bars_daily' INTO daily_rows;
    EXECUTE 'SELECT count(*) FROM bars_minute_hot' INTO minute_rows;

    IF daily_rows > 0 OR minute_rows > 0 THEN
        RAISE EXCEPTION
            'bars_daily has % rows and bars_minute_hot has %. Rekeying populated bar '
            'tables needs a verified data migration -- see MASTER_SPEC §6.4.5.',
            daily_rows, minute_rows;
    END IF;
END $$;

-- ===========================================================================
-- instruments -- one row per security, stable across every ticker it ever wore
-- ===========================================================================

CREATE TABLE IF NOT EXISTS instruments (
    instrument_id   bigserial PRIMARY KEY,

    -- Convenience for humans reading a query result. NOT a key, and NOT safe to
    -- join on: it is whatever ticker the instrument wears most recently.
    primary_symbol  text        NOT NULL,

    name            text,
    exchange        text,
    asset_class     text        NOT NULL DEFAULT 'us_equity',
    security_type   text,
    sector          text,

    -- The vendor's own stable identifier (Alpaca issues a UUID per asset).
    -- Recorded but not relied on: a second broker would have a different one,
    -- and the surrogate key is ours.
    vendor_asset_id text UNIQUE,

    listed_at       date,
    -- R-6.4.c: set, never deleted, and neither are the instrument's bars.
    delisted_at     date,

    first_seen_at   timestamptz NOT NULL DEFAULT now(),
    last_seen_at    timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT instruments_delisted_after_listed
        CHECK (delisted_at IS NULL OR listed_at IS NULL OR delisted_at >= listed_at)
);

COMMENT ON TABLE instruments IS
    'One row per security. instrument_id is stable across ticker changes and is '
    'never reused, which symbol is not (R-6.4.h).';

COMMENT ON COLUMN instruments.primary_symbol IS
    'Display convenience only. Never join on this -- use symbol_mappings.';

-- ===========================================================================
-- symbol_mappings -- which ticker pointed at which instrument, when
-- ===========================================================================

CREATE TABLE IF NOT EXISTS symbol_mappings (
    id              bigserial PRIMARY KEY,
    symbol          text        NOT NULL,
    instrument_id   bigint      NOT NULL REFERENCES instruments(instrument_id),

    -- Half-open [valid_from, valid_until). NULL valid_until means "still current",
    -- which daterange treats as unbounded above.
    valid_from      date        NOT NULL,
    valid_until     date,

    -- R-6.4.a. A ticker change is announced before it takes effect; a backtest
    -- run before the announcement must resolve the old ticker.
    knowledge_at    timestamptz NOT NULL,
    source          text        NOT NULL DEFAULT 'ingest',
    created_at      timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT symbol_mappings_range_sane
        CHECK (valid_until IS NULL OR valid_until > valid_from),

    -- A symbol may point at only one instrument at a time. Overlapping ranges
    -- for one ticker are ambiguous, and the ambiguity must be refused at write
    -- time: resolving it at read time would mean picking one silently.
    CONSTRAINT symbol_mappings_no_overlapping_symbol
        EXCLUDE USING gist (
            symbol WITH =,
            daterange(valid_from, valid_until, '[)') WITH &&
        ),

    -- And an instrument wears one ticker at a time. Dual-class shares (GOOG and
    -- GOOGL) are separate instruments, so this does not conflict with them.
    CONSTRAINT symbol_mappings_no_overlapping_instrument
        EXCLUDE USING gist (
            instrument_id WITH =,
            daterange(valid_from, valid_until, '[)') WITH &&
        )
);

CREATE INDEX IF NOT EXISTS symbol_mappings_resolve_idx
    ON symbol_mappings (symbol, valid_from DESC);
CREATE INDEX IF NOT EXISTS symbol_mappings_reverse_idx
    ON symbol_mappings (instrument_id, valid_from DESC);

COMMENT ON TABLE symbol_mappings IS
    'Point-in-time ticker -> instrument. Resolve with as-of semantics; never '
    'assume today''s mapping held in the past (R-6.4.h).';

-- ===========================================================================
-- Backfill from the old symbols table
-- ===========================================================================
--
-- One instrument per existing symbol, with a mapping open from the listing date
-- (or an early sentinel when unknown). This is correct for every symbol that has
-- never changed ticker, which is the overwhelming majority; genuine historical
-- changes are reconstructed by ingest from corporate actions of type
-- 'symbol_change', which is why that action type already exists in 0003.

DO $$
BEGIN
    IF to_regclass('public.symbols') IS NULL THEN
        RETURN;  -- already migrated
    END IF;

    INSERT INTO instruments (
        primary_symbol, name, exchange, asset_class, security_type, sector,
        listed_at, delisted_at, first_seen_at, last_seen_at
    )
    SELECT symbol, name, exchange, asset_class, security_type, sector,
           listed_at, delisted_at, first_seen_at, last_seen_at
    FROM symbols
    ON CONFLICT DO NOTHING;

    INSERT INTO symbol_mappings
        (symbol, instrument_id, valid_from, valid_until, knowledge_at, source)
    SELECT s.symbol,
           i.instrument_id,
           COALESCE(s.listed_at, DATE '1900-01-01'),
           s.delisted_at,
           s.first_seen_at,
           'migration_0005'
    FROM symbols s
    JOIN instruments i ON i.primary_symbol = s.symbol
    ON CONFLICT DO NOTHING;
END $$;

-- ===========================================================================
-- Repoint the dependent tables
-- ===========================================================================

-- --- universe_snapshots ---------------------------------------------------
ALTER TABLE universe_snapshots
    ADD COLUMN IF NOT EXISTS instrument_id bigint REFERENCES instruments(instrument_id);

UPDATE universe_snapshots u
SET instrument_id = m.instrument_id
FROM symbol_mappings m
WHERE m.symbol = u.symbol
  AND u.instrument_id IS NULL
  AND daterange(m.valid_from, m.valid_until, '[)') @> u.as_of;

ALTER TABLE universe_snapshots
    DROP CONSTRAINT IF EXISTS universe_snapshots_symbol_fkey;
ALTER TABLE universe_snapshots ALTER COLUMN instrument_id SET NOT NULL;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_index i
        JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
        WHERE i.indrelid = 'universe_snapshots'::regclass
          AND i.indisprimary AND a.attname = 'symbol'
    ) THEN
        ALTER TABLE universe_snapshots DROP CONSTRAINT universe_snapshots_pkey;
        ALTER TABLE universe_snapshots ADD PRIMARY KEY (as_of, instrument_id);
    END IF;
END $$;

-- The ticker as it stood on as_of, kept deliberately: it is the PIT ticker, and
-- reconstructing it later would require the very lookup this column records.
COMMENT ON COLUMN universe_snapshots.symbol IS
    'The ticker in effect on as_of. Provenance, not a key (R-6.4.h).';

-- --- corporate_actions ----------------------------------------------------
ALTER TABLE corporate_actions
    ADD COLUMN IF NOT EXISTS instrument_id bigint REFERENCES instruments(instrument_id);

UPDATE corporate_actions c
SET instrument_id = m.instrument_id
FROM symbol_mappings m
WHERE m.symbol = c.symbol
  AND c.instrument_id IS NULL
  AND daterange(m.valid_from, m.valid_until, '[)') @> c.effective_at;

CREATE INDEX IF NOT EXISTS corporate_actions_instrument_idx
    ON corporate_actions (instrument_id, effective_at, knowledge_at);

-- --- bars -----------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'bars_daily' AND column_name = 'symbol'
    ) THEN
        ALTER TABLE bars_daily ADD COLUMN instrument_id bigint;
        ALTER TABLE bars_daily RENAME COLUMN symbol TO symbol_as_reported;
        ALTER TABLE bars_daily ALTER COLUMN instrument_id SET NOT NULL;
        ALTER TABLE bars_daily DROP CONSTRAINT bars_daily_pkey;
        ALTER TABLE bars_daily ADD PRIMARY KEY (instrument_id, session_date);
    END IF;
END $$;

COMMENT ON COLUMN bars_daily.symbol_as_reported IS
    'The ticker the vendor used for this bar. Provenance only -- join on '
    'instrument_id, or a ticker change splits one company''s history in two.';

DROP INDEX IF EXISTS bars_daily_session_date_idx;
CREATE INDEX bars_daily_session_date_idx
    ON bars_daily (session_date, instrument_id);

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'bars_minute_hot' AND column_name = 'symbol'
    ) THEN
        ALTER TABLE bars_minute_hot ADD COLUMN instrument_id bigint;
        ALTER TABLE bars_minute_hot RENAME COLUMN symbol TO symbol_as_reported;
        ALTER TABLE bars_minute_hot ALTER COLUMN instrument_id SET NOT NULL;
        ALTER TABLE bars_minute_hot DROP CONSTRAINT bars_minute_hot_pkey;
        ALTER TABLE bars_minute_hot ADD PRIMARY KEY (instrument_id, ts);
    END IF;
END $$;

-- --- retire the old table -------------------------------------------------
DROP TABLE IF EXISTS symbols;

-- ===========================================================================
-- RLS (R-16.4.a)
-- ===========================================================================

ALTER TABLE instruments      ENABLE ROW LEVEL SECURITY;
ALTER TABLE instruments      FORCE  ROW LEVEL SECURITY;
ALTER TABLE symbol_mappings  ENABLE ROW LEVEL SECURITY;
ALTER TABLE symbol_mappings  FORCE  ROW LEVEL SECURITY;

COMMIT;
