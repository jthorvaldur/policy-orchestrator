# Data Flow

## End-to-End Pipeline

```
Raw Source → Extract → Normalize → Dedup → Chunk → Embed → Store → Analyze → Output
                                                                        ↓
                                                              Re-inject → Concepts DB
```

## Phase 1: Acquisition (div_legal + contacts)

### Email (Gmail IMAP)
```
Gmail API/IMAP → imap_sync.py → EML files → eml_extractor.py → Markdown + metadata
                 (UID tracking)                                  (date, parties, topics)
```
- 2 Gmail accounts, 55K+ emails synced
- Incremental by UID (state: `sdata/imap_sync_state.json`)
- Attachments extracted to `sdata/attachments/` with vision summary
- Repo: `div_legal/src/scripts/imap_sync.py`

### WhatsApp
```
macOS ChatStorage.sqlite → contacts index --chats → JSON → whatsapp_extractor.py → Markdown
                           (live SQLite access)
```
- 135 chats, 41K messages
- Timestamps, sender, multi-line messages preserved
- System messages filtered
- Repo: `contacts/src/contacts_organizer/extract/`, `div_legal/src/extractors/whatsapp_extractor.py`

### Signal
```
Signal Desktop DB → sigexport CLI → chat.md per contact → signal_extractor.py → Markdown
```
- 73 conversations, 50+ ingested
- Format: `[YYYY-MM-DD HH:MM:SS] Sender: message`
- Reactions/call events filtered
- Repo: `div_legal/src/extractors/signal_extractor.py`, `div_legal/src/scripts/ingest_signal.py`

### iMessage
```
macOS Messages.app → contacts extract (AppleScript) → Structured JSON → Markdown
```
- Extracted via macOS Contacts pipeline
- Part of the unified contact/communication graph
- Repo: `contacts/src/contacts_organizer/extract/applescript.py`

### Court Documents / PDFs
```
PDF files → pdf_extractor.py (PyMUPDF) → Markdown
                                          ├── Text extraction (native PDF text)
                                          ├── Encrypted PDF handling (password list)
                                          └── Page separator (---)
```
- 600+ disclosure documents, 376 bank statement PDFs
- Repo: `div_legal/src/extractors/pdf_extractor.py`

### Images / Screenshots
```
Image files → image_summarizer.py → Vision model (Gemma 4 via Ollama) → Markdown summary
```
- Formats: PNG, JPG, TIFF, WebP, BMP, GIF
- Legal-focused vision prompt
- Binary saved to `sdata/attachments/` with SHA256 hash
- Repo: `div_legal/src/processors/image_summarizer.py`

### Financial Data
```
Plaid API / OFX / Revolut CSV / IB / Gemini → bank_sync.py → Markdown + TimescaleDB
```
- Multi-currency (USD, ISK, EUR, GBP)
- Account registry: `financial/accounts.yaml`
- Repo: `div_legal/src/scripts/bank_sync.py`

## Phase 2: Processing (docvec + Ollama)

### Chunking
```
Markdown → chunk_text() → 512-token chunks (64-token overlap, paragraph-aware)
```
- Respects paragraph boundaries (`\n\n` splits)
- Short chunks get merged, long chunks get split
- Deterministic chunk boundaries for reproducibility

### Embedding (Hybrid: Dense + Sparse)
```
Chunk → docvec service (:8100) → { dense: [768 floats], sparse: {indices, values} }
        ├── Dense: BAAI/bge-base-en-v1.5 (sentence-transformers)
        └── Sparse: SPLADE++ (fastembed ONNX)
```
- Service stays warm (LaunchAgent, KeepAlive=true)
- Auto-detected by all consumers (health check on :8100)
- Fallback to in-process loading if service down
- GPU option: Vast.ai batch (150 chunks/sec vs 3-4 local)

### Deduplication
```
Content → SHA256 hash → deduplicator.py → Skip if hash exists in registry
```
- Content-addressed: same content always produces same hash
- Cross-source dedup: catches forwarded emails, duplicate scans
- Query-time dedup: content_fingerprint() in search results

### Fact Extraction
```
Document → Ollama (llama3.1:8b) → Structured facts with confidence + source
           System prompt: "Extract dated, sourced, verifiable facts..."
```
- Temperature: 0.1 (deterministic)
- Optional: Claude Opus for cross-document reasoning
- Output: fact_id, statement, date, confidence, category, status

### Topic Classification
```
Document → Ollama → Topics (communication, financial, timeline, testimony, evidence, custody, property)
```

## Phase 3: Storage

### Qdrant (Vector Search)
```
Embedded chunks → Qdrant upsert (deterministic point IDs)
                  Named vectors: { "dense": [768], "sparse": {indices, values} }
                  Payload: doc_id, source_path, date, title, text, topics, source_type
```

### PostgreSQL (Structured Facts)
```
Extracted facts → facts table (id, statement, confidence, category, status)
                  fact_sources (provenance: which doc, which chunk)
                  fact_links (contradicts, corroborates, supersedes)
                  fact_versions (audit trail: who changed what, why)
```

### TimescaleDB (Time Series)
```
Financial data → trades, bars hypertables
Events → events hypertable (type, domain, content_hash)
Facts → facts hypertable (confidence_rank, source_type, superseded_by)
Files → file_registry (content_hash PK, paths, repos)
```

## Phase 4: Analysis (caseledger)

See [06-analysis-engine.md](06-analysis-engine.md) for full details.

```
Facts + Docs + Graph → Contradiction Detector → Attack Vectors
                     → Cycle Detector → Circuit Breakers
                     → Chain Engine → Logical Proofs
                     → Consistency Metrics → Cumulative Score Timeline
                     → Financial Recon → Gap Analysis
                     → Compliance Audit → Checklist
```

## Phase 5: Output

```
Analysis results → Court PDF (WeasyPrint) + HTML Timeline + Encrypted Pages + API JSON
```

## Phase 6: Re-injection (Knowledge Loop)

```
Discoveries → devctl log-fact → fact_registry (Qdrant) + facts (TimescaleDB)
Concepts → concepts collection (Qdrant, 444 vectors)
Sessions → claude_code_sessions (96K vectors) — anonymized conversation context
Feedback → feedback_events (calibration for agent behavior)
```

## Composite Reindex (sync_all.sh)

The full 7-phase pipeline runs all the above in correct order:

```bash
cd ~/GitHub/div_legal && bash scripts/sync_all.sh
```

Phases: Preflight → Data Acquisition (parallel) → Contacts Pipeline → div_legal Pipeline → Contacts Embedding → CaseLedger → Reports

Flags: `--no-contacts`, `--no-caseledger`, `--no-embed`, `--no-signal`, `--no-whatsapp`, `--no-imap`, `--no-reports`, `--full`, `--from N`, `--dry-run`
