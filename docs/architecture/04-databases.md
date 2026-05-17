# Databases

## Qdrant Vector Database

### Instance 1: Port 6333 (Main — div_legal, contacts, policy-orchestrator)

| Collection | Points | Vector | Data | Sensitivity |
|-----------|--------|--------|------|-------------|
| `legal_docs_v2` | 379K | Hybrid (768d + sparse) | Emails, PDFs, filings, bank statements | High |
| `claude_code_sessions` | 96K | Hybrid | All Claude Code conversations (all repos) | Medium |
| `whatsapp_chats` | 19K | Hybrid | WhatsApp + Signal messages | High |
| `openai_chats` | 5.5K | Hybrid | ChatGPT exports (1,709 convos) | Medium |
| `contacts` | 3.4K | Hybrid | macOS + WhatsApp + LinkedIn contacts | Medium |
| `claude_chats_ai` | 2K | Hybrid | Claude.ai web conversations | Medium |
| `concepts` | 444 | Hybrid | Strategic concepts, learnings | Low |
| `directives` | 270 | Hybrid | System directives | Low |
| `fact_registry` | 167 | Hybrid | Classified facts with confidence | High |
| `feedback_events` | 3 | Hybrid | Agent calibration notes | Low |

**Config:** HNSW (m=16, ef_construct=200), INT8 scalar quantization, COSINE distance

### Instance 2: Port 7333 (CaseLedger — dedicated)

| Collection | Points | Vector | Data |
|-----------|--------|--------|------|
| `case_docs` | 1.7M | Hybrid (768d + sparse) | Full legal document corpus |
| `case_facts` | 16.7K | Hybrid | Extracted case facts |

### Named Vectors Schema (Hybrid Collections)

```json
{
  "vectors": {
    "dense": {
      "size": 768,
      "distance": "Cosine"
    },
    "sparse": {
      "index": { "on_disk": false }
    }
  }
}
```

### Payload Schema (legal_docs_v2 / case_docs)

```json
{
  "doc_id": "29202ad1",
  "chunk_index": 3,
  "source_path": "sdata/md/20240904_retainer.md",
  "source_type": "pdf",
  "title": "Pre-Decree Retainer Agreement",
  "date": "2024-09-04",
  "topics": ["legal", "financial"],
  "content_preview": "first 200 chars...",
  "text": "full chunk text (up to 2048 chars)"
}
```

### Payload Schema (claude_code_sessions)

```json
{
  "session_id": "abc123-def456",
  "project": "-Users-jthor-GitHub-caseledger",
  "repo": "caseledger",
  "role": "assistant",
  "turn_index": 42,
  "chunk_index": 0,
  "date": "2026-05-15",
  "content_preview": "first 200 chars...",
  "text": "full chunk text"
}
```

### Payload Schema (fact_registry)

```json
{
  "fact": "Conniff billed $15K for unperformed work",
  "source_type": "email",
  "confidence": "asserted",
  "confidence_rank": 3,
  "domain": "financial",
  "source_ref": "Email from Conniff, 2025-03-15",
  "source_date": "2025-03-15",
  "claimed_by": "Joel Thorarinson",
  "contradicts": null,
  "repo": "div_legal",
  "logged_at": "2026-05-10T14:30:00"
}
```

## TimescaleDB (Port 5434)

**Database:** `orchestrator` | **User:** `orchestrator`

### Hypertables

```sql
-- Financial tick data
CREATE TABLE trades (
    time        TIMESTAMPTZ NOT NULL,
    exchange    TEXT NOT NULL,
    symbol      TEXT NOT NULL,
    price       NUMERIC NOT NULL,
    quantity    NUMERIC NOT NULL,
    quote_qty   NUMERIC,
    side        TEXT,          -- buy/sell
    is_maker    BOOLEAN,
    trade_id    TEXT,
    wallet      TEXT,
    closed_pnl  NUMERIC,
    fee         NUMERIC,
    direction   TEXT,
    source_file TEXT
);
SELECT create_hypertable('trades', 'time');

-- OHLCV bars
CREATE TABLE bars (
    time        TIMESTAMPTZ NOT NULL,
    exchange    TEXT NOT NULL,
    symbol      TEXT NOT NULL,
    interval    TEXT NOT NULL,  -- 1m, 5m, 1h, 1d
    open        NUMERIC, high NUMERIC, low NUMERIC, close NUMERIC,
    volume      NUMERIC,
    trade_count INTEGER,
    vwap        NUMERIC
);
SELECT create_hypertable('bars', 'time', chunk_time_interval => INTERVAL '1 month');

-- General events (filings, meetings, deadlines)
CREATE TABLE events (
    id           UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    time         TIMESTAMPTZ NOT NULL,
    event_type   TEXT NOT NULL,
    domain       TEXT,
    title        TEXT,
    description  TEXT,
    content_hash TEXT,
    session_id   TEXT,
    fact_ids     UUID[],
    file_path    TEXT,
    source_type  TEXT,
    confidence   TEXT,
    repo         TEXT
);
SELECT create_hypertable('events', 'time');

-- Facts timeline (audit trail, supersession tracking)
CREATE TABLE facts (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    fact            TEXT NOT NULL,
    domain          TEXT,
    confidence      TEXT,
    confidence_rank INTEGER,  -- verified=5, documented=4, asserted=3, inferred=2, disputed=1
    source_type     TEXT,
    source_ref      TEXT,
    source_date     DATE,
    content_hash    TEXT,
    session_id      TEXT,
    qdrant_point_id UUID,
    logged_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    superseded_by   UUID REFERENCES facts(id),
    is_ground_truth BOOLEAN DEFAULT FALSE
);
SELECT create_hypertable('facts', 'logged_at');

-- Content-addressed file registry
CREATE TABLE file_registry (
    content_hash TEXT PRIMARY KEY,  -- sha256:hex
    file_path    TEXT NOT NULL,
    file_name    TEXT,
    file_size    BIGINT,
    mime_type    TEXT,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    repo         TEXT,
    storage_uri  TEXT
);
```

