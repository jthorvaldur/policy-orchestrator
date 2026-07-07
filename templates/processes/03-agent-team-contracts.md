# Process 3 — Agent Team Contracts

**Problem:** either no delegation, or 30 vague subagents producing
"expensive fog."

**Rule:** a small, fixed team. Every subagent runs under a strict contract.
No contract, no spawn.

## The team (roles, not models)

| Role | Mission |
|------|---------|
| `chief-operator` | Decision maker and orchestrator (process 2) |
| `system-fixer` | Quick repairs to agents, skills, hooks, contracts |
| `builder` | The actual implementation work |
| `qa-engineer` | Verifies with evidence — returns PASS/FAIL, never "looks good" |
| `adversarial-critic` | Calls out fake progress, bloat, weak handoffs |
| `improvement-analyst` | Turns recurring failures into evals and patches (process 5) |
| `context-librarian` | Keeps intent files, contracts, and references current and small |

## Contract schema (every spawn must satisfy)

```yaml
mission:     # one sentence — what outcome this agent owns
scope:       # files/dirs it may touch; everything else is out of bounds
inputs:      # exactly what context it is given (no "read everything")
output_limit:  # max size/shape of its return (e.g. "≤30 lines, structured")
evidence:    # what proof must accompany any claim of completion
model_tier:  # worker | operator | frontier  (resolved via process 6)
```

A subagent that returns without its required evidence is treated as FAILED,
not as done.

## Machine-readable source of truth

`contracts/agents.yaml` in this pack defines the team. Provider bindings
(Claude Code agent files, CODEX.md sections, GEMINI.md sections) are
*generated views* of that file — edit the contract, not the view.

## Enforced by

- `contracts/agents.yaml` — the contracts.
- `.claude/hooks/delivery-gate.sh` — blocks "done" without evidence at the
  session level (same rule the qa-engineer applies per-task).
