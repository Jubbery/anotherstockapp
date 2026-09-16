-- 0003_data_platform.sql
--
-- The data platform (MASTER_SPEC §6). Everything downstream is a function of
-- this being right, which is why §20.2's acceptance criteria are deliberately
-- harsh and why Phase 1 is expected to take longer than it "should".
--
-- Two design decisions are load-bearing and visible in the DDL:
--
--   1. Prices are stored RAW (R-6.4.d). Adjustment is computed at read time, as
--      of a date, by libs/atlas_core/pit/adjustment.py. Storing adjusted prices
--      means every split silently rewrites history.
--
--   2. Only DAILY bars live in Postgres. Minute bars for ~8,000 symbols are
--      ~786M rows/year (§6.3); they live as Parquet in Supabase Storage, indexed
--      by bar_files, and are read with DuckDB. bars_minute_hot holds the current
--      session only and is archived nightly.

BEGIN;

-- ===========================================================================
-- Reference
-- ===========================================================================

CREATE TABLE IF NOT EXISTS symbols (
    symbol          text PRIMARY KEY,
    name            text,
    exchange        text,
    asset_class     text        NOT NULL DEFAULT 'us_equity',
    security_type   text,                       -- common stock | etf | adr | ...
    sector          text,
    listed_at       date,
    -- R-6.4.c: delisted symbols are NEVER deleted, and neither are their bars.
    -- Deleting them reintroduces survivorship bias through the back door.
    delisted_at     date,
    first_seen_at   timestamptz NOT NULL DEFAULT now(),
    last_seen_at    timestamptz NOT NULL DEFAULT now()
);

COMMENT ON COLUMN symbols.delisted_at IS
    'R-6.4.c. Set, never deleted. A universe with no delistings is the signature '
    'of survivorship bias.';

-- R-6.4.b: the tradeable universe as it stood on each date, INCLUDING symbols
-- that later delisted. Backtests build the universe for date D from the snapshot
-- taken on D, never from today''s asset list.
CREATE TABLE IF NOT EXISTS universe_snapshots (
    as_of           date        NOT NULL,
    symbol          text        NOT NULL REFERENCES symbols(symbol),
    tradable        boolean     NOT NULL,
    shortable       boolean     NOT NULL,
    easy_to_borrow  boolean     NOT NULL,
    marginable      boolean     NOT NULL,
    fractionable    boolean     NOT NULL DEFAULT false,
    -- Denormalised from symbols so a snapshot is self-describing: reading it
    -- must not require a join that reflects today's state.
    delisted_at     date,
    PRIMARY KEY (as_of, symbol)
);

CREATE INDEX IF NOT EXISTS universe_snapshots_symbol_idx
    ON universe_snapshots (symbol, as_of DESC);

-- R-6.4.a: effective_at is when the fact became true in the world; knowledge_at
-- is when Atlas learned it. Historical queries MUST filter on knowledge_at, or
-- a backtest uses a split it could not have known about.
CREATE TABLE IF NOT EXISTS corporate_actions (
    id              bigserial PRIMARY KEY,
    symbol          text        NOT NULL,
    action_type     text        NOT NULL,
    effective_at    date        NOT NULL,
    knowledge_at    timestamptz NOT NULL,
    ratio           numeric(20,10),             -- splits: new shares per old share
    cash_amount     numeric(20,8),              -- dividends
    new_symbol      text,                       -- symbol changes, mergers
    raw             jsonb       NOT NULL,
    ingested_at     timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT corporate_actions_type_known
        CHECK (action_type IN ('split','dividend','merger','spinoff','symbol_change')),
    -- A split without a positive ratio would divide prices by zero or flip them.
    CONSTRAINT corporate_actions_split_has_ratio
        CHECK (action_type <> 'split' OR (ratio IS NOT NULL AND ratio > 0)),
    CONSTRAINT corporate_actions_dividend_has_amount
        CHECK (action_type <> 'dividend' OR cash_amount IS NOT NULL),
    -- Same action, same day, learned once.
    CONSTRAINT corporate_actions_unique
        UNIQUE (symbol, action_type, effective_at, knowledge_at)
);

CREATE INDEX IF NOT EXISTS corporate_actions_lookup_idx
    ON corporate_actions (symbol, effective_at, knowledge_at);

