# Process 6 — Model Routing

**Problem:** one model for everything — either the frontier model burns
budget on mechanical edits, or a small model silently makes architecture
decisions.

**Rule:** route by *role tier*, not by habit. Tiers are provider-neutral;
`contracts/model-routing.yaml` maps each tier to concrete models per
provider and is the single source of truth.

## Tiers

| Tier | Used for | Never used for |
|------|----------|----------------|
| `frontier` | System audits, root-cause analysis, architecture, adversarial review, improvement loops (process 5) | High-volume mechanical work |
| `operator` | The disciplined chief-operator session (process 2) | — |
| `worker` | Bounded, contracted subagent tasks: implementation, search, summarization, QA runs | Architecture or system-patch decisions |
| `local` | Free/offline extraction, classification, embedding-adjacent chores | Anything requiring judgment that will be acted on unverified |

## The loop worth protecting

```
frontier audits the system
  → operator runs the work through contracted workers
  → failures feed evals (process 5)
  → frontier reviews the patches adversarially
```

## Escalation rule

A worker that hits ambiguity outside its contract does not improvise — it
returns the question. The operator resolves it or escalates to frontier.
Cost priority for bulk extraction stays: local (free) → cheap API →
frontier (last resort).

## Enforced by

- `contracts/model-routing.yaml` — the mapping; injected at session start
  by `session-routing-audit.sh` so routing never relies on recall.
