# System Architecture — Legal Intelligence Platform

A self-reinforcing adversarial analysis system that ingests raw data (emails, chats, documents, screenshots), extracts facts, detects contradictions, finds logical cycles, generates attack vectors, and produces court-ready filings — while feeding discoveries back into itself to compound strategic advantage.

## The Algorithm (Daylight Loop)

```
INGEST → EXTRACT → EMBED → ANALYZE → ATTACK → OUTPUT → RE-INJECT
  ↑                                                          |
  └──────────── knowledge compounds each cycle ─────────────┘
```

Each cycle through the loop:
1. Brings in new raw data (emails arrive, chats happen, documents filed)
2. Extracts structured facts with provenance and confidence levels
3. Embeds into searchable vector space (2M+ vectors across 12 collections)
4. Runs adversarial analysis (contradiction detection, cycle finding, game theory)
5. Generates attack vectors and court-ready filings
6. Re-injects discoveries (anonymized) as concepts — the system grows smarter

The concept DB (`concepts`, `directives`, `fact_registry`) is the institutional memory. Every cycle adds to it. Every future search benefits from past analysis.

## Architecture Docs

| Doc | Purpose |
|-----|---------|
| [00-system-overview.md](00-system-overview.md) | High-level architecture, repo map, the Daylight concept |
| [01-data-flow.md](01-data-flow.md) | End-to-end data flow from raw sources to outputs |
| [02-repos.md](02-repos.md) | All repos, their roles, dependencies, how they connect |
| [03-ingestion.md](03-ingestion.md) | All ingestion pipelines (Gmail, WhatsApp, Signal, iMessage, screenshots, PDFs) |
| [04-databases.md](04-databases.md) | Qdrant collections, TimescaleDB hypertables, PostgreSQL schemas |
| [05-embedding-models.md](05-embedding-models.md) | ML models, docvec service, GPU workers, the warm service |
| [06-analysis-engine.md](06-analysis-engine.md) | Game theory, cycle detection, chain engine, attack vectors |
| [07-tools-cli.md](07-tools-cli.md) | devctl, gpuw, gai, llm-router — all CLI tools |
| [08-provenance.md](08-provenance.md) | Provenance tracking, fact validation, confidence hierarchy |
| [09-deployment.md](09-deployment.md) | Local stack, Docker, LaunchAgents, AWS Lambda scaling path |
| [10-outputs.md](10-outputs.md) | HTML timelines, court filings, encrypted pages, binder generation |
| [11-knowledge-loop.md](11-knowledge-loop.md) | Feedback re-injection, concept growth, learning loop |
| [12-fact-treatment.md](12-fact-treatment.md) | 6-layer context model, eval loop, confidence-weighted retrieval (from OpenAI) |

## Quick Start (Local)

```bash
# Core services (always running)
docker compose -f ~/GitHub/policy-orchestrator/infra/docker-compose.yml up -d  # TimescaleDB :5434
docker compose -f ~/GitHub/caseledger/infra/docker-compose.yml up -d          # Qdrant :7333, Postgres :5433
# Qdrant main instance (port 6333) assumed running via Docker Desktop or separate compose

# Embedding service (stays warm, loads models once)
launchctl load ~/Library/LaunchAgents/com.jthor.docvec-service.plist  # :8100

# Full reindex (all data sources)
cd ~/GitHub/div_legal && bash scripts/sync_all.sh

# Search across everything
cd ~/GitHub/policy-orchestrator && uv run devctl search "query here"

# CaseLedger API (analysis endpoints)
cd ~/GitHub/caseledger && uv run uvicorn api.main:app --port 8000
```

## Key Repos (Start Here)

| Repo | Role | GitHub |
|------|------|--------|
| [policy-orchestrator](https://github.com/jthorvaldur/policy-orchestrator) | Control plane, registries, devctl CLI | Hub |
| [docvec](https://github.com/jthorvaldur/docvec) | Shared embedding library + warm service | Core lib |
| [div_legal](https://github.com/jthorvaldur/div-legal) | Data pipeline — extraction, ingestion, embedding | Data engine |
| [caseledger](https://github.com/jthorvaldur/caseledger) | Analysis engine — facts, graphs, cycles, chains | Brain |
| [contacts](https://github.com/jthorvaldur/contacts) | Contact + chat ingestion (WhatsApp, Signal, iMessage) | Data source |
| [gpu-workers](https://github.com/jthorvaldur/gpu-workers) | Vast.ai GPU provisioning for batch embedding | Compute |
