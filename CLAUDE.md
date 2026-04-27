# policy-orchestrator

> Read `INTENT.md` first. It is the root authority for all work in this repo.

## Overview
Development control plane for the jthorvaldur multi-repo ecosystem. Centralizes policy enforcement, agent contracts, secrets hygiene, and cross-repo coordination across 21 active repositories.

## Architecture
- **Hub-and-spoke**: This repo is the hub. Each managed repo is a spoke with a `.control/repo.yaml` contract.
- **No application code here** — only governance: policies, registries, templates, scripts, ADRs.
- See `adr/0001-control-plane-architecture.md` for the full architectural decision record.

## INTENT.md integration
All policies derive from INTENT.md:
- **Section 1 (Operating Rules)** -> hard policies enforce "no drift" and "internal consistency"
- **Section 2 (Decision Principles)** -> design choices: explicit > implicit, composable > monolithic, auditable > opaque
- **Section 4 (Repo Boundaries)** -> hard policies — cannot be relaxed by local overrides
- **Section 5 (Agent Protocol)** -> agent contracts in registries/agents.yaml

## Key directories
- `INTENT.md` — root authority, governing document for all policies
- `policies/hard/` — enforced rules (ERROR): secrets, git-main, legal-data
- `policies/soft/` — advisory conventions (WARN): style, docs, llm-prompts
- `registries/` — repos.yaml, secrets.schema.yaml, agents.yaml, providers.yaml, vector-collections.yaml, tools.yaml
- `templates/` — standard files synced to managed repos
- `scripts/` — repo_status, repo_audit, secrets_check, policy_lint
- `adr/` — architectural decision records

## Commands
```bash
devctl list                          # list all registered repos
devctl status                        # git state of all repos
devctl status --dirty                # only dirty repos
devctl audit                         # structural compliance check
devctl audit --repo=vpin             # audit single repo
devctl secrets                       # secret hygiene check
devctl policy                        # policy lint (ERROR/WARN/INFO)
```

## Rules for agents working in this repo
1. Read `INTENT.md` before acting. Identify the relevant repo intent before producing output.
2. Never commit .env or secret files.
3. Never modify `registries/repos.yaml` without explicit instruction.
4. Policy files in `policies/hard/` must not be weakened without an ADR.
5. Templates are source-of-truth — changes here propagate to managed repos.
6. Scripts must be idempotent and non-destructive.
7. Flag uncertainty using the INTENT.md template:
   ```
   Uncertainty: [what is unknown]
   Assumption: [what is being assumed]
   Implication: [what breaks if the assumption is wrong]
   ```
8. Every file must answer: Why does this belong here? What system reads or enforces it? What happens if it changes?
