# docvec Integration into policy-orchestrator

## Context

`docvec` is a shared embedding/chunking/search package at `~/GitHub/docvec/` that now powers vector infrastructure across div_legal, caseledger, and contacts. Policy-orchestrator should become the **control plane** for this infrastructure — coordinating embeds, enforcing model consistency, auditing collection health, and providing a unified search interface via `devctl`.

## Current State

### What docvec provides
- **Embedding**: BGE-base-en-v1.5 (768-dim) via sentence-transformers, with SPLADE++ sparse
- **Chunking**: Sentence-aware, configurable per-repo
- **Qdrant client**: Named vectors, INT8 quantization, RRF hybrid search
- **Deterministic IDs**: SHA256-based, no dupes on re-run
- **State tracking**: Per-file content hash, crash recovery
- **Error reporting**: Typed exceptions, EmbedResult summaries
- **Federated search**: Cross-collection parallel search with RRF merge
- **GPU pipeline**: Pipelined DataLoader, fp16, GPU SPLADE++

### What policy-orchestrator currently has
- `scripts/lib/embedder.py` — Ollama nomic-embed-text (legacy, should migrate to docvec)
- `scripts/lib/qdrant_helpers.py` — Basic Qdrant client (should migrate to docvec)
- `registries/vector-collections.yaml` — Collection ownership + access control
- `scripts/ingest_sessions.py` — Claude session ingestion to Qdrant
- `scripts/search_sessions.py` — Semantic search across sessions
- `scripts/log_feedback.py` + `log_fact.py` — Fact/feedback event logging

## New devctl Commands

### `devctl embed` — Trigger re-embed for any repo

```bash
devctl embed --repo div_legal                    # incremental embed (local)
devctl embed --repo div_legal --full             # full re-embed (clears state)
devctl embed --repo div_legal --gpu              # offload to Vast.ai
devctl embed --repo caseledger --sparse-backfill # add SPLADE++ to existing dense
devctl embed --repo contacts --collection whatsapp_chats  # specific collection
```

**Implementation**: Script at `scripts/embed.py` that:
1. Reads `registries/repos.yaml` to get repo path + vector_namespace
2. Reads `registries/vector-collections.yaml` for collection config
3. Calls docvec functions directly (Python import, not subprocess)
4. Supports `--gpu` flag to provision Vast.ai instance via `vastai` CLI

### `devctl search` — Unified cross-repo search

```bash
devctl search "Reserve 1153 balance $77,185"
devctl search "custody schedule Allison" --rerank
devctl search "settlement damages" --collection legal_docs_v2
devctl search "discussed mortgage" --collections legal_docs_v2,whatsapp_chats
```

**Implementation**: Thin wrapper around `docvec.federated.federated_search()`. Uses BGE embedding for query, SPLADE++ for hybrid, optional cross-encoder reranking.

### `devctl audit-vectors` — Collection health check

```bash
devctl audit-vectors                  # all collections on all ports
devctl audit-vectors --repo div_legal # just div_legal's collections
```

**Output**:
```
Port 6333:
  legal_docs_v2    238,499 pts  INDEXED  hybrid(dense+sparse)  INT8  BGE
  contacts           3,390 pts  INDEXED  flat                   none  BGE
  whatsapp_chats    19,061 pts  INDEXED  flat                   none  BGE
  claude_code_ses   19,465 pts  INDEXED  flat                   none  nomic ⚠ (should be BGE)
  
Port 7333:
  case_docs      1,711,012 pts  INDEXED  hybrid(dense+sparse)  INT8  BGE
  
Warnings:
  ⚠ claude_code_sessions: embedding model mismatch (nomic vs BGE standard)
  ⚠ contacts: no sparse vectors (hybrid search unavailable)
  ⚠ whatsapp_chats: no sparse vectors
```

**Implementation**: Script at `scripts/audit_vectors.py` that:
1. Queries both Qdrant ports (6333, 7333)
2. Checks each collection against `registries/vector-collections.yaml`
3. Reports model mismatches, missing sparse vectors, quantization status

### `devctl sync-vectors` — Enforce collection standards

```bash
devctl sync-vectors --dry-run        # show what would change
devctl sync-vectors --collection contacts  # re-embed one collection
```

**Implementation**: Reads `registries/vector-collections.yaml` for expected config, compares to actual Qdrant state, triggers re-embed for non-compliant collections.

## Registry Updates

### `registries/vector-collections.yaml` — Add docvec fields

