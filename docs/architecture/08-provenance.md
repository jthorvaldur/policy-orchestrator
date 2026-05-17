# Provenance & Fact Validation

## Confidence Hierarchy

Every fact in the system carries a confidence level based on its source:

| Level | Rank | Source Examples | Legal Weight |
|-------|------|----------------|-------------|
| **verified** | 5 | Bank CSV, court stamp, tax return, public record | Dispositive |
| **documented** | 4 | Signed letter, sworn declaration, notarized doc | Strong |
| **asserted** | 3 | Email claim, text message, oral statement | Rebuttable |
| **inferred** | 2 | Calculated from other facts, timeline deduction | Supporting |
| **disputed** | 1 | Contradicted by equal/higher confidence source | Attacked |

**Rule:** Never present an asserted fact as verified. Always cite source and level.

## Fact Lifecycle

```
Discovery → Log → Validate → Link → Version → Supersede
```

### 1. Discovery
A fact is discovered during:
- Document ingestion (LLM extraction)
- Manual review (human identifies)
- Cross-reference analysis (contradiction detector finds it)
- Financial reconciliation (gap detected)

### 2. Log
```bash
devctl log-fact \
  --fact "Respondent transferred $47K to undisclosed account on 2024-08-15" \
  --source-type financial_download \
  --confidence verified \
  --domain financial \
  --source-ref "JPM statement 2024-08, page 3" \
  --source-date 2024-08-15
```

Stored in:
- `fact_registry` Qdrant collection (embedded for semantic search)
- `facts` TimescaleDB hypertable (time-series audit trail)
- `facts` PostgreSQL table in caseledger (structured queries)

### 3. Validate
- **Corroboration:** Independent source confirms → upgrade confidence
- **Contradiction:** Conflicting source found → `fact_links` entry, downgrade confidence
- **Supersession:** New information replaces old → `superseded_by` pointer

### 4. Link
Facts connect to each other via `fact_links`:
- `contradicts` — statements conflict
- `corroborates` — independent confirmation
- `supersedes` — newer info replaces older

### 5. Version
Every change creates a `fact_versions` entry:
```json
{
  "trigger": "contradiction",
  "trigger_source": "F003",
  "old_confidence": "asserted",
  "new_confidence": "disputed",
  "note": "Contradicted by bank statement (F003, verified)"
}
```

### 6. Supersede
When a fact is replaced:
- Original fact gets `superseded_by` UUID pointing to replacement
- Original remains searchable (audit trail preserved)
- Queries default to non-superseded facts

## File-Level Provenance

**Tool:** `devctl provenance`
**Storage:** SQLite at `~/.local/share/devctl/provenance.db`

### What It Tracks

Every generated file records:
- What inputs were used to create it
- What script/tool generated it
- What parameters were used
- How to recreate it (exact command)
- SHA256 hashes of both inputs and outputs

### Recording Provenance

Scripts write `.provenance/build.jsonl` entries:
```json
{
  "generator": "embed_incremental.py",
  "inputs": ["sdata/md/email_20240815.md"],
  "input_hashes": ["sha256:abc123..."],
  "outputs": ["collection:legal_docs_v2/point:def456"],
  "output_hashes": ["sha256:789..."],
  "parameters": {"model": "bge-base-en-v1.5", "chunk_size": 512},
  "timestamp": "2026-05-15T14:30:00",
  "duration_ms": 450,
  "recreate_cmd": "uv run python -m src.scripts.embed_incremental"
}
```

### Querying Provenance

```bash
devctl provenance show sdata/md/email_20240815.md
# → Shows: who created it, when, from what source, hash

devctl provenance stale --repo=div_legal
# → Shows: outputs whose inputs have changed since generation

devctl provenance rebuild
# → Rebuilds SQLite index from all .provenance/build.jsonl files
```

### Lineage Chains

```
Raw email (Gmail) → EML file → eml_extractor.py → Markdown → embed_incremental.py → Qdrant point
     └── Each step recorded with input/output hashes, enabling full trace
```

## TimescaleDB as Provenance Timeline

The `facts` hypertable in TimescaleDB provides a temporal view:

```sql
-- All facts logged in last 7 days
SELECT fact, confidence, source_type, logged_at
FROM facts
WHERE logged_at > NOW() - INTERVAL '7 days'
ORDER BY logged_at DESC;

-- Facts that were superseded (story changed)
SELECT f1.fact AS original, f2.fact AS replacement, f1.logged_at
FROM facts f1
JOIN facts f2 ON f1.superseded_by = f2.id
ORDER BY f1.logged_at;

-- Ground truth facts (bank statements, court records)
SELECT fact, source_ref, source_date
FROM facts
WHERE is_ground_truth = TRUE
ORDER BY source_date;
```

## Content-Addressed Storage

The `file_registry` table uses SHA256 as primary key:

```sql
-- Same content, multiple paths? → detected as duplicate
SELECT content_hash, array_agg(file_path) AS locations
FROM file_registry
GROUP BY content_hash
HAVING COUNT(*) > 1;

-- Trace file across repos
SELECT repo, file_path, created_at
FROM file_registry
WHERE content_hash = 'sha256:abc123...';
```

## Source Types

| Type | Confidence Ceiling | Examples |
|------|-------------------|----------|
| `financial_download` | verified | Bank CSV, brokerage statement |
| `court_document` | verified | Court orders, filed motions |
| `tax_document` | verified | Tax returns, W-2s |
| `email` | asserted | Email communications |
| `text_message` | asserted | WhatsApp, Signal, iMessage |
| `conversation` | asserted | Phone calls, meetings |
| `medical_record` | documented | Doctor notes, prescriptions |
| `legal_filing` | documented | Declarations, affidavits |
| `calculation` | inferred | Derived amounts, timelines |
| `public_record` | verified | Property records, corporate filings |
| `photograph` | documented | Screenshots, photos |

## AWS Scaling

| Local | AWS |
|-------|-----|
| SQLite provenance | DynamoDB (content_hash as partition key) |
| TimescaleDB facts | RDS TimescaleDB or Aurora + pg_timescaledb |
| Qdrant fact_registry | Qdrant Cloud (managed) |
| File hashes | S3 + DynamoDB metadata |
