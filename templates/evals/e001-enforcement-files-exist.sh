#!/usr/bin/env bash
# eval: instructions claimed in docs must have an enforcing file (process 1)
# date: 2026-07-07 | failure: rules lived only in chat/prose | root cause: no
# enforcement layer | patch: hooks + contracts pack | next: sync via
# policy-orchestrator to all repos
set -euo pipefail
cd "$(dirname "$0")/.."

fail=0
for f in contracts/agents.yaml contracts/model-routing.yaml \
         .claude/settings.json \
         .claude/hooks/session-routing-audit.sh \
         .claude/hooks/pre-tool-risk-guard.sh \
         .claude/hooks/post-tool-evidence-logger.sh \
         .claude/hooks/delivery-gate.sh \
         .claude/hooks/pre-compact-handoff.sh \
         scripts/test.sh; do
  if [[ ! -f $f ]]; then echo "FAIL: missing enforcing file $f"; fail=1; fi
done
for h in .claude/hooks/*.sh; do
  if [[ ! -x $h ]]; then echo "FAIL: $h not executable"; fail=1; fi
done
# Hooks must parse (bash -n) so a broken hook can't silently disable enforcement.
for h in .claude/hooks/*.sh; do
  bash -n "$h" || { echo "FAIL: $h has syntax errors"; fail=1; }
done

[[ $fail -eq 0 ]] && echo "PASS: all enforcement files present, executable, and parseable"
exit $fail
