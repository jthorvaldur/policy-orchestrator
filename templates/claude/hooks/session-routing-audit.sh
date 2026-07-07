#!/usr/bin/env bash
# SessionStart — inject model routing and run a reality check on required
# enforcement files (processes/01-outside-audit.md).
# Intent injection is handled by session-start-intent.sh (runs first).
set -euo pipefail
cd "$(dirname "$0")/../.."

if [[ -f contracts/model-routing.yaml ]]; then
  echo "<model-routing>"
  cat contracts/model-routing.yaml
  echo "</model-routing>"
fi

# Outside audit, steps 1-2: report gaps loudly instead of pretending.
echo "<enforcement-audit>"
missing=0
for f in contracts/agents.yaml contracts/model-routing.yaml .claude/settings.json scripts/test.sh evals; do
  if [[ ! -e $f ]]; then echo "GAP: $f missing — behavior it enforces does not exist"; missing=1; fi
done
[[ $missing -eq 0 ]] && echo "OK: enforcement files present"
echo "Rule: for any claimed behavior, ask 'which file enforces this tomorrow?'"
echo "</enforcement-audit>"
