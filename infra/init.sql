-- Policy Orchestrator — TimescaleDB Schema
-- Runs once on first container start via docker-entrypoint-initdb.d
-- Port: 5434 | DB: orchestrator | User: orchestrator

CREATE EXTENSION IF NOT EXISTS timescaledb;

-- ═══════════════════════════════════════════════════════════════════
-- Layer 4a: Financial TimeSeries — tick-level trades
-- ═══════════════════════════════════════════════════════════════════

CREATE TABLE trades (
    time        TIMESTAMPTZ NOT NULL,
    exchange    TEXT NOT NULL,
    symbol      TEXT NOT NULL,
    price       NUMERIC NOT NULL,
    quantity    NUMERIC NOT NULL,
    quote_qty   NUMERIC,
    side        TEXT,
    is_maker    BOOLEAN,
    trade_id    BIGINT,
    wallet      TEXT,           -- HL only
    closed_pnl  NUMERIC,        -- HL only
    fee         NUMERIC,        -- HL only
    direction   TEXT,           -- HL only
    source_file TEXT
);

SELECT create_hypertable('trades', 'time', chunk_time_interval => INTERVAL '1 day');
CREATE INDEX idx_trades_sym_time ON trades (symbol, time DESC);
CREATE INDEX idx_trades_exch_time ON trades (exchange, time DESC);
CREATE INDEX idx_trades_wallet ON trades (wallet, time DESC) WHERE wallet IS NOT NULL;

-- ═══════════════════════════════════════════════════════════════════
-- Layer 4a: Financial TimeSeries — aggregated bars
-- ═══════════════════════════════════════════════════════════════════

CREATE TABLE bars (
    time        TIMESTAMPTZ NOT NULL,
    exchange    TEXT NOT NULL,
    symbol      TEXT NOT NULL,
    interval    TEXT NOT NULL,
    open        NUMERIC,
    high        NUMERIC,
    low         NUMERIC,
    close       NUMERIC,
    volume      NUMERIC,
    trade_count INT,
    vwap        NUMERIC
);

SELECT create_hypertable('bars', 'time', chunk_time_interval => INTERVAL '1 month');
CREATE UNIQUE INDEX idx_bars_unique ON bars (exchange, symbol, interval, time);

-- ═══════════════════════════════════════════════════════════════════
-- Layer 4b: Event TimeSeries
-- ═══════════════════════════════════════════════════════════════════

CREATE TABLE events (
    id            UUID DEFAULT gen_random_uuid(),
    time          TIMESTAMPTZ NOT NULL,
    event_type    TEXT NOT NULL,
    domain        TEXT,
    title         TEXT,
    description   TEXT,
    content_hash  TEXT,
    session_id    TEXT,
    fact_ids      UUID[],
    file_path     TEXT,
    source_type   TEXT,
    confidence    TEXT DEFAULT 'documented',
    repo          TEXT
);

SELECT create_hypertable('events', 'time');
CREATE INDEX idx_events_type ON events (event_type, time DESC);
CREATE INDEX idx_events_domain ON events (domain, time DESC);
CREATE INDEX idx_events_hash ON events (content_hash) WHERE content_hash IS NOT NULL;

-- ═══════════════════════════════════════════════════════════════════
-- Layer 3b: Facts Timeline
-- ═══════════════════════════════════════════════════════════════════

CREATE TABLE facts (
    id              UUID DEFAULT gen_random_uuid(),
    fact            TEXT NOT NULL,
    domain          TEXT NOT NULL,
    confidence      TEXT NOT NULL,
    confidence_rank INT NOT NULL,
    source_type     TEXT,
    source_ref      TEXT,
    source_date     DATE,
    content_hash    TEXT,
    session_id      TEXT,
    qdrant_point_id UUID,
    logged_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    superseded_by   UUID,
    is_ground_truth BOOLEAN DEFAULT FALSE
);

SELECT create_hypertable('facts', 'logged_at');
CREATE INDEX idx_facts_domain ON facts (domain, logged_at DESC);
CREATE INDEX idx_facts_confidence ON facts (confidence_rank, logged_at DESC);

-- ═══════════════════════════════════════════════════════════════════
-- Layer 4c: File Registry — content-addressed file index
-- ═══════════════════════════════════════════════════════════════════

CREATE TABLE file_registry (
    content_hash  TEXT PRIMARY KEY,
    file_path     TEXT NOT NULL,
    file_name     TEXT NOT NULL,
    file_size     BIGINT,
    mime_type     TEXT,
    created_at    TIMESTAMPTZ,
    repo          TEXT,
    storage_uri   TEXT
);

CREATE INDEX idx_files_repo ON file_registry (repo);
