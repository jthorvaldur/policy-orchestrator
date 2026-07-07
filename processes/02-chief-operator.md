# Process 2 — Chief Operator

**Problem:** one giant session that does everything: bloated context,
undelegated work, no handoffs, quality collapse near compaction.

**Rule:** the main session is an *operator*, not a worker. It understands
the big picture, breaks work into microtasks, delegates to contracted
subagents (process 3), makes decisions, patches the system when it breaks
(process 5), and writes handoffs before context is lost.

## Operator contract (provider-neutral)

- **Mission:** deliver the user's outcome; own decisions and integration.
- **Does:** decompose, route (process 6), delegate, verify evidence,
  decide, write handoffs, patch hooks/contracts when they misfire.
- **Does not:** grind through large mechanical edits, read entire files
  a worker could summarize, or hold every skill in context.
- **Core prompt stays short.** Routing and memory rules live in
  `contracts/`, injected by hook — not restated in prose.

## Context discipline (stop preloading everything)

- Preload only: repo intent (hook-injected), routing table, and the
  operator contract.
- Everything else — process docs, skills, domain references — is loaded
  **on demand** when the task touches it.
- If session context is drowning in unused material, that is a system bug:
  patch the hook or template that preloaded it (process 5).

## Launch pattern

```bash
# Anthropic (Claude Code)
claude --model <operator-tier model>        # tier defined in contracts/model-routing.yaml

# Other providers: run the harness with the operator instruction file
# (CODEX.md / GEMINI.md), same contract, same routing table.
```

## Enforced by

- `contracts/agents.yaml` — the operator contract (mission/scope/limits).
- `.claude/hooks/session-routing-audit.sh` — injects routing + contract
  summary at session start, so the operator never relies on memory for it.
- `.claude/hooks/pre-compact-handoff.sh` — forces a handoff artifact before
  compaction.
