# Policy: Legal Data Handling (HARD)

**Severity:** ERROR — blocks action

## Rules

1. **No LLM-generated legal filings without human review.** Any output destined for court, regulatory, or contractual submission must be reviewed by a human before filing.
2. **Legal data stays in designated repos.** Legal documents, case files, and privileged communications belong in repos with `category: legal` only.
3. **Prefer local models for private legal material.** When processing sensitive legal content, prefer local Ollama models over cloud APIs unless explicitly authorized.
4. **No legal data in public repos.** Repos with `visibility: public` must never contain case-specific legal documents.
5. **Vector collections for legal data must have restricted access.** Legal vector namespaces must declare explicit `allowed_readers` — no `all` access.

## Enforcement

- `devctl audit --category legal` validates boundaries
- Vector registry checks access declarations
- Agent contracts forbid unsupervised legal output
