# Process 5 — Improvement Loop (Failures → Evals)

**Problem:** the same annoyance recurs; each time it gets a memory note or
another paragraph of instructions. Neither prevents the next occurrence.

**Rule:** every *repeated* failure becomes an eval — an executable check
that fails while the problem exists and passes when it is fixed. Memory
notes are for context; evals are for prevention.

## The loop

```
failure observed
  → root cause (one sentence)
  → system patch (hook, contract, script, or template change)
  → eval added under evals/ that would have caught it
  → memory entry (one line, operational format below)
  → next action
```

Frontier-tier models (process 6) run this loop: audits, root-cause
analysis, adversarial review of the patch. Worker tiers do not design
system changes.

## Memory discipline — short and operational

One line per event, machine-scannable. No narrative, no diary.

```
2026-07-07 | delivery claimed without tests | Stop had no gate | added delivery-gate.sh | evals/e001-delivery-gate.sh | watch recurrence 2wk
  date     | failure                        | root cause       | system patch          | eval                        | next
```

Cross-repo: also log via the existing calibration store —
`devctl log-feedback --type correction --signal "<failure>" --rule "<patch>"`
so `feedback_events` (Qdrant) carries it to every repo's session start.

## Eval format

`evals/eNNN-<slug>.sh` — exits 0 = pass, non-zero = fail, prints one line of
evidence either way. `scripts/test.sh` runs all evals; the delivery gate
(process 4) requires that run before "done."

## Enforced by

- `evals/` + `scripts/test.sh` — the checks themselves.
- `.claude/hooks/delivery-gate.sh` — makes skipping the checks loud.
