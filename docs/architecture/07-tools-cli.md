# CLI Tools

## devctl (Control Plane)

**Repo:** `policy-orchestrator/src/policy_orchestrator/cli.py`
**Install:** `cd ~/GitHub/policy-orchestrator && uv run devctl <command>`

### Search & Data
```bash
devctl search "query"                    # Federated search across all 12 collections (20 results default)
devctl search "query" -n 50              # More results
devctl search "query" -c legal_docs_v2   # Single collection
devctl search "query" --no-rerank        # Skip cross-encoder (faster)
devctl db-status                         # All repos → collections → live point counts
devctl audit-vectors                     # Collection health check (model compliance, staleness)
devctl embed --repo=div_legal --full     # Full re-embed
devctl embed --repo=div_legal --gpu      # Offload to Vast.ai
```

### Facts & Knowledge
```bash
devctl log-fact --fact "X owes Y $50K" --source-type email --confidence asserted --domain financial
devctl query-facts "payment" --min-confidence=verified
devctl log-feedback --type correction --signal "Don't summarize" --rule "Terse responses"
devctl query-feedback "testing"
```

### Repos & Governance
```bash
devctl list                              # All registered repos
devctl status --dirty                    # Only repos with uncommitted changes
devctl audit --repo=vpin                 # Policy compliance check
devctl policy                            # Lint all repos against hard/soft policies
devctl sync --repo=caseledger            # Sync templates to repo
devctl secrets --live                    # Validate API keys (ping endpoints)
```

### Provenance & Build
```bash
devctl provenance show path/to/file      # What generated this file?
devctl provenance stale --repo=div_legal # Outputs with changed inputs
devctl provenance rebuild                # Rebuild SQLite index from .provenance/ files
devctl health                            # Full system health (services, data, disk)
```

### Pages & Deploy
```bash
devctl deploy-pages --section=filing --push --verify  # Encrypt + deploy + verify
devctl audit-pages                                     # Check encryption compliance
devctl verify-pages --section=filing                   # Test live decryption via HTTPS
```

### Sessions
```bash
devctl ingest-sessions                   # Ingest Claude Code sessions (incremental)
devctl ingest-sessions --all             # Full re-ingest
devctl search-sessions "query" --repo=caseledger  # Search within sessions
```

## gai (Global AI Orchestrator)

**Location:** `~/bin/gai` (symlink to policy-orchestrator/gai)
**Install:** In PATH via symlink

```bash
gai                    # Default: status of all ~80 repos (dirty/clean, branch, sync)
gai commit             # AI-powered commits for all dirty repos (Claude Haiku generates messages)
gai commit --dry       # Preview without committing
gai secrets --live     # Validate keys across all repos
gai providers          # Show LLM provider status (Anthropic, OpenAI, OpenRouter, Ollama)
gai vast               # Vast.ai credit balance + instance status
gai pages              # GitHub Pages deployment status (deployed vs pending)
gai env --export       # Generate remote env file (for Vast/Lambda: HF_TOKEN, VAST_API_KEY, etc.)
```

**Uses:** Claude Haiku for commit message generation, httpx for API health checks

## gpuw (GPU Workers)

**Repo:** `gpu-workers/gpuw`
**Provider:** Vast.ai

```bash
gpuw up 2xa40                           # Provision 2x A40 instance
gpuw up 4090                            # Budget option
gpuw status                             # Instance state + GPU utilization
gpuw ssh                                # SSH into running instance
gpuw run embed_hybrid --input ~/data/md/  # Run embedding workload (nohup, SSH-safe)
gpuw run classify_topics --input ~/data/  # Run topic classification
gpuw run full_rebuild --input ~/data/     # Combined: extract + classify + embed
gpuw upload ~/local/data/ ~/remote/data/  # Upload data to instance
gpuw download ~/remote/results/ ./local/  # Download results
gpuw down                               # Destroy instance (warns if workload running)
```

**State:** `~/.gpu_worker_state.json`
**Models:** Pre-cached on instance startup (BGE, SPLADE++, llama3.1)
**Idempotency:** SHA256 point IDs + crash recovery via sentinel files

## llm-router (Cost Routing)

**Repo:** `llm-router/router.js` (Node.js)

Routes queries to appropriate model by complexity:

| Complexity | Model | Cost | Use Case |
|-----------|-------|------|----------|
| Low | llama-3.2-3b (OpenRouter) | ~$0.001/query | Classification, extraction |
| Mid | mistral-7b (OpenRouter) | ~$0.01/query | Moderate reasoning |
| High | claude-sonnet (Anthropic) | ~$0.10/query | Complex analysis, code |

```javascript
const { ask } = require('./router');
const result = await ask("Classify this document", { complexity: 'low' });
```

## docvec-service (Embedding API)

**Repo:** `docvec/src/docvec/service.py`
**Start:** `uv run --extra service docvec-service` (or via LaunchAgent)

```bash
# Health check
curl http://localhost:8100/health

# Embed text
curl -X POST http://localhost:8100/embed \
  -H 'Content-Type: application/json' \
  -d '{"texts": ["search query here"]}'

# Hybrid embed (dense + sparse)
curl -X POST http://localhost:8100/embed/hybrid \
  -H 'Content-Type: application/json' \
  -d '{"text": "search query here"}'

# Rerank results
curl -X POST http://localhost:8100/rerank \
  -H 'Content-Type: application/json' \
  -d '{"query": "...", "results": [...], "limit": 10}'
```

## CaseLedger API (Analysis)

**Repo:** `caseledger/api/main.py`
**Start:** `cd ~/GitHub/caseledger && uv run uvicorn api.main:app --port 8000 --reload`
**Docs:** http://localhost:8000/docs (dark-themed Swagger UI)

```bash
# Search
curl -X POST http://localhost:8000/search \
  -d '{"query": "financial disclosure", "limit": 20, "rerank": true}'

# Facts
curl http://localhost:8000/cases/default/facts
curl http://localhost:8000/cases/default/facts/disputed

# Analysis
curl http://localhost:8000/cases/default/cycles
curl http://localhost:8000/cases/default/consistency/respondent
curl http://localhost:8000/cases/default/audit?deep=true
curl http://localhost:8000/cases/default/deadlines

# Chain building
curl -X POST http://localhost:8000/cases/default/chain \
  -d '{"fact_ids": ["F001", "F003"], "rules": ["750 ILCS 5/503(d)"]}'

# Natural language Q&A
curl -X POST http://localhost:8000/cases/default/ask \
  -d '{"question": "What evidence supports dissipation?"}'
```