## PostgreSQL (Port 5433 — CaseLedger)

**Database:** `caseledger` | **User:** `caseledger`

### Core Tables

```sql
-- Extracted evidence with confidence
CREATE TABLE facts (
    id          TEXT PRIMARY KEY,  -- F001, F002...
    statement   TEXT NOT NULL,
    date        TEXT,
    confidence  TEXT CHECK (confidence IN ('low','medium','high','disputed')),
    category    TEXT,  -- communication, financial, timeline, testimony, evidence, custody, property
    status      TEXT,  -- asserted, corroborated, disputed, resolved, retracted
    content_hash TEXT UNIQUE,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Provenance: which document + chunk produced this fact
CREATE TABLE fact_sources (
    id              SERIAL PRIMARY KEY,
    fact_id         TEXT REFERENCES facts(id),
    doc_id          TEXT,
    chunk_id        TEXT,  -- Qdrant point UUID
    source_filename TEXT,
    chunk_index     INTEGER,
    extraction_method TEXT  -- auto, manual, corroboration
);

-- Semantic relationships between facts
CREATE TABLE fact_links (
    id         SERIAL PRIMARY KEY,
    fact_a_id  TEXT REFERENCES facts(id),
    fact_b_id  TEXT REFERENCES facts(id),
    link_type  TEXT,  -- contradicts, corroborates, supersedes
    evidence_note TEXT,
    UNIQUE(fact_a_id, fact_b_id, link_type)
);

-- Audit trail for fact changes
CREATE TABLE fact_versions (
    id             SERIAL PRIMARY KEY,
    fact_id        TEXT REFERENCES facts(id),
    version        INTEGER,
    confidence     TEXT,
    status         TEXT,
    trigger        TEXT,  -- initial_extraction, corroboration, contradiction, manual_review, retraction
    trigger_source TEXT,  -- doc_id or fact_id that caused change
    note           TEXT,
    created_at     TIMESTAMPTZ DEFAULT NOW()
);

-- Case graph: typed nodes (obligations, deadlines, payments)
CREATE TABLE graph_nodes (
    id          TEXT PRIMARY KEY,
    case_id     TEXT,
    node_type   TEXT,  -- obligation, deadline, payment, filing, order, communication
    state       TEXT,  -- pending, satisfied, violated, withdrawn
    party       TEXT,
    t_created   BIGINT,  -- unix timestamp
    t_effective BIGINT,
    t_deadline  BIGINT,
    t_resolved  BIGINT,
    data        JSONB
);

-- Case graph: relationships
CREATE TABLE graph_edges (
    id            SERIAL PRIMARY KEY,
    case_id       TEXT,
    src_id        TEXT REFERENCES graph_nodes(id),
    dst_id        TEXT REFERENCES graph_nodes(id),
    label         TEXT,  -- responds_to, requires, violates, blocks, cites, contradicts, modifies
    evidence_note TEXT,
    inferred_by   TEXT  -- manual, llm, rule
);

-- Parties (people, organizations, courts)
CREATE TABLE parties (
    id             TEXT PRIMARY KEY,  -- P001, P002...
    canonical_name TEXT,
    party_type     TEXT,  -- person, organization, court, attorney
    role           TEXT,  -- petitioner, respondent, judge, witness, GAL
    case_id        TEXT,
    metadata       JSONB
);
```

## Provenance SQLite (~/.local/share/devctl/provenance.db)

```sql
-- Build artifacts: what generated what, how to recreate
CREATE TABLE builds (
    id            TEXT PRIMARY KEY,
    repo          TEXT,
    generator     TEXT,      -- script or tool that created output
    outputs       TEXT,      -- JSON array of output paths
    output_hashes TEXT,      -- JSON array of SHA256 hashes
    inputs        TEXT,      -- JSON array of input paths
    input_hashes  TEXT,
    parameters    TEXT,      -- JSON of build params
    timestamp     TEXT,
    duration_ms   INTEGER,
    recreate_cmd  TEXT,      -- command to reproduce
    items         INTEGER
);

-- Git-tracked files with content addressing
CREATE TABLE files (
    content_hash TEXT PRIMARY KEY,
    file_path    TEXT,
    repo         TEXT,
    first_seen   TEXT,
    last_modified TEXT,
    file_size    INTEGER,
    mime_type    TEXT,
    created_by   TEXT,  -- git commit or session_id
    git_commit   TEXT
);

-- Input → output derivation chains
CREATE TABLE file_lineage (
    output_hash TEXT,
    input_hash  TEXT,
    transform   TEXT  -- description of derivation
);
```
