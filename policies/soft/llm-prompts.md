# Preference: LLM Usage (SOFT)

**Severity:** WARN — advisory

## Conventions

1. **Declare allowed LLM providers per repo** in `.control/repo.yaml`.
2. **Prefer local models for sensitive data.** Use Ollama or local inference for private legal, financial, or personal data when possible.
3. **Agent instructions should be provider-neutral at source.** Use `.agent-spec/base.md` as single source of truth, generate provider-specific files.
4. **No secret injection into prompts.** API keys and tokens must come from environment, never hardcoded in prompt templates.
5. **Log LLM usage for audit.** Repos using LLM agents should have a mechanism to track which models were used and for what.

## Enforcement

- `devctl audit` checks for declared providers
- Agent contract registry validates consistency
