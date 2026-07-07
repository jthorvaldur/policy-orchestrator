# Agent Operating Processes

Model-agnostic processes for running AI agents against any repo in this
control plane. Each process answers the audit question: **"Which file
enforces this tomorrow?"** If a rule lives only in a chat session, it does
not exist.

## The processes

| # | Process | Enforced by |
|---|---------|-------------|
| 1 | [Outside audit](01-outside-audit.md) | `session-routing-audit.sh` hook + `repo_audit.py` |
| 2 | [Chief operator](02-chief-operator.md) | `contracts/agents.yaml` (operator contract) |
| 3 | [Agent team contracts](03-agent-team-contracts.md) | `contracts/agents.yaml` |
| 4 | [Hooks over instructions](04-hooks-over-instructions.md) | `.claude/settings.json` + `.claude/hooks/` |
| 5 | [Improvement loop](05-improvement-loop.md) | `evals/` + `scripts/test.sh` + delivery-gate hook |
| 6 | [Model routing](06-model-routing.md) | `contracts/model-routing.yaml` |

## Design rules

- **Processes are provider-neutral.** Contracts and routing are defined by
  *role and tier*, not by model name. Bindings map roles to each provider
  (Anthropic, OpenAI, Google, local Ollama).
- **Hooks enforce; instructions advise.** Anything that must always happen
  goes in a hook or a script, never in prose.
- **Failures become evals, not memory notes.** See process 5.
- **Context is loaded on demand.** Sessions start with intent + routing
  only; process docs are read when the work touches them.

## Installation

This pack is distributed by policy-orchestrator:

```bash
devctl sync --agent-processes --repo <name> --dry-run   # preview
devctl sync --agent-processes --repo <name>             # install (never overwrites)
devctl audit --repo=<name>                              # verify
```

New repos get it automatically via `scripts/init_repo.py`. Per-repo
overrides: `contracts/*.local.yaml`, same precedence rules as
`INTENT.local.md`. Reference-priority repos are not audited for the pack.
