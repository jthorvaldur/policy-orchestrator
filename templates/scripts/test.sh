#!/usr/bin/env bash
# Run tests + all evals. Required by .control/repo.yaml and the delivery gate.
set -euo pipefail
cd "$(dirname "$0")/.."

status=0

if compgen -G "tests/*.py" > /dev/null; then
  uv run pytest -q || status=1
fi

for e in evals/e*.sh; do
  [[ -f $e ]] || continue
  if bash "$e"; then
    echo "eval PASS: $e"
  else
    echo "eval FAIL: $e"
    status=1
  fi
done

exit $status
