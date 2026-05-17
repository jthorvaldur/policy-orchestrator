# Ingestion Pipelines

## Gmail (IMAP Incremental Sync)

**Repo:** `div_legal/src/scripts/imap_sync.py`

```bash
uv run python -m src.scripts.imap_sync --embed              # sync + embed
uv run python -m src.scripts.imap_sync --since 01-Apr-2026  # since date
```

**How it works:**
1. Connects via IMAP (supports Gmail 2FA with app passwords)
2. Discovers mailbox (`[Gmail]/All Mail` or localized variant)
3. Fetches UIDs since last sync (state: `sdata/imap_sync_state.json`)
4. Downloads new messages as EML
5. Extracts: body text, headers (date, from, to, subject), attachments
6. Attachments → `sdata/attachments/` (images get vision summary via Ollama)
7. Produces markdown with frontmatter (date, parties, topics, source_type)
8. Optional `--embed` flag triggers vectorization into `legal_docs_v2`

**Config (env vars):**
```
IMAP_USER_1=joel@example.com
IMAP_PASSWORD_1=app-password-here
IMAP_USER_2=second@example.com
IMAP_PASSWORD_2=...
```

**Scale (55K+ emails across 2 accounts)**

## WhatsApp (Live SQLite)

**Repo:** `contacts/src/contacts_organizer/extract/`, `div_legal/src/extractors/whatsapp_extractor.py`

```bash
cd ~/GitHub/contacts && uv run contacts index --chats  # Extract from live DB
```

**How it works:**
1. Reads macOS ChatStorage.sqlite directly (WhatsApp stores here)
2. Extracts: sender, timestamp, message text, group info
3. Handles multi-line messages, filters system messages (group changes, calls)
4. Produces one document per conversation
5. Embeds into `whatsapp_chats` collection (19K vectors)

**Scale:** 135 chats, 41K messages

## Signal (Desktop Export)

**Repo:** `div_legal/src/scripts/ingest_signal.py`, `div_legal/src/extractors/signal_extractor.py`

```bash
# Export from Signal Desktop
sigexport ~/GitHub/contacts/data/signal/

# Ingest into vector DB
cd ~/GitHub/div_legal && uv run python -m src.scripts.ingest_signal
```

**How it works:**
1. `sigexport` CLI extracts Signal Desktop database to markdown per contact
2. Format: `[YYYY-MM-DD HH:MM:SS] Sender: message`
3. Filters: reactions, call events, empty messages
4. Normalizes contact names (CamelCase → spaced)
5. Embeds into `legal_docs_v2` + `whatsapp_chats`

**Scale:** 73 conversations, 50+ ingested

## iMessage (macOS Contacts Pipeline)

**Repo:** `contacts/src/contacts_organizer/extract/applescript.py`

```bash
cd ~/GitHub/contacts && uv run contacts extract
```

**How it works:**
1. AppleScript drives macOS Contacts.app + Messages.app
2. Extracts communication history per contact
3. Merges with WhatsApp/Signal data for unified communication graph
4. Part of the 4-stage contacts pipeline (Extract → Merge → Dedupe → Embed)

## PDF Documents

**Repo:** `div_legal/src/extractors/pdf_extractor.py`

**How it works:**
1. PyMUPDF (fitz) extracts text + metadata from PDFs
2. Handles encrypted PDFs (tries password list from config)
3. Pages joined with `---` separator
4. Metadata: creation date, title, author from PDF properties
5. For image-only PDFs: fallback to vision model

**Scale:** 376 bank statement PDFs, 600+ disclosure documents

## Images & Screenshots → Markdown

**Repo:** `div_legal/src/processors/image_summarizer.py`

```python
# Converts any image to descriptive markdown via vision model
from src.processors.image_summarizer import summarize_image
text = summarize_image("/path/to/screenshot.png")
```

**How it works:**
1. Supported: PNG, JPG, TIFF, WebP, BMP, GIF
2. Image binary → base64 → Ollama vision endpoint
3. Model: Gemma 4 (12B) or LLava (13B) with legal-focused prompt
4. Output: Structured markdown describing document content
5. Binary saved to `sdata/attachments/{sha256_hash}.{ext}`

**Legal prompt focuses on:** dates, amounts, signatures, stamps, headers, handwriting

## Financial Data (Bank Sync)

**Repo:** `div_legal/src/scripts/bank_sync.py`

```bash
uv run python -m src.scripts.bank_sync --sync
```

**Connectors:** Plaid API, OFX (bank feeds), Revolut API, Interactive Brokers, Gemini, CSV
**Output:** Markdown + TimescaleDB `trades` hypertable
**Currencies:** USD, ISK, EUR, GBP

## Claude Code Sessions

**Repo:** `policy-orchestrator/scripts/ingest_sessions.py`

```bash
uv run devctl ingest-sessions        # incremental (6h LaunchAgent)
uv run devctl ingest-sessions --all   # full re-ingest
```

**How it works:**
1. Discovers JSONL files in `~/.claude/projects/*/`
2. Parses user/assistant turns, tool_use blocks
3. Chunks at 512 tokens with 64-token overlap
4. Embeds hybrid (BGE + SPLADE) via docvec service
5. Upserts with deterministic point IDs (re-ingestion = update, not duplicate)
6. State tracking: `local/ingest_state.json` (re-ingests if file grows >10%)

**Scale:** 1793 sessions, 96K+ vectors

## Claude.ai Web Conversations

**Repo:** `contacts/`

```bash
cd ~/GitHub/contacts && uv run contacts import-claude
```

**Source:** Export from claude.ai/settings → JSON
**Scale:** 132 conversations → `claude_chats_ai` (2K vectors)

## Composite Reindex (All Sources)

**Repo:** `div_legal/scripts/sync_all.sh`

```bash
cd ~/GitHub/div_legal && bash scripts/sync_all.sh [flags]
```

**7 Phases:**
1. Preflight — health checks (Qdrant, Ollama, disk space)
2. Data Acquisition — IMAP + Signal + Contacts extract (parallel)
3. Contacts Pipeline — WhatsApp import → merge → enrich → dedupe → index → render
4. div_legal Pipeline — incoming → frontmatter → Signal ingest → index → embed
5. Contacts Embedding — WhatsApp + Signal + Claude chats → Qdrant
6. CaseLedger — Docker stack + incremental embed
7. Reports — timeline, case timeline, state summary

**Flags:** `--no-contacts`, `--no-caseledger`, `--no-embed`, `--no-signal`, `--no-whatsapp`, `--no-imap`, `--no-reports`, `--full`, `--from N`, `--dry-run`
