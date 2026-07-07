#!/usr/bin/env bash
# PostToolUse (all tools) — append one evidence line per tool action.
# The log feeds the delivery gate, handoff writer, and improvement loop.
# Also acts as budget governor: warns every 50 tool calls.
set -euo pipefail
cd "$(dirname "$0")/../.."
mkdir -p .claude/state
# Self-ignoring: keep session state out of git (and out of auto-commit sweeps).
[[ -f .claude/state/.gitignore ]] || echo '*' > .claude/state/.gitignore

# Heredoc occupies stdin, so capture the hook payload into an env var first.
HOOK_INPUT=$(cat) python3 - <<'PY'
import json, sys, datetime, os

data = json.loads(os.environ.get("HOOK_INPUT") or "{}")
sid = (data.get("session_id") or "unknown")[:8]
tool = data.get("tool_name", "?")
ti = data.get("tool_input", {}) or {}
detail = ti.get("command") or ti.get("file_path") or ti.get("prompt") or ""
detail = " ".join(str(detail).split())[:160]
ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

path = f".claude/state/evidence-{sid}.log"
with open(path, "a") as f:
    f.write(f"{ts} | {tool} | {detail}\n")

# Budget governor: loud line every 50 calls so runaway loops surface early.
n = sum(1 for _ in open(path))
if n and n % 50 == 0:
    print(f"budget-governor: {n} tool calls this session — check for loops/scope creep", file=sys.stderr)
PY
exit 0
