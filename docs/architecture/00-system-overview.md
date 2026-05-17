# System Overview

## What This Is

A distributed legal intelligence platform that treats litigation as an information warfare problem. The system continuously ingests adversary communications, court filings, and financial records, then runs adversarial analysis to find contradictions, obligation cycles, and disclosure gaps — outputting court-ready attack filings.

The architecture is **hub-and-spoke**: `policy-orchestrator` is the hub (governance, registries, coordination). Each specialized repo is a spoke (data pipeline, analysis engine, embedding layer, etc.).

## Core Concept: The Daylight Algorithm

Named for the legal principle "sunlight is the best disinfectant." The system exposes contradictions in adversary positions by:

1. **Ingesting everything** — emails, texts, court filings, bank statements, phone records
2. **Extracting facts** — with confidence levels and provenance chains
3. **Detecting contradictions** — statement A conflicts with statement B (date, amount, claim)
4. **Finding cycles** — obligation loops that create legal paradoxes (e.g., "comply to get access, but need access to comply")
5. **Building chains** — assertion → evidence → rule → conclusion (court-admissible logic)
6. **Generating attacks** — court filings that exploit found weaknesses

Each cycle compounds: discoveries become facts, facts inform future searches, searches find deeper contradictions.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    DATA SOURCES (Raw Input)                       │
├─────────────────────────────────────────────────────────────────┤
│  Gmail (IMAP)  │  WhatsApp  │  Signal  │  Court Filings  │ Bank │
│  iMessage      │  PDFs      │  Images  │  CSV/XLSX       │ Docs │
└────────┬───────┴─────┬──────┴────┬─────┴───────┬─────────┴──┬──┘
         │             │           │             │            │
         ▼             ▼           ▼             ▼            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    INGESTION LAYER (div_legal)                    │
├─────────────────────────────────────────────────────────────────┤
│  IMAP Sync  │  WhatsApp SQLite  │  Signal Export  │  Extractors │
│  (UID track) │  (ChatStorage.db) │  (sigexport)   │  (PDF/Image)│
│             │                    │                 │  OCR/Vision │
└────────────────────────┬────────────────────────────────────────┘
                         │ Markdown + Metadata
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    PROCESSING LAYER (docvec + GPU)                │
├─────────────────────────────────────────────────────────────────┤
│  Chunking (512 tok)  │  Dense Embed (BGE 768d)  │  Sparse (SPLADE) │
│  Dedup (SHA256)      │  Rerank (cross-encoder)  │  Topic Classify  │
│  Metadata Extract    │  Fact Extract (LLM)      │  Vision Summary  │
└────────────────────────┬────────────────────────────────────────┘
                         │ Vectors + Facts + Metadata
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    STORAGE LAYER                                  │
├──────────────────┬──────────────────┬───────────────────────────┤
│  Qdrant :6333    │  Qdrant :7333    │  TimescaleDB :5434         │
│  12 collections  │  case_docs 1.7M  │  trades, bars, events      │
│  380K+ legal     │  case_facts 17K  │  facts timeline            │
│  96K sessions    │                  │  file_registry             │
│  19K chats       │  PostgreSQL:5433 │                            │
│  3.4K contacts   │  facts, sources  │  Provenance SQLite         │
│  concepts, facts │  graph, parties  │  builds, files, lineage    │
└──────────────────┴──────────────────┴───────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    ANALYSIS ENGINE (caseledger)                   │
├─────────────────────────────────────────────────────────────────┤
│  Contradiction Detector  │  Cycle Detector (Betti numbers)       │
│  Chain Engine (proofs)   │  Consistency Metrics (KL divergence)  │
│  Compliance Audit        │  Financial Reconciliation             │
│  Deadline Tracker        │  Case Hypergraph                      │
│  Game Theory (response deficit, disclosure completeness)         │
└────────────────────────┬────────────────────────────────────────┘
                         │ Attack vectors + chains + filings
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    OUTPUT LAYER                                   │
├─────────────────────────────────────────────────────────────────┤
│  Court Filings (PDF)  │  HTML Timelines  │  Encrypted Pages      │
│  Binder Generator     │  Dashboards      │  API (FastAPI :8000)  │
│  Attack Vectors       │  Projections     │  Concept Re-injection │
└─────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    KNOWLEDGE LOOP (re-injection)                  │
├─────────────────────────────────────────────────────────────────┤
│  Discoveries → fact_registry (confidence-ranked)                 │
│  Session analysis → concepts collection (strategic edge)         │
│  Feedback events → calibration (agent behavior)                  │
│  Chat re-injection (anonymized) → compounding intelligence       │
└─────────────────────────────────────────────────────────────────┘
```

## Scaling Model (AWS Lambda)

The system is designed for local-first (M4 MacBook Pro) but every component maps to a serverless equivalent:

| Local Component | AWS Equivalent | Notes |
|----------------|----------------|-------|
| Qdrant Docker | Qdrant Cloud (managed) | Direct API compatibility |
| TimescaleDB Docker | RDS + TimescaleDB extension | Or Aurora PostgreSQL |
| PostgreSQL (caseledger) | RDS PostgreSQL | Shared with above |
| docvec service (:8100) | Lambda + API Gateway | Or ECS Fargate (warm) |
| GPU Workers (Vast.ai) | SageMaker batch transform | Or Lambda with EFS model cache |
| LaunchAgents (cron) | EventBridge + Step Functions | Scheduled triggers |
| IMAP sync | Lambda + SES/SNS trigger | Or EventBridge scheduler |
| FastAPI (caseledger) | Lambda + API Gateway | Or ECS for always-on |
| Ollama (local LLM) | Bedrock (Claude) | Or SageMaker endpoints |
| GitHub Pages | CloudFront + S3 | Same encryption, CDN delivery |

## Port Map (Local)

| Port | Service | Owner |
|------|---------|-------|
| 6333 | Qdrant (main, 12 collections) | div_legal / policy-orchestrator |
| 7333 | Qdrant (caseledger, 1.7M vectors) | caseledger |
| 5433 | PostgreSQL (facts, graphs) | caseledger |
| 5434 | TimescaleDB (trades, events, provenance) | policy-orchestrator |
| 8000 | CaseLedger API (FastAPI) | caseledger |
| 8100 | docvec embedding service (FastAPI) | docvec |
| 11434 | Ollama (local LLM inference) | system-wide |