```yaml
collections:
  legal_docs_v2:
    port: 6333
    owner: div_legal
    readers: [div_legal, caseledger, policy-orchestrator]
    writers: [div_legal]
    embedding_model: BAAI/bge-base-en-v1.5
    vector_type: hybrid          # dense + sparse
    sparse_model: prithivida/Splade_PP_en_v1
    quantization: int8
    hnsw_m: 16
    hnsw_ef_construct: 200
    chunk_max_chars: 512
    chunk_overlap_chars: 128
    points_expected: 238000      # approximate, for health check
    
  contacts:
    port: 6333
    owner: contacts
    readers: [contacts, policy-orchestrator]
    writers: [contacts]
    embedding_model: BAAI/bge-base-en-v1.5
    vector_type: flat            # TODO: upgrade to hybrid
    quantization: none
    points_expected: 3400
    
  whatsapp_chats:
    port: 6333
    owner: contacts
    readers: [contacts, div_legal, policy-orchestrator]
    writers: [contacts]
    embedding_model: BAAI/bge-base-en-v1.5
    vector_type: flat            # TODO: upgrade to hybrid
    quantization: none
    points_expected: 19000
    
  case_docs:
    port: 7333
    owner: caseledger
    readers: [caseledger, div_legal, policy-orchestrator]
    writers: [caseledger]
    embedding_model: BAAI/bge-base-en-v1.5
    vector_type: hybrid
    sparse_model: prithivida/Splade_PP_en_v1
    quantization: int8
    hnsw_m: 16
    hnsw_ef_construct: 200
    points_expected: 1711000

  claude_code_sessions:
    port: 6333
    owner: policy-orchestrator
    readers: [all]
    writers: [policy-orchestrator]
    embedding_model: nomic-embed-text  # TODO: migrate to BGE
    vector_type: flat
    quantization: none
    points_expected: 19000

  feedback_events:
    port: 6333
    owner: policy-orchestrator
    readers: [all]
    writers: [policy-orchestrator]
    embedding_model: nomic-embed-text  # TODO: migrate to BGE
    vector_type: flat
    quantization: none

  fact_registry:
    port: 6333
    owner: policy-orchestrator
    readers: [all]
    writers: [policy-orchestrator]
    embedding_model: nomic-embed-text  # TODO: migrate to BGE
    vector_type: flat
    quantization: none
```

### New policy: `policies/hard/embedding-model.yaml`

```yaml
name: embedding-model-standard
level: hard
description: All vector collections must use the standard embedding model

rules:
  - dense_model: BAAI/bge-base-en-v1.5
    vector_dim: 768
    rationale: >
      Single model ensures cross-collection score comparability.
      BGE-base chosen for best size/quality tradeoff on M4 Mac.
      
  - sparse_model: prithivida/Splade_PP_en_v1
    rationale: >
      SPLADE++ enables literal matching (names, numbers, account IDs)
      alongside semantic search. Required for financial/legal data.
      
  - quantization: int8
    rationale: >
      4x memory reduction with ~99% recall. Required for collections
      >10K points to keep Qdrant performant.

exceptions:
  - collection: claude_code_sessions
    reason: Legacy nomic-embed-text, migration pending
    deadline: 2026-06-01
```

## Environment Variables

All variables from `~/.oh-my-zsh/custom/keys.zsh` that are relevant:

### Embedding & Vector Infrastructure
| Variable | Used By | Purpose |
|----------|---------|---------|
| `OLLAMA_BASE_URL` | docvec (fallback), policy-orchestrator | Local LLM inference endpoint |
| `QDRANT_URL` | all repos | Qdrant endpoint (default localhost:6333) |
| `HF_TOKEN` | docvec GPU, vast.ai | HuggingFace gated model access |
| `VAST_API_KEY` | vast.ai scripts | GPU instance provisioning |
| `VAST_SSH_KEY` | vast.ai scripts | SSH to GPU instances |

### Search & Retrieval
| Variable | Used By | Purpose |
|----------|---------|---------|
| `ANTHROPIC_API_KEY` | caseledger, policy-orchestrator | Complex analysis, cross-doc reasoning |
| `EMBED_BACKEND` | docvec | Override embedding backend (st/fastembed/tei/ollama) |

### Secrets & Pages
| Variable | Used By | Purpose |
|----------|---------|---------|
| `JTHORVALDUR_LEGAL_PAGE_PASSWORD` | deploy_pages.py | Encrypt legal reports for GitHub Pages |
| `CONTACTS_PAGE_PASSWORD` | deploy_pages.py | Encrypt contacts pages |
| `ENERGY_TEXAS_PAGE_PASSWORD` | deploy_pages.py | Encrypt energy reports |

