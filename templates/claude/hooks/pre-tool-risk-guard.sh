#!/usr/bin/env bash
# PreToolUse (Bash|Write|Edit) — block forbidden operations before they run.
# Exit 2 = deny, stderr is fed back to the agent. Everything else passes.
set -euo pipefail

# Heredoc occupies stdin, so capture the hook payload into an env var first.
HOOK_INPUT=$(cat) python3 - <<'PY'
import json, os, re, sys

data = json.loads(os.environ.get("HOOK_INPUT") or "{}")
tool = data.get("tool_name", "")
ti = data.get("tool_input", {}) or {}

def deny(msg):
    print(f"BLOCKED by pre-tool-risk-guard: {msg}", file=sys.stderr)
    sys.exit(2)

# Forbidden target files (mirror .control/repo.yaml: forbidden_files)
FORBIDDEN_FILES = re.compile(r"(^|/)(\.env|secrets\.json|id_rsa|service_account\.json)$")

if tool in ("Write", "Edit"):
    path = ti.get("file_path", "")
    if FORBIDDEN_FILES.search(path):
        deny(f"writes to secret file '{path}' are forbidden (hard policy)")

if tool == "Bash":
    cmd = ti.get("command", "")
    checks = [
        (r"push\s+.*(--force|-f)\b.*\b(main|master)\b", "force push to main"),
        (r"push\s+.*\b(main|master)\b.*(--force|-f)\b", "force push to main"),
        (r"rm\s+(-[a-z]*r[a-z]*f|-[a-z]*f[a-z]*r)[a-z]*\s+(/|~|\$HOME)(\s|$)", "recursive delete of / or home"),
        (r"git\s+add\s+.*(^|[\s/])\.env(\s|$)", "staging .env"),
        (r">\s*\.env(\s|$)", "redirect into .env"),
        (r"curl[^|;&]*\|\s*(ba)?sh", "piping curl to shell"),
    ]
    for pat, why in checks:
        if re.search(pat, cmd):
            deny(f"{why}: `{cmd[:120]}`")

sys.exit(0)
PY