-- R-5.4.c: session boundaries come from here, never from hardcoded 09:30/16:00.
-- Half-days exist; a hardcoded close is a position held overnight.
CREATE TABLE IF NOT EXISTS market_calendar (
    session_date    date PRIMARY KEY,
    is_trading_day  boolean     NOT NULL,
    open_at         timestamptz,
    close_at        timestamptz,
    is_half_day     boolean     NOT NULL DEFAULT false,
    settlement_date date,

    CONSTRAINT market_calendar_times_paired
        CHECK ((is_trading_day AND open_at IS NOT NULL AND close_at IS NOT NULL)
               OR (NOT is_trading_day AND open_at IS NULL AND close_at IS NULL)),
    CONSTRAINT market_calendar_open_before_close
        CHECK (close_at IS NULL OR open_at < close_at)
);

-- ===========================================================================
-- Market data
-- ===========================================================================

-- RAW, unadjusted OHLCV (R-6.4.d). Partitioned by year: ~8,000 symbols x 252
-- sessions is ~2M rows/year, and Stage A scans one recent slice at a time.
CREATE TABLE IF NOT EXISTS bars_daily (
    symbol          text        NOT NULL,
    session_date    date        NOT NULL,
    open            numeric(20,8) NOT NULL,
    high            numeric(20,8) NOT NULL,
    low             numeric(20,8) NOT NULL,
    close           numeric(20,8) NOT NULL,
    volume          bigint      NOT NULL,
    vwap            numeric(20,8),
    trade_count     integer,
    data_feed       text        NOT NULL,       -- R-6.2.b: sip | iex, recorded per row
    ingested_at     timestamptz NOT NULL DEFAULT now(),

    -- R-6.6.b: invariants are rejects at ingest, not warnings. A bar that
    -- violates them is a vendor or parsing bug, and the feature computed over it
    -- is wrong in a way nothing downstream notices.
    CONSTRAINT bars_daily_sane CHECK (
        low <= high
        AND open  BETWEEN low AND high
        AND close BETWEEN low AND high
        AND volume >= 0
        AND (trade_count IS NULL OR trade_count >= 0)
        AND low > 0
    ),
    PRIMARY KEY (symbol, session_date)
) PARTITION BY RANGE (session_date);

COMMENT ON TABLE bars_daily IS
    'RAW unadjusted prices (R-6.4.d). Adjust at read time via atlas_core.pit.adjustment.';

-- Current session only (§6.3.1). Archived to Parquet nightly, then truncated --
-- verify the archive, then delete, never the other way round (§6.5.4).
CREATE TABLE IF NOT EXISTS bars_minute_hot (
    symbol          text        NOT NULL,
    -- R-6.4.g: BAR-OPEN convention. A bar stamped 14:31:00Z covers
    -- [14:31:00, 14:32:00). A decision at 14:31 uses the bar stamped 14:30.
    ts              timestamptz NOT NULL,
    open            numeric(20,8) NOT NULL,
    high            numeric(20,8) NOT NULL,
    low             numeric(20,8) NOT NULL,
    close           numeric(20,8) NOT NULL,
    volume          bigint      NOT NULL,
    vwap            numeric(20,8),
    trade_count     integer,
    data_feed       text        NOT NULL,
    ingested_at     timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT bars_minute_hot_sane CHECK (
        low <= high
        AND open  BETWEEN low AND high
        AND close BETWEEN low AND high
        AND volume >= 0
        AND low > 0
    ),
    -- Bars are aligned to the minute grid. An unaligned timestamp means the
    -- vendor's convention is not what we think it is.
    CONSTRAINT bars_minute_hot_aligned
        CHECK (date_trunc('minute', ts) = ts),
    PRIMARY KEY (symbol, ts)
);

-- R-6.3.b: every Parquet partition is registered with its hash and row count.
-- A reader verifies the hash before using a partition in training.
CREATE TABLE IF NOT EXISTS bar_files (
    id              bigserial PRIMARY KEY,
    storage_path    text        NOT NULL,
    session_date    date        NOT NULL,
    timeframe       text        NOT NULL DEFAULT '1Min',
    -- R-6.3.a: bars are written once, never updated. A vendor correction creates
    -- a NEW version rather than rewriting history.
    version         integer     NOT NULL DEFAULT 1,
    row_count       bigint      NOT NULL,
    symbol_count    integer     NOT NULL,
    byte_size       bigint      NOT NULL,
    content_hash    text        NOT NULL,
    min_ts          timestamptz NOT NULL,
    max_ts          timestamptz NOT NULL,
    data_feed       text        NOT NULL,
    ingest_run_id   bigint,
    verified_at     timestamptz,                -- read back and hash-checked
    created_at      timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT bar_files_counts_positive CHECK (row_count >= 0 AND byte_size > 0),
    CONSTRAINT bar_files_unique_version UNIQUE (storage_path, version)
);

