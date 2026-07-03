#!/usr/bin/env bash
# SessionStart hook (control-plane template) — inject the repo's governing md
# files into every agent session so they are read, not merely present.
# Injects INTENT[.local].md and policies/hard/* when they exist; falls back to
# CLAUDE.md so no managed repo starts a session contextless.
set -euo pipefail
cd "$(dirname "$0")/../.."

echo "<repo-intent>"
if [[ -f INTENT.md ]]; then
  cat INTENT.md
elif [[ -f CLAUDE.md ]]; then
  cat CLAUDE.md
fi
if [[ -f INTENT.local.md ]]; then
  echo ""
  echo "--- INTENT.local.md (machine-local overrides) ---"
  cat INTENT.local.md
fi
if compgen -G "policies/hard/*.md" > /dev/null; then
  echo ""
  echo "--- HARD POLICIES (non-relaxable) ---"
  for f in policies/hard/*.md; do
    echo ""
    cat "$f"
  done
fi
echo "</repo-intent>"
