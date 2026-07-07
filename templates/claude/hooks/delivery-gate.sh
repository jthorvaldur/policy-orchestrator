#!/usr/bin/env bash
# Stop — no fake "done" without proof. If the working tree has changes and
# no test/eval evidence exists this session, bounce the agent back once to
# verify (or explicitly justify skipping). Exit 2 = block stop.
set -euo pipefail
cd "$(dirname "$0")/../.."

# Heredoc occupies stdin, so capture the hook payload into an env var first.
HOOK_INPUT=$(cat) python3 - <<'PY'
import json, sys, subprocess, os

data = json.loads(os.environ.get("HOOK_INPUT") or "{}")
# Never loop: if we already blocked once, let the stop through.
if data.get("stop_hook_active"):
    sys.exit(0)

sid = (data.get("session_id") or "unknown")[:8]

dirty = subprocess.run(
    ["git", "status", "--porcelain", "--untracked-files=no"],
    capture_output=True, text=True).stdout.strip()
if not dirty:
    sys.exit(0)  # nothing changed; nothing to prove

log = f".claude/state/evidence-{sid}.log"
evidence = ""
if os.path.exists(log):
    evidence = open(log).read()

markers = ("scripts/test.sh", "pytest", "evals/", "npm test", "cargo test", "go test")
if any(m in evidence for m in markers):
    sys.exit(0)

print(
    "delivery-gate: tracked files were modified but no test/eval ran this "
    "session. Run scripts/test.sh (or the relevant check) and report the "
    "result — or state explicitly why verification is not applicable.",
    file=sys.stderr)
sys.exit(2)
PY
