# Repository Map

## Core Repos (Must Deploy)

### policy-orchestrator (Hub)
- **Role:** Control plane, governance, registries, cross-repo coordination
- **Key files:** `registries/repos.yaml`, `registries/vector-collections.yaml`, `registries/secrets.schema.yaml`, `registries/agents.yaml`, `INTENT.md`
- **CLI:** `devctl` — 30+ commands for search, audit, embed, facts, provenance, pages
- **Also ships:** `gai` (global repo orchestrator), `ingest_sessions.py`, `search_unified.py`
- **Depends on:** docvec (embedding), Qdrant, TimescaleDB

### docvec (Shared Library)
- **Role:** Embedding, chunking, vector search infrastructure
- **Key exports:** `embed_hybrid()`, `embed_batch()`, `rerank()`, `chunk_text()`, `chunk_point_id()`
- **Service:** FastAPI on :8100 (loads models once, stays warm)
- **Models:** BGE-base-en-v1.5 (dense), SPLADE++ (sparse), ms-marco-MiniLM-L-6-v2 (reranker)
- **Depends on:** sentence-transformers, fastembed, qdrant-client

### div_legal (Data Engine)
- **Role:** Raw data → processed markdown → embedded vectors
- **Extractors:** PDF, EML, MBOX, WhatsApp, Signal, Image, HTML, DOCX, XLSX, CSV, ICS
- **Pipelines:** IMAP sync, Signal ingest, bank sync, image summarization
- **Scripts:** `sync_all.sh` (7-phase composite reindex), `imap_sync.py`, `ingest_signal.py`
- **Output:** `sdata/md/` (processed markdown corpus), `legal_docs_v2` collection (379K vectors)
- **Depends on:** docvec, Ollama (vision + classification), Qdrant

### caseledger (Analysis Brain)
- **Role:** Adversarial analysis — facts, contradictions, cycles, chains, attack vectors
- **API:** FastAPI on :8000 (25 endpoints)
- **Pipeline:** 11-step extraction + analysis
- **Analysis modules:** contradiction_detector, cycle_detector, chain_engine, consistency_metrics, compliance_audit, financial_recon, deadline_tracker, case_graph, projections
- **Rules DB:** `pipeline/rules/illinois_family.yaml` (100+ statutes + case law)
- **Output:** JSON API, HTML timelines, court-ready PDFs
- **Depends on:** docvec, Qdrant (:7333), PostgreSQL (:5433), Ollama, optionally Claude API

### contacts (Communication Graph)
- **Role:** Contact ingestion (macOS, WhatsApp, LinkedIn), chat indexing
- **Sources:** AppleScript (macOS Contacts), ChatStorage.sqlite (WhatsApp live), Signal Desktop, LinkedIn CSV, Claude.ai exports
- **Pipeline:** Extract → Merge → Dedupe → Embed → Render
- **Collections:** `contacts` (3.4K), `whatsapp_chats` (19K), `claude_chats_ai` (2K)
- **Depends on:** docvec, Qdrant

### gpu-workers (Compute Layer)
- **Role:** Vast.ai GPU provisioning for batch embedding + classification
- **CLI:** `gpuw up|status|ssh|run|upload|download|down`
- **Specs:** 2xA40 (default), 4090, L40S, H100
- **Workloads:** embed_hybrid, classify_topics, full_rebuild
- **Throughput:** 150 chunks/sec (vs 3-4 local)
- **Depends on:** Vast.ai API, docvec models

## Supporting Repos

### llm-router
- **Role:** Cost-optimized model routing by complexity
- **Models:** llama-3.2-3b (low) → mistral-7b (mid) → claude-sonnet (high)
- **Language:** Node.js

### sovereign-legal / dna-rights / embedded-commands
- **Role:** Legal framework repos (jurisdictional analysis, natural rights, cognitive architecture)
- **Created:** 2026-05-08
- **Status:** Active, content in progress

### words_quantum_legal
- **Role:** Quantum legal analysis visualizations
- **Output:** 19 HTML pages deployed to GitHub Pages (public, unencrypted)

### energy_texas
- **Role:** ERCOT energy market research
- **Output:** 21 HTML reports (encrypted, deployed to Pages)

## Dependency Graph

```
policy-orchestrator (hub)
├── docvec (lib)        ← all repos depend on this for embedding
├── div_legal (data)    ← depends on docvec, feeds caseledger
├── caseledger (brain)  ← depends on docvec, div_legal data, PostgreSQL
├── contacts (comms)    ← depends on docvec
├── gpu-workers (gpu)   ← uses docvec models on remote GPUs
└── llm-router (llm)    ← standalone, used by caseledger for routing
```

## Category Breakdown (61 active repos)

| Category | Count | Examples |
|----------|-------|---------|
| Infrastructure | 8 | policy-orchestrator, docvec, gpu-workers, llm-router, development-environment |
| Legal | 7 | div_legal, caseledger, sovereign-legal, dna-rights, words_quantum_legal |
| AI/Agents | 5 | cortex, puffin, vector-lab, embedded-commands |
| Quant Finance | 6 | vpin, alpha_research, ts_embed, hyperliquid, fi-futures |
| Trading | 12 | sv* repos (svprod, svstrat, svpnl, etc.) |
| Creative/Math | 4 | Escher, d72, twoform, gaba_glutamate |
| Web/Portfolio | 5 | jthorvaldur.github.io, darkgallery, morpheme-page |
| Research | 4 | lectures_sloan, joel-knowledge, nova |
| Contacts/Personal | 3 | contacts, imclean, imdb |
