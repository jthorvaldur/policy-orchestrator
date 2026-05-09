# policy-orchestrator

Development control plane for a 26-repo ecosystem. Centralizes policy enforcement, vector DB management, encrypted GitHub Pages deployment, build provenance, and cross-repo coordination.

## Quick start

```bash
uv sync
devctl              # dashboard + cheat sheet
devctl health       # full system check
```

## devctl

Run bare for live dashboard:

```
$ devctl

  devctl — control plane

  26 repos  ai-agents:6  infrastructure:6  legal:4  quant-finance:5  ...
  2,050,352 vectors  across 12 collections
  11 page sections  8 deployed  3 pending

  Commands

  Repos      status, list, audit, discover, inventory
  Data       db-status, search, embed, audit-vectors
  Pages      deploy-pages, audit-pages, verify-pages
  Secrets    secrets, validate-secrets
  Facts      log-fact, query-facts, log-feedback, query-feedback
  Build      provenance, benchmark, health
  Tools      sync, dashboard, readme, policy, ingest-sessions, search-sessions

  Quick Start

  Check everything           devctl health
  What's dirty?              devctl status --dirty
  Search all data            devctl search "query"
  Deploy pages from cwd      devctl deploy-pages --auto --verify --push
  Run benchmarks             devctl benchmark
  Scale projection           devctl benchmark --project=100000
  Vector DB overview         devctl db-status
  Security audit pages       devctl audit-pages
  Live page verification     devctl verify-pages --quick
  What generated a file?     devctl provenance show path/file.html
  Stale outputs?             devctl provenance stale
  Log a verified fact        devctl log-fact --fact "X" --source-type email --confidence verified --domain legal

  Full reference: docs/DEVCTL.md
```

## What it manages

### 26 repos across 7 categories

| Category | Repos | Key |
|----------|-------|-----|
| Legal | div_legal, caseledger, legal-tax-ops, words_quantum_legal, morpheme-page | Case analysis, document intelligence |
| AI/Agents | cortex, puffin, llm-router, vector-lab, joel-knowledge, open-multi-agent-fork | Agent frameworks, LLM routing |
| Quant/Finance | vpin, alpha_research, ts_embed, cyfopt | Quantitative research |
| Infrastructure | policy-orchestrator, contacts, d72, docvec, gpu-workers, energy_texas | Control plane, vectordb, GPU compute |
| Creative/Math | Escher, darkgallery | Visualizations |
| Web/Portfolio | jthorvaldur.github.io, bulldogs | Public sites |
| Product | caseledger | Legal case management |

### 2M+ vectors across 12 collections

Two Qdrant instances, all hybrid (dense BGE + sparse SPLADE).

```bash
devctl db-status    # colored overview with chunking info + coverage
devctl search "X"   # federated search across all collections
```

| Collection | Points | Owner |
|-----------|--------|-------|
| case_docs | 1.7M | caseledger |
| legal_docs_v2 | 239K | div_legal |
| claude_code_sessions | 68K | policy-orchestrator |
| whatsapp_chats | 19K | contacts |
| openai_chats | 5.6K | div_legal |
| contacts | 3.4K | contacts |
| claude_chats_ai | 2K | contacts |
| + 5 more | | |

### 146 encrypted GitHub Pages

AES-256-GCM client-side encryption, 3 password zones.

```bash
devctl deploy-pages --auto --verify --push   # deploy from current repo
devctl audit-pages                           # security policy check
devctl verify-pages                          # live HTTPS decrypt test
```

### Build provenance + benchmarks

```bash
devctl provenance show reports/timeline.html   # what generated this file?
devctl provenance stale                        # outputs needing regeneration
devctl benchmark                               # time all operations
devctl benchmark --project=100000              # project costs at scale
devctl health                                  # full system status
```

## Architecture

```
INTENT.md                              <- root authority
  ├── policies/hard/                   <- ERROR on violation
  │   ├── secrets.md                   <- never commit secrets
  │   ├── git-main.md                  <- no force push
  │   ├── legal-data.md               <- legal data boundaries
  │   ├── pages-encryption.yaml       <- AES-GCM encryption rules
  │   └── quantization.yaml           <- int8 for >10K point collections
  ├── policies/soft/                   <- WARN only
  ├── registries/
  │   ├── repos.yaml                  <- 26 repos
  │   ├── vector-collections.yaml     <- 12 collections with chunking/coverage
  │   ├── pages.yaml                  <- 11 page sections with generators
  │   ├── providers.yaml              <- 6 LLM providers with task routing
  │   └── secrets.schema.yaml         <- key profiles + validation patterns
  ├── lib/
  │   ├── llm_router.py               <- single-file LLM provider router
  │   ├── provenance.py               <- build lineage tracking
  │   └── profiler.py                 <- operation timing + throughput
  ├── scripts/                        <- 20+ enforcement and utility scripts
  ├── docs/
  │   ├── DEVCTL.md                   <- full command reference
  │   ├── devctl-commands.yaml        <- machine-readable command registry
  │   ├── DEPLOYMENT.md               <- provider + Vast.ai + pages guide
  │   └── KEY_ACQUISITION.md          <- API key priority spec
  ├── templates/                      <- standard files synced to managed repos
  └── adr/                            <- architectural decision records
```

Hub-and-spoke: code stays distributed, governance is centralized. See `adr/0001-control-plane-architecture.md`.

## Global tools

```bash
gai                 # repo status across all ~/GitHub/ (pub/priv, clean/dirty)
gai commit          # AI commit message + push for each dirty repo
gai pages           # GitHub Pages deployment status
gai providers       # LLM provider availability
gai vast            # Vast.ai GPU instance status
gai secrets         # key validation
gai env             # keys.zsh propagation check
```

## Governing document

[`INTENT.md`](INTENT.md) is the root authority. Core directive:

> Maximize alignment with repository intent. Not output volume.

## Full command reference

See [`docs/DEVCTL.md`](docs/DEVCTL.md) for all 27 commands with options, examples, and cross-references.

Machine-readable: [`docs/devctl-commands.yaml`](docs/devctl-commands.yaml).

<!-- AUTO:footer -->
Managed by [policy-orchestrator](https://github.com/jthorvaldur/policy-orchestrator). Category: infrastructure. 53 commits, last updated 10 minutes ago.
<!-- /AUTO:footer -->