### Financial APIs
| Variable | Used By | Purpose |
|----------|---------|---------|
| `PLAID_CLIENT_ID` | div_legal (future) | Banking API access |
| `PLAID_SECRET` | div_legal (future) | Banking API secret |

## Implementation Steps

### Step 1: Add docvec dependency to policy-orchestrator

```toml
# pyproject.toml
dependencies = [
    "docvec",                    # ADD
    "sentence-transformers>=3.3", # ADD (for BGE embedding)
    "pyyaml>=6.0",
    "click>=8.1",
    "qdrant-client>=1.9",
    "httpx>=0.27",
    "cryptography>=47.0.0",
]

[tool.uv.sources]
docvec = { path = "../docvec" }  # ADD
```

### Step 2: Migrate scripts/lib/embedder.py to docvec

Replace:
```python
# OLD: scripts/lib/embedder.py
def embed_text(text, max_chars=8000, max_retries=3):
    resp = httpx.post(f"{OLLAMA_URL}/api/embeddings", ...)
```

With:
```python
# NEW: scripts/lib/embedder.py
from docvec.embedder import embed_text as _embed
from docvec.config import EmbedConfig

_config = EmbedConfig(embed_backend="st", dense_model="BAAI/bge-base-en-v1.5")

def embed_text(text, max_chars=8000):
    return _embed(text[:max_chars], config=_config)
```

### Step 3: Add new devctl commands in cli.py

```python
@main.command("search")
@click.argument("query")
@click.option("--limit", "-n", default=10)
@click.option("--collection", "-c", default=None)
@click.option("--rerank", is_flag=True)
def search_cmd(query, limit, collection, rerank):
    """Unified search across all vector collections."""
    args = [sys.executable, str(SCRIPTS_DIR / "search_unified.py"), query]
    if limit != 10: args.extend(["--limit", str(limit)])
    if collection: args.extend(["--collection", collection])
    if rerank: args.append("--rerank")
    subprocess.run(args)

@main.command("embed")
@click.option("--repo", required=True)
@click.option("--full", is_flag=True)
@click.option("--gpu", is_flag=True)
@click.option("--collection", default=None)
def embed_cmd(repo, full, gpu, collection):
    """Trigger embedding for a repo's vector collection."""
    args = [sys.executable, str(SCRIPTS_DIR / "embed.py"), f"--repo={repo}"]
    if full: args.append("--full")
    if gpu: args.append("--gpu")
    if collection: args.extend(["--collection", collection])
    subprocess.run(args)

@main.command("audit-vectors")
@click.option("--repo", default=None)
def audit_vectors_cmd(repo):
    """Audit vector collection health across all repos."""
    args = [sys.executable, str(SCRIPTS_DIR / "audit_vectors.py")]
    if repo: args.append(f"--repo={repo}")
    subprocess.run(args)
```

### Step 4: Write new scripts

- `scripts/search_unified.py` — Wraps `docvec.federated.federated_search()`
- `scripts/embed.py` — Reads registry, triggers embed for specified repo
- `scripts/audit_vectors.py` — Queries all Qdrant ports, compares to registry

### Step 5: Update registries

- `registries/vector-collections.yaml` — Add docvec fields (model, type, quantization, expected points)
- `registries/repos.yaml` — Ensure all repos have correct `vector_namespace`

### Step 6: Add embedding model policy

- `policies/hard/embedding-model.yaml` — Enforce BGE + SPLADE++ standard

## Architecture After Integration

```
policy-orchestrator (control plane)
    │
    ├── devctl search    → docvec.federated.federated_search()
    ├── devctl embed     → docvec.embedder + docvec.qdrant
    ├── devctl audit-vectors → docvec.qdrant.get_client() + registry comparison
    │
    ├── registries/vector-collections.yaml  (source of truth for collection configs)
    ├── policies/hard/embedding-model.yaml  (enforced standards)
    │
    └── depends on: docvec (path = "../docvec")
    
docvec (shared library)
    │
    ├── embedder.py    — BGE + SPLADE++ + reranker
    ├── qdrant.py      — Named vectors, INT8, RRF hybrid
    ├── federated.py   — Cross-collection search
    ├── ids.py         — Deterministic point IDs
    ├── state.py       — Per-file tracking
    ├── gpu/           — Vast.ai batch embedding
    │
    └── used by: div_legal, caseledger, contacts, policy-orchestrator

div_legal → docvec → Qdrant :6333 (legal_docs_v2, 238K hybrid)
caseledger → docvec → Qdrant :7333 (case_docs, 1.7M hybrid)  
contacts → docvec → Qdrant :6333 (contacts + whatsapp, 22K BGE)
```
