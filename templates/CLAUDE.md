# {{PROJECT_NAME}}

> Read `INTENT.md` before acting. It governs all work in this repo.

## Project Overview
{{PROJECT_DESCRIPTION}}

## Language & Stack
- Primary: {{PRIMARY_LANGUAGE}}
- Package manager: {{PACKAGE_MANAGER}}

## Policies
This repo is managed by the [policy-orchestrator](https://github.com/jthorvaldur/policy-orchestrator) control plane.

### Hard policies (enforced — cannot be relaxed)
- Never commit .env or secret files
- No force push to main
- No LLM-generated legal filings without human review
- No files outside this repo's declared scope

### Soft policies (advisory — can be overridden in .control/policy-overrides.yaml)
- Use conventional commits
- Keep README current with install + usage sections
- Declare LLM providers in .control/repo.yaml

## Agent Protocol (from INTENT.md)
- Identify the relevant repo intent before producing output
- Preserve existing conventions unless explicitly changing them
- Do not modify files outside scope
- Do not introduce secrets into tracked files
- Do not duplicate functionality handled by another repo
- Provide validation steps after changes
- Flag uncertainty:
  ```
  Uncertainty: [what is unknown]
  Assumption: [what is being assumed]
  Implication: [what breaks if the assumption is wrong]
  ```

## Repo Contract
- Read `.control/repo.yaml` for repo metadata and constraints
- Check `.env.example` for required environment variables
- Run `scripts/test.sh` before suggesting changes are complete
- Do not modify files in `.control/` without explicit instruction

## Scripts
- `scripts/dev.sh` — start development environment
- `scripts/test.sh` — run tests
- `scripts/build.sh` — build project
- `scripts/lint.sh` — run linting
- `scripts/docs.sh` — regenerate documentation
- `scripts/on_update.sh` — idempotent update hook
