# INTENT.md

> **Version:** 0.2.0
> **Scope:** All repositories. Repo-local overrides go in `INTENT.local.md`.
> **Audience:** Every agent — human, AI, or automated — that reads or writes in this repo.

---

## Prime Directive

Maximize alignment with repository intent. Not output volume.

---

## 1. Operating Rules

**Signal over noise.** Every output — code, docs, commits, responses — must be directly relevant, logically consistent, and actionable. Remove anything that merely appears useful.

**Internal consistency.** Before producing or accepting work, verify it does not contradict the repo's purpose, prior architectural decisions, or existing conventions. Resolve contradictions before proceeding.

**No drift.** If work begins to generalize, lose specificity, duplicate existing mechanisms, or expand beyond scope — stop. Correct before continuing.

**Flag uncertainty.** State what is unknown. Name the assumption. Do not present guesses as facts.

```
Uncertainty: [what is unknown]
Assumption: [what is being assumed]
Implication: [what breaks if the assumption is wrong]
```

---

## 2. Decision Principles

When choosing between designs, prefer — in order:

1. Simpler over complex.
2. Explicit over implicit.
3. Composable over monolithic.
4. Auditable over opaque.
5. Repo-local autonomy with central policy inheritance.
6. One source of truth over repeated configuration.
7. Reversible over permanent (unless permanence is required).

---

## 3. Output Structure

Default:

```
Key Insight -> Supporting Logic -> Clear Conclusion
```

Technical changes:

```
Problem -> Decision -> Implementation -> Validation -> Remaining Risk
```

Every substantial output ends with either:

```
Clear Conclusion: [what was decided or changed]
```

or

```
Next Action: [what must happen next]
```

---

## 4. Repo Boundaries

This repository must not become:

- A dumping ground for unrelated ideas.
- A duplicate of another repo's responsibility.
- A mix of policy, secrets, scripts, and docs without clear boundaries.
- A source of hidden behavior that cannot be audited.

Every file should answer:

```
Why does this belong here?
What system reads or enforces it?
What happens if it changes?
```

---

## 5. Agent Protocol

Applies to all AI assistants, code generators, and automated tooling:

- Read this file before acting.
- Identify the relevant repo intent before producing output.
- Preserve existing conventions unless explicitly changing them.
- Do not modify files outside scope.
- Do not introduce secrets into tracked files.
- Do not duplicate functionality handled by another repo.
- Provide validation steps after changes.
- Explain only what is needed.

---

## Override Mechanism

Repos may extend or narrow these rules via `INTENT.local.md` in the repo root. Local intent inherits from this file. Conflicts resolve in favor of the local file, except for Section 4 (Repo Boundaries), which cannot be relaxed.

---
