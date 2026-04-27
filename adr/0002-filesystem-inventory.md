# ADR 0002: Filesystem Repository Inventory

## Status
Accepted

## Date
2026-04-27

## Context
The control plane manages 21 active repos via `registries/repos.yaml`, but 297 git repos exist across the filesystem in 5+ locations (`~/GitHub/`, `~/projects/`, `~/ruv_repos/`, `~/`, and others). Many are untracked, some are duplicates, some have no remote (data loss risk), and ~180 are third-party reference clones. We need visibility before any consolidation.

## Decision

### Separate inventory from active registry
- `registries/repos.yaml` remains the curated list of repos the user actively manages (high signal, specific fields like secret_profile, vector_namespace)
- `registries/inventory.yaml` is a machine-generated snapshot of all personal and work repos on the filesystem
- `registries/reference-repos.yaml` tracks third-party reference clones separately

This follows INTENT.md principle 6: "One source of truth over repeated configuration." These are different truths: "what do I manage" vs "what exists on disk."

### Lifecycle taxonomy
Nine categories, each with programmatic detection rules:

| Category | Meaning | Detection |
|----------|---------|-----------|
| active | Owned, has remote, recent activity | jthorvaldur org, remote, commits, <6 months old |
| work-org | Work organization repos | EislerSysJT in remote URL |
| reference | Third-party clones, not owned | Remote org not in user's orgs |
| duplicate | Copy of a repo that exists elsewhere | Same normalized remote URL at multiple paths |
| backup | Explicit backup or archived copy | Path contains backup/old_ patterns |
| orphan | Has commits but no remote | Commits present, no remote configured |
| empty | git init with no commits | Zero commits |
| dependency | Tool-managed clones | Under .vim/plugged/, .codex/, .nvm/, etc. |
| stale | Owned but inactive >12 months | Personal org, remote, no commits in 12+ months |

### Risk assessment
- **critical**: No remote + commits + (legal data OR 20+ commits)
- **high**: No remote + commits + 5+ commits
- **medium**: Behind remote, or dirty with unpushed work
- **low**: Clean, remote, up to date

### Scan strategy
Depth-limited filesystem walk with skip lists for macOS system dirs, package caches, and build artifacts. Dedicated roots scanned at different depths to handle nested project structures.

## Consequences
- `devctl discover` provides complete filesystem visibility without modifying any repo
- Risk flagging surfaces data loss hazards (especially `~/legal` which has no remote)
- Duplicate detection prevents wasted effort maintaining multiple copies
- Cross-reference with `repos.yaml` identifies registry inaccuracies
- Reference repos (ruv_repos) are tracked but don't pollute the active registry
