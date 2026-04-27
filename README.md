# policy-orchestrator

A control plane for multi-repo development governance. Not a framework, not an app — a policy enforcement and coordination layer across 21 active repositories.

## Governing document

[`INTENT.md`](INTENT.md) is the root authority. Every policy, script, template, and agent contract in this repo derives from it. The core directive:

> Maximize alignment with repository intent. Not output volume.

All policies inherit from INTENT.md. Repos may extend or narrow rules via `INTENT.local.md`, except for boundary rules (INTENT Section 4), which cannot be relaxed.

## How it works

```
INTENT.md                          <- root authority
  ├── policies/hard/               <- enforceable rules (ERROR on violation)
  │   ├── secrets.md               <- never commit secrets
  │   ├── git-main.md              <- no force push, no dirty deploys
  │   └── legal-data.md            <- legal data boundaries, human review
  ├── policies/soft/               <- advisory conventions (WARN only)
  │   ├── style.md                 <- conventional commits, ruff, uv
  ���   ├── docs.md                  <- README standards, auto-doc markers
  │   └── llm-prompts.md           <- provider declaration, local-first for sensitive data
  ├── registries/                  <- typed metadata
  │   ├── repos.yaml               <- 21 repos with category, language, priority, secrets profile
  │   ├── secrets.schema.yaml      <- per-profile required/optional env vars, forbidden files
  │   ├── agents.yaml              <- per-provider allowed/forbidden actions
  │   ├── providers.yaml           <- LLM provider models and use cases
  │   ├── vector-collections.yaml  <- collection ownership, access control, embedding models
  │   └── tools.yaml               <- required/recommended tooling
  ├── templates/                   <- standard files synced to managed repos
  ├── scripts/                     <- enforcement and reporting
  └── adr/                         <- architectural decision records
```

### Hard vs soft

This is the key distinction. It maps to INTENT.md Section 2 principle: "explicit over implicit."

| Type | Severity | What happens | Example |
|------|----------|-------------|---------|
| **Hard policy** | `ERROR` | Blocks commit, push, or deploy. Must be fixed. | `.env` committed to git |
| **Soft policy** | `WARN` | Flagged in audit. Fix when convenient. | README under 50 characters |
| **Info** | `INFO` | Noted for awareness. No action required. | `scripts/dev.sh` missing |

Hard policies correspond to INTENT.md Section 4 (Repo Boundaries) — they cannot be relaxed by local overrides. Soft policies can be adjusted per-repo via `.control/policy-overrides.yaml`.

## Quick start

```bash
# Clone and install
git clone https://github.com/jthorvaldur/policy-orchestrator
cd policy-orchestrator
uv sync

# See what you're managing
devctl list
devctl list --category=legal

# Check the state of everything
devctl status
devctl status --dirty
```

## Testing and enforcement

### 1. Audit: are repos structurally compliant?

```bash
# Audit all repos for required files, forbidden files, git state
devctl audit

# Audit a single repo
devctl audit --repo=vpin
```

Checks for:
- Missing required files (`README.md`, `.gitignore`)
- Missing recommended files (`CLAUDE.md`, `.env.example`)
- Forbidden files committed (`.env`, `secrets.json`, private keys)
- Dirty git trees, missing upstream remotes
- Missing `.control/repo.yaml` contract
- Missing `scripts/` directory and standard scripts

### 2. Secrets: is anything leaking?

```bash
# Check all repos for secret hygiene
devctl secrets

# Check one repo
devctl secrets --repo=words_quantum_legal
```

Checks for:
- Forbidden files tracked by git (`.env`, `credentials.json`, `*.pem`, etc.)
- Secret patterns in tracked files (API keys, private keys, AWS credentials, Slack tokens)
- Missing `.env.example` for repos with a declared secret profile
- `gitleaks` scan (if installed — `brew install gitleaks`)

### 3. Policy lint: do repos follow the rules?

```bash
# Lint all repos against hard and soft policies
devctl policy

# Lint one repo
devctl policy --repo=Escher
```

Checks for:
- `.gitignore` exists and excludes `.env` (hard: secrets policy)
- No API keys in `CLAUDE.md` (hard: secrets policy)
- `README.md` exists and has substance (soft: docs policy)
- Python repos have `pyproject.toml` (soft: style policy)
- LLM-using repos declare providers in `.control/repo.yaml` (soft: llm-prompts policy)

### 4. Status: what's the operational state?

```bash
# All repos — branch, clean/dirty, unpushed commits
devctl status

# Only repos with uncommitted changes
devctl status --dirty

# Filter by category
devctl status --category=legal
```

## The repo contract

Every managed repo gets a standard contract. This is how the control plane knows what a repo is, what it needs, and what it's allowed to do — without understanding its code.

