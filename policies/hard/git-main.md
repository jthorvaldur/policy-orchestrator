# Policy: Git Main Branch Protection (HARD)

**Severity:** ERROR — blocks action

## Rules

1. **No force push to main.** The `main` branch is append-only. History rewriting is forbidden.
2. **No deploy from dirty tree.** Production deploys require a clean `git status` on a tagged commit.
3. **No direct commits to main on shared repos.** Use feature branches and pull requests for repos with more than one contributor or active CI.
4. **Commit messages must be meaningful.** No empty messages, no `WIP` on main, no `fix fix fix` chains.

## Enforcement

- Pre-push hook: reject `--force` to main
- CI: verify clean tree on deploy
- `devctl audit` checks for dirty trees and unpushed changes
