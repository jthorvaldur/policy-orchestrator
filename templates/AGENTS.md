# {{PROJECT_NAME}} — Agent Instructions

## For All Agents
- This repo is part of the jthorvaldur development ecosystem
- Managed by [policy-orchestrator](https://github.com/jthorvaldur/policy-orchestrator)
- Check `.control/repo.yaml` for repo metadata and constraints

## Allowed Actions
- Read any file
- Edit source files
- Run tests via `scripts/test.sh`
- Generate documentation

## Forbidden Actions
- Never commit .env, secrets, or credentials
- Never force push to main
- Never rewrite git history
- Never deploy to production without explicit human approval
- Never process legal filings without human review flag

## Required Before Completing Work
1. Run `scripts/test.sh` if it exists
2. Run `scripts/lint.sh` if it exists
3. Verify no secrets in staged changes
