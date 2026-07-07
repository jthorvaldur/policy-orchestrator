#!/usr/bin/env bash
# PreCompact — write a handoff artifact so the post-compact session resumes
# from facts (git state + recent evidence), not from summary vibes.
# Pairs with the control-plane post-compact-reinject.sh template.
set -euo pipefail
cd "$(dirname "$0")/../.."
mkdir -p .claude/state
# Self-ignoring: keep session state out of git (and out of auto-commit sweeps).
[[ -f .claude/state/.gitignore ]] || echo '*' > .claude/state/.gitignore

sid=$(python3 -c 'import json,sys; print((json.load(sys.stdin).get("session_id") or "unknown")[:8])')
out=".claude/state/handoff.md"

{
  echo "# Handoff (pre-compact) — $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo
  echo "## Git state"
  echo '```'
  git status --short --branch
  echo '```'
  echo
  echo "## Last 25 tool actions"
  echo '```'
  tail -n 25 ".claude/state/evidence-${sid}.log" 2>/dev/null || echo "(no evidence log)"
  echo '```'
  echo
  echo "Resume rule: verify claims above against the tree before continuing."
} > "$out"

echo "pre-compact-handoff: wrote $out"
