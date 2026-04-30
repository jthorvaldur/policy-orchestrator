# Deployment & Provider Configuration

How API keys, LLM providers, and GPU compute work across the repo ecosystem.

## Provider Inventory

| Provider | Env Var | Endpoint | Use For |
|----------|---------|----------|---------|
| **Ollama (local)** | `OLLAMA_BASE_URL` | `http://localhost:11434` | Sensitive data, legal docs, embeddings, offline dev |
| **Anthropic** | `ANTHROPIC_API_KEY` | `api.anthropic.com` | Complex reasoning, legal analysis, code architecture |
| **OpenRouter** | `OPENROUTER_API_KEY` | `openrouter.ai/api/v1` | Cheap classification, model variety, fallback |
| **Vast.ai** | `VAST_API_KEY` + `VAST_ENDPOINT` | Per-instance | Batch embedding, GPU-accelerated inference |
| **OpenAI** | `OPENAI_API_KEY` | `api.openai.com` | Implementation tasks, code generation |
| **Google** | `GEMINI_API_KEY` | `generativelanguage.googleapis.com` | Research, large context |

## Key Setup

All keys live in `~/.oh-my-zsh/custom/keys.zsh` — the single source of truth. Keys are exported to every new shell session automatically. Repos never store keys — they read from environment.

### Local Propagation

keys.zsh is sourced when a new terminal opens. If you add or change a key, existing shells won't see it until you either open a new terminal or re-source:

```bash
source ~/.oh-my-zsh/custom/keys.zsh
```

Check propagation status:
```bash
gai env              # compare keys.zsh vs current shell — shows stale/missing
gai secrets          # validate repos have the keys their profiles require
gai secrets --live   # also ping endpoints (ollama, anthropic, openrouter)
```

### Remote Propagation (Vast.ai, SSH, etc.)

When spinning up remote machines, only forward the keys needed for that job:

```bash
# Generate a safe env file for remote machines
gai env --export > /tmp/remote_env.sh

# SCP to Vast.ai instance
scp -P $PORT /tmp/remote_env.sh root@$HOST:~/env.sh
ssh -p $PORT root@$HOST "source ~/env.sh && echo ok"

# Clean up local copy
rm /tmp/remote_env.sh
```

The `--export` output includes only `HF_TOKEN` (for pulling gated models) and `VAST_API_KEY`, with `ANTHROPIC_API_KEY` and `OPENROUTER_API_KEY` commented out as optional. Never forward `PLAID_*`, `CONTACTS_PAGE_PASSWORD`, or other non-compute keys to remote machines.

div_legal's `vast_deploy_oneshot.sh` already forwards `HF_TOKEN` via the `HF_CMD` pattern — the `gai env --export` approach is a generalized version of the same idea.

## LLM Router

`lib/llm_router.py` is a single-file provider router. Copy or symlink it into any repo:

```bash
# From a repo directory
ln -s ~/GitHub/policy-orchestrator/lib/llm_router.py ./llm_router.py
```

### Usage

```python
from llm_router import ask, ask_json, available_providers

# Task-based routing (auto-selects provider + model)
answer = ask("summarize this contract", task="summarize")     # -> ollama (low)
answer = ask("analyze these contradictions", task="analyze")   # -> anthropic haiku (mid)
answer = ask("draft legal analysis", task="legal_analysis")    # -> anthropic sonnet (high)

# Explicit model
answer = ask("complex reasoning task", model="claude-sonnet-4-6")

# Structured output
data = ask_json("extract all dates and amounts", task="extract")

# Async (for caseledger, etc.)
result = await async_ask("classify this document", task="classify")

# Diagnostics
print(available_providers())
# {'ollama': True, 'anthropic': True, 'openrouter': True, 'vast': False}
```

### Task Routing Table

| Task | Tier | Primary Provider | Fallback |
|------|------|-----------------|----------|
| `classify`, `extract`, `summarize`, `tag` | Low | Ollama local | OpenRouter |
| `analyze`, `compare`, `draft` | Mid | Anthropic Haiku | OpenRouter → Ollama |
| `reason`, `plan`, `code`, `legal_analysis`, `contradict` | High | Anthropic Sonnet | OpenRouter → Ollama |

### Legal Repos

div_legal and other legal repos must not send data to cloud providers. Set in the repo's `.env`:

```
LEGAL_LOCAL_ONLY=1
```

The router will refuse cloud calls and use only local Ollama. The `--use-opus` flag pattern in div_legal scripts can override this by calling the router with an explicit model.

## Vast.ai GPU Offload

For batch embedding and heavy inference that's too slow on the local M4.

### Prerequisites

```bash
pip install vastai
vastai set api-key YOUR_API_KEY   # from https://cloud.vast.ai/manage-keys/
```

### Reference Implementation: div_legal

div_legal has a production-tested Vast.ai pipeline with shell scripts and two GPU embedding versions. This is the pattern to follow for other repos.