-- R-6.3.a: what changed in a correction, and when we learned of it.
CREATE TABLE IF NOT EXISTS bar_revisions (
    id              bigserial PRIMARY KEY,
    symbol          text        NOT NULL,
    session_date    date        NOT NULL,
    timeframe       text        NOT NULL,
    previous_version integer    NOT NULL,
    new_version     integer     NOT NULL,
    reason          text,
    rows_changed    bigint      NOT NULL,
    knowledge_at    timestamptz NOT NULL DEFAULT now()
);

-- ===========================================================================
-- Ingest
-- ===========================================================================

-- R-6.5.a: bulk ingest checkpoints after every page so a crash resumes rather
-- than restarts. A 3-year minute backfill takes hours; restarting it is not an
-- acceptable failure mode.
CREATE TABLE IF NOT EXISTS ingest_runs (
    id              bigserial PRIMARY KEY,
    kind            text        NOT NULL,       -- bulk_daily | bulk_minute | nightly | intraday
    started_at      timestamptz NOT NULL DEFAULT now(),
    finished_at     timestamptz,
    status          text        NOT NULL DEFAULT 'running',
    data_feed       text        NOT NULL,
    rows_written    bigint      NOT NULL DEFAULT 0,
    rows_rejected   bigint      NOT NULL DEFAULT 0,
    error           text,
    git_sha         text,
    config_hash     text,

    CONSTRAINT ingest_runs_status_known
        CHECK (status IN ('running','succeeded','failed','aborted'))
);

CREATE TABLE IF NOT EXISTS ingest_checkpoints (
    id              bigserial PRIMARY KEY,
    ingest_run_id   bigint      NOT NULL REFERENCES ingest_runs(id),
    symbol_batch    text[]      NOT NULL,
    window_start    timestamptz NOT NULL,
    window_end      timestamptz NOT NULL,
    page_token      text,
    completed       boolean     NOT NULL DEFAULT false,
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ingest_checkpoints_resume_idx
    ON ingest_checkpoints (ingest_run_id, completed);

-- R-6.6.a: rejects are kept with their raw payload, not dropped. A rising reject
-- rate is a leading indicator of a vendor change.
CREATE TABLE IF NOT EXISTS ingest_rejects (
    id              bigserial PRIMARY KEY,
    ingest_run_id   bigint      REFERENCES ingest_runs(id),
    occurred_at     timestamptz NOT NULL DEFAULT now(),
    symbol          text,
    reason          text        NOT NULL,
    raw             jsonb       NOT NULL
);

CREATE INDEX IF NOT EXISTS ingest_rejects_recent_idx
    ON ingest_rejects (occurred_at DESC);

-- ===========================================================================
-- Data quality gate (§6.7)
-- ===========================================================================

-- R-6.7.a: a BLOCK result prevents the engine leaving WARMUP. There is no
-- override flag; fixing the data is the only path forward.
CREATE TABLE IF NOT EXISTS data_quality_runs (
    id              bigserial PRIMARY KEY,
    as_of           date        NOT NULL,
    ran_at          timestamptz NOT NULL DEFAULT now(),
    result          text        NOT NULL,
    checks          jsonb       NOT NULL,
    duration_ms     integer,

    CONSTRAINT data_quality_result_known CHECK (result IN ('pass','warn','block'))
);

CREATE INDEX IF NOT EXISTS data_quality_runs_as_of_idx
    ON data_quality_runs (as_of DESC, ran_at DESC);

-- ===========================================================================
-- RLS on every table (R-16.4.a). No policies: default deny stands.
-- ===========================================================================

DO $$
DECLARE
    t text;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'symbols','universe_snapshots','corporate_actions','market_calendar',
        'bars_daily','bars_minute_hot','bar_files','bar_revisions',
        'ingest_runs','ingest_checkpoints','ingest_rejects','data_quality_runs'
    ] LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    END LOOP;
END $$;

COMMIT;