```
repo/
├── INTENT.md              <- inherited from control plane (or INTENT.local.md override)
├── CLAUDE.md              <- agent instructions
├── README.md              <- human instructions
├── .gitignore             <- must exclude .env, secrets, local state
├── .env.example           <- documents required secret names (no values)
├── .control/
│   ├── repo.yaml          <- metadata: language, category, visibility, providers, hooks
│   └── policy-overrides.yaml  <- optional: relax soft policies (hard policies cannot be relaxed)
└── scripts/
    ├── dev.sh             <- start development environment
    ├── test.sh            <- run tests
    └── on_update.sh       <- idempotent update hook (safe to run repeatedly)
```

### repo.yaml example

```yaml
name: words_quantum_legal
language:
  primary: python
category: legal
owner: joel
visibility: public
uses:
  vector_db: true
  llm_agents: true
allowed_llm_providers:
  - anthropic
  - local_ollama
required_files:
  - README.md
  - CLAUDE.md
  - .env.example
forbidden_files:
  - .env
  - secrets.json
```

## Policy enforcement flow

```
Developer or agent makes a change
        │
        ▼
  Pre-commit hook ──── gitleaks scan ──── forbidden file check
        │
        ▼
  Pre-push hook ─────── no force-push to main ──── clean tree check
        │
        ▼
  CI (GitHub Actions) ── gitleaks action ──── ruff lint ──── tests
        │
        ▼
  devctl audit ────────── periodic full audit across all repos
        │
        ▼
  devctl policy ───────── policy lint with ERROR/WARN/INFO classification
```

Each layer catches different things. Hooks catch at commit time. CI catches on push. `devctl` catches drift over time.

## Decision principles

From [INTENT.md](INTENT.md) Section 2, applied to this control plane:

1. **Simpler over complex.** `devctl` is a thin CLI over simple Python scripts. No ORM, no database, no daemon.
2. **Explicit over implicit.** Every repo's contract is declared in `.control/repo.yaml`. No convention-based magic.
3. **Composable over monolithic.** Each script does one thing. `repo_status`, `repo_audit`, `secrets_check`, `policy_lint` are independent.
4. **Auditable over opaque.** Policies are markdown files. Registries are YAML. Everything is version-controlled and human-readable.
5. **Repo-local autonomy with central policy inheritance.** Repos own their code. The control plane owns governance.
6. **One source of truth.** Agent contracts in `registries/agents.yaml` generate per-repo instruction files. Secret schemas in one place.
7. **Reversible over permanent.** Scripts suggest changes. They do not silently bulldoze state.

## Managed repositories

21 active repos across 6 categories. Full registry in [`registries/repos.yaml`](registries/repos.yaml).

| Category | Repos | Priority |
|----------|-------|----------|
| **Legal** | words_quantum_legal, div_legal, legal-tax-ops, morpheme-page | critical/active |
| **Quant/Finance** | vpin, alpha_research, ts_embed, cyfopt | active |
| **AI/Agents** | cortex, puffin, open-multi-agent-fork, vector-lab, joel-knowledge, llm-router | active |
| **Creative/Math** | Escher, darkgallery | active |
| **Web/Portfolio** | jthorvaldur.github.io, bulldogs | active |
| **Infrastructure** | policy-orchestrator, contacts, d72 | critical/active |

## Adding a new repo

1. Add entry to `registries/repos.yaml`
2. Clone the repo locally
3. Copy `.control/repo.yaml` template and fill in metadata
4. Copy `CLAUDE.md`, `.gitignore`, `.env.example` templates
5. Run `devctl audit --repo=<name>` to verify compliance
6. Run `devctl secrets --repo=<name>` to check for leaks

## Architecture

See [`adr/0001-control-plane-architecture.md`](adr/0001-control-plane-architecture.md) for the full decision record.

**Key choice:** Hub-and-spoke, not monorepo. Code stays distributed. Policy, metadata, and enforcement are centralized.

```
                    ┌─────────────────────┐
                    │ policy-orchestrator  │
                    │   (control plane)    │
                    │                      │
                    │  policies/           │
                    │  registries/         │
                    │  templates/          │
                    │  scripts/            │
                    └──────────┬───────────┘
                               │
            ┌──────────────────┼─��────────────────┐
            │                  │                   │
     ��──────┴──────┐   ┌──────┴──────┐    ┌��─────┴────��─┐
     │  repo A     │   │  repo B     │    │  repo C     │
     │ .control/   │   │ .control/   │    │ .control/   │
     │ CLAUDE.md   │   │ CLAUDE.md   │    │ CLAUDE.md   │
     │ scripts/    │   ��� scripts/    │    │ scripts/    │
     └─────────────┘   └─────────────┘    └��────────────┘
```