**Shell scripts** (in `div_legal/scripts/`):

| Script | Purpose |
|--------|---------|
| `vast_up.sh` | Find cheapest GPU, create instance, save state to `~/.vast_instance.json` |
| `vast_status.sh` | Show running instances, SSH strings, cost, balance |
| `vast_deploy_oneshot.sh` | Full pipeline: wait for boot, install deps, upload data, launch embed, poll, download |
| `vast_down.sh` | Download results, destroy instance, show final cost |
| `deploy_vast_embed.sh` | Step-by-step alternative to oneshot |

**GPU embedding scripts** (in `div_legal/src/scripts/`):

| Script | Version | Details |
|--------|---------|---------|
| `embed_gpu.py` | v1 | sentence-transformers, batch=256, 768-char chunks, resume support |
| `embed_gpu_v2.py` | v2 | Pipelined tokenization, fp16, batch=1024, 512-char chunks, DataLoader workers, SPLADE++ sparse |
| `upsert_from_jsonl.py` | - | Read JSONL vectors, batch upsert to local Qdrant (100/batch) |

### Workflow (proven)

```bash
# 1. Spin up GPU
cd ~/GitHub/div_legal
./scripts/vast_up.sh                    # cheapest 4090 (~$0.30/hr)
./scripts/vast_up.sh --gpu A100         # or specific GPU

# 2. Deploy and run embedding
./scripts/vast_deploy_oneshot.sh        # full pipeline, runs in background

# 3. Monitor
./scripts/vast_deploy_oneshot.sh --poll # check GPU util, progress, log tail

# 4. Download results and destroy
./scripts/vast_deploy_oneshot.sh --download  # downloads JSONL, upserts to Qdrant, destroys instance
```

### Instance Selection Policy

For embedding workloads:

| GPU | $/hr | Throughput | Best For |
|-----|------|-----------|----------|
| RTX 4090 | ~$0.30 | 300-400 chunks/s | Best cost/performance for most jobs |
| A100 40GB | ~$0.50 | 400-500 chunks/s | Large models, fp16 tensor cores |
| 2x RTX 4090 | ~$0.60 | 600-800 chunks/s | Max throughput with --multi-gpu |
| H100 | ~$1.50 | Highest | Only if time-critical |

Search filters that work well:
```bash
vastai search offers "gpu_name=RTX_4090 num_gpus=1 inet_down>100 disk_space>20 verified=true" -o 'dph+'
```

Key parameters: `verified=true` (reliable hosts), `inet_down>100` (fast data transfer), `dph+` (sort cheapest first).

### Adapting for Other Repos

To add Vast.ai embedding to a new repo:

1. Copy `vast_up.sh`, `vast_down.sh`, `vast_deploy_oneshot.sh` from div_legal
2. Copy `embed_gpu.py` (or v2) and `upsert_from_jsonl.py`
3. Adjust: input directory, output JSONL path, Qdrant collection name, embedding model
4. The shell scripts are repo-agnostic — they detect instances via `vastai show instances`

CaseLedger has `vastai>=1.0.8` in deps but the scripts aren't wired up yet. Same pattern applies.

### Monitoring from anywhere

```bash
gai vast           # show all running instances
gai providers      # check if VAST_ENDPOINT is set
```

## OpenRouter

Multi-model gateway. Single API key accesses 100+ models. Useful for:

- **Cheap classification:** `meta-llama/llama-3.2-3b-instruct` at $0.06/M tokens
- **Mid-tier extraction:** `mistralai/mistral-7b-instruct` at $0.10/M tokens
- **Large context:** `google/gemini-2.5-flash` at $0.15/M tokens
- **High quality via proxy:** `anthropic/claude-sonnet-4-6` (uses your OpenRouter balance)

The router's `_ask_openai_compat()` backend handles OpenRouter natively — same endpoint format.

## Validation

### Per-Repo Secret Profiles

Each repo declares its requirements in `registries/secrets.schema.yaml` under `repo_requirements`:

```yaml
caseledger:
  profiles: [base_llm, gpu_compute]
  cloud_allowed: true

div_legal:
  profiles: [legal_local]
  cloud_allowed: false
```

### Key Pattern Validation

`validate_secrets.py` checks key prefixes to catch mislabeled keys:

| Key | Expected Prefix |
|-----|----------------|
| `ANTHROPIC_API_KEY` | `sk-ant-` |
| `OPENROUTER_API_KEY` | `sk-or-v1-` |
| `OPENAI_API_KEY` | `sk-` |
| `HF_TOKEN` | `hf_` |
| `VAST_API_KEY` | (get from vast.ai console) |

### Running Validation

```bash
devctl validate-secrets                    # full check, all repos
devctl validate-secrets --repo=caseledger  # single repo
devctl validate-secrets --live             # ping endpoints too
devctl validate-secrets --keys-only        # just the key table
```
