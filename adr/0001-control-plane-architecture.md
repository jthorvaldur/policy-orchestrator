# ADR 0001: Control Plane Architecture

## Status
Accepted

## Date
2026-04-27

## Context
Managing 43 GitHub repositories (and growing) requires centralized policy enforcement, secrets hygiene, agent behavior contracts, and cross-repo coordination. Without a control plane, each repo independently drifts on conventions, secrets management, documentation standards, and agent instructions.

## Decision
Adopt a **hub-and-spoke control plane** architecture:

- **Hub**: `policy-orchestrator` repo contains all policies, registries, templates, scripts, and ADRs
- **Spokes**: Each managed repo gets a `.control/repo.yaml` contract and standardized files (CLAUDE.md, .env.example, scripts/)
- **No monorepo**: Code stays in individual repos. The control plane centralizes policy, metadata, and health checks only.

### Key design choices:
1. **Typed repo registry** (`registries/repos.yaml`) over flat repo lists — supports filtering by category, priority, language
2. **Hard/soft policy separation** — hard policies (secrets, git-main) block actions; soft policies (style, docs) warn only
3. **Secrets schema** — unified `.env.example` and forbidden-file patterns across all repos
4. **Provider-neutral agent specs** — single source of truth generates CLAUDE.md, CODEX.md, AGENTS.md per repo
5. **Vector collection ownership** — explicit producers, consumers, and embedding model versioning

## Consequences
- Every repo must adopt the `.control/repo.yaml` contract to be managed
- Policy changes propagate from the control plane, not from individual repos
- Scripts must be idempotent — safe to run repeatedly without side effects
- The control plane does not contain application code — only governance infrastructure

## Alternatives Considered
- **Monorepo**: Rejected — too rigid, forces coupling between unrelated projects
- **GitHub App / bot**: Deferred to Phase 5+ — local-first approach is simpler to bootstrap
- **Just CLAUDE.md per repo**: Insufficient — doesn't scale past ~10 repos, no enforcement mechanism
