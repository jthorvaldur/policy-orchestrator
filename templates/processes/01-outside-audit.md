# Process 1 — Outside Audit

**Problem:** agents describe the setup you *wish* existed. Rules agreed in
chat evaporate when the session ends.

**Rule:** audit reality, not intention. For every claimed behavior, ask:

> **Which file enforces this tomorrow?**

If the answer is "nowhere," the behavior does not exist. Either write the
enforcing file or drop the claim.

## Procedure (any model, any repo)

Run at session start, before any substantive work, and on demand
("audit this repo"):

1. List what actually exists: `INTENT.md`, `CLAUDE.md` (or `CODEX.md` /
   `GEMINI.md`), `.control/repo.yaml`, `.claude/settings.json`,
   `.claude/hooks/`, `contracts/`, `evals/`, `scripts/test.sh`.
2. For each required file in `.control/repo.yaml: required_files` that is
   missing or empty, report it as a gap — do not silently work around it.
3. For each instruction in CLAUDE.md/INTENT.md, classify:
   - **Enforced** — a hook, script, or CI check makes violation impossible
     or loud.
   - **Advisory** — prose only. Candidate for promotion to a hook (process 4)
     or an eval (process 5).
4. Report gaps in the standard format:

```
Gap: [what is claimed but unenforced]
Enforcing file: [none | path]
Promotion: [hook | eval | script | drop]
```

## Enforced by

- `.claude/hooks/session-routing-audit.sh` — runs a lightweight version of
  steps 1–2 on every session start and injects the result into context.
- `policy-orchestrator/scripts/repo_audit.py` — cross-repo sweep.
