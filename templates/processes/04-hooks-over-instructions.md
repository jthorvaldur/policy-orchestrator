# Process 4 — Hooks Over Instructions

**Problem:** adding more prose to CLAUDE.md when behavior drifts. Prose is
advisory; agents under context pressure drop it.

**Rule:** when a behavior must *always* happen, implement it as a hook (or
script/CI check). Instructions explain; hooks enforce.

## The hook catalog

| Hook | Event | What it enforces |
|------|-------|------------------|
| Session routing audit | SessionStart | Injects intent, routing table, and a reality-check of required files (process 1) |
| Pre-tool risk guard | PreToolUse | Blocks forbidden operations before they run: force-push to main, writes to `.env`/secret files, destructive shell patterns |
| Post-tool evidence logger | PostToolUse | Appends every tool action to a session evidence log — the raw material for delivery gates and evals |
| Delivery gate | Stop | No "done" without proof: if the tree is dirty and no test/eval ran this session, the agent is bounced back once to verify or explicitly justify |
| Pre-compact handoff writer | PreCompact | Writes a handoff artifact (git state + evidence tail) so post-compact sessions resume from facts, not vibes |
| Budget governor | PostToolUse (counter) | Warns when tool-call volume passes thresholds — runaway loops surface early |

Reference implementations: `.claude/hooks/*.sh`, wired in
`.claude/settings.json`. All are plain bash + python3 stdlib — portable to
any harness that supports lifecycle hooks; for harnesses that don't, the
same checks run as `scripts/test.sh` + CI.

## Promotion rule

When the same instruction is violated twice, promote it:

```
prose (CLAUDE.md) → hook (blocking) or eval (detecting)
```

Log the promotion in the improvement loop (process 5).

## Enforced by

- `.claude/settings.json` — the wiring; if a hook isn't wired here, it
  doesn't exist.
