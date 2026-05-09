#!/usr/bin/env python3
"""Check repos for secret hygiene."""

import re
import subprocess
import sys
from pathlib import Path

import yaml

C = {
    "reset": "\033[0m", "bold": "\033[1m", "dim": "\033[90m",
    "green": "\033[32m", "yellow": "\033[33m", "red": "\033[31m",
    "cyan": "\033[36m",
}

# Patterns that suggest a secret value (not a variable name)
SECRET_PATTERNS = [
    (r"sk-[a-zA-Z0-9]{20,}", "OpenAI API key pattern"),
    (r"sk-ant-[a-zA-Z0-9\-]{20,}", "Anthropic API key pattern"),
    (r"ghp_[a-zA-Z0-9]{36}", "GitHub personal access token"),
    (r"gho_[a-zA-Z0-9]{36}", "GitHub OAuth token"),
    (r"github_pat_[a-zA-Z0-9_]{22,}", "GitHub fine-grained PAT"),
    (r"AIza[a-zA-Z0-9\-_]{35}", "Google API key pattern"),
    (r"-----BEGIN (RSA |EC |DSA )?PRIVATE KEY-----", "Private key"),
    (r"-----BEGIN CERTIFICATE-----", "Certificate"),
    (r"AKIA[0-9A-Z]{16}", "AWS access key"),
    (r"xox[bpors]-[a-zA-Z0-9\-]{10,}", "Slack token"),
]

FORBIDDEN_FILES = [
    ".env",
    "secrets.json",
    "id_rsa",
    "id_ed25519",
    "service_account.json",
    "credentials.json",
    "token.json",
]


def load_registry() -> dict:
    registry_path = Path(__file__).parent.parent / "registries" / "repos.yaml"
    with open(registry_path) as f:
        return yaml.safe_load(f)


def check_repo_secrets(repo: dict) -> list[dict]:
    """Check a repo for secret violations."""
    findings = []
    path = repo.get("path")

    if not path:
        return findings

    repo_path = Path(path).expanduser()
    if not repo_path.exists() or not (repo_path / ".git").exists():
        return findings

    # Check for forbidden committed files
    for fname in FORBIDDEN_FILES:
        result = subprocess.run(
            ["git", "ls-files", fname],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.stdout.strip():
            findings.append({
                "level": "ERROR",
                "file": fname,
                "message": f"forbidden file is tracked by git: {fname}",
            })

    # Check for .env.example (should exist if repo uses secrets)
    secret_profile = repo.get("secret_profile")
    if secret_profile and not (repo_path / ".env.example").exists():
        findings.append({
            "level": "WARN",
            "file": ".env.example",
            "message": f"repo uses secret profile '{secret_profile}' but has no .env.example",
        })

    # Scan tracked files for secret patterns
    tracked = subprocess.run(
        ["git", "ls-files"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        timeout=10,
    )

    # Files that contain secret patterns as detection rules, not actual secrets
    scanner_files = {"scripts/secrets_check.py", "scripts/policy_lint.py"}

    for tracked_file in tracked.stdout.strip().split("\n"):
        if not tracked_file or tracked_file in scanner_files:
            continue

        file_path = repo_path / tracked_file
        if not file_path.exists() or file_path.stat().st_size > 1_000_000:
            continue

        # Skip binary files
        try:
            content = file_path.read_text(errors="ignore")
        except Exception:
            continue

        for pattern, description in SECRET_PATTERNS:
            matches = re.findall(pattern, content)
            if matches:
                findings.append({
                    "level": "ERROR",
                    "file": tracked_file,
                    "message": f"potential secret detected: {description}",
                })
                break  # one finding per file is enough

    # Check if gitleaks is available and run it
    gitleaks_check = subprocess.run(
        ["which", "gitleaks"],
        capture_output=True,
        text=True,
    )
    if gitleaks_check.returncode == 0:
        result = subprocess.run(
            ["gitleaks", "detect", "--source", ".", "--no-banner",
             "--report-format", "json", "--report-path", "/dev/stdout"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=60,
        )
        # gitleaks exit 1 = leaks found, exit 0 = clean
        # Parse JSON output to distinguish real findings from errors
        if result.returncode == 1 and result.stdout.strip():
            import json
            try:
                leaks = json.loads(result.stdout)
                if leaks:
                    for leak in leaks[:5]:  # cap at 5 findings per repo
                        findings.append({
                            "level": "ERROR",
                            "file": leak.get("File", "-"),
                            "message": f"gitleaks: {leak.get('Description', 'secret detected')} "
                                       f"(rule: {leak.get('RuleID', 'unknown')})",
                        })
            except json.JSONDecodeError:
                findings.append({
                    "level": "WARN",
                    "file": "-",
                    "message": "gitleaks returned non-zero but output was not parseable",
                })
    # Silently skip if gitleaks is not installed (no INFO noise)

    return findings


def _dedup_repos(repos: list[dict]) -> list[dict]:
    """Deduplicate repos by name, keeping the first occurrence."""
    seen = set()
    out = []
    for r in repos:
        if r["name"] not in seen:
            seen.add(r["name"])
            out.append(r)
    return out


def main():
    registry = load_registry()
    repos = _dedup_repos(registry.get("repos", []))

    filter_repo = None
    for arg in sys.argv[1:]:
        if arg.startswith("--repo="):
            filter_repo = arg.split("=", 1)[1]

    total = len(repos)
    print(f"\n{C['bold']}  devctl secrets{C['reset']}  {C['dim']}{total} repos{C['reset']}\n")

    # Collect all results
    repo_findings = []
    for repo in repos:
        if filter_repo and repo["name"] != filter_repo:
            continue
        findings = check_repo_secrets(repo)
        repo_findings.append((repo, findings))

    # Classify repos
    n_errors = 0
    n_warnings = 0
    n_clean = 0
    error_count = 0

    # Sort: repos with findings first, sorted by error count descending
    def _sort_key(item):
        _, findings = item
        errors = sum(1 for f in findings if f["level"] == "ERROR")
        warns = sum(1 for f in findings if f["level"] == "WARN")
        return (-errors, -warns)

    repo_findings.sort(key=_sort_key)

    for repo, findings in repo_findings:
        # Skip INFO-only findings from display
        display_findings = [f for f in findings if f["level"] != "INFO"]

        if not display_findings:
            n_clean += 1
            if filter_repo:
                print(f"  {C['green']}\u25cf{C['reset']} {C['bold']}{repo['name']}{C['reset']}  {C['dim']}{repo['category']}{C['reset']}")
                print(f"    {C['green']}all checks passed{C['reset']}")
                print()
            continue

        has_errors = any(f["level"] == "ERROR" for f in display_findings)
        has_warns = any(f["level"] == "WARN" for f in display_findings)

        if has_errors:
            dot = f"{C['red']}\u25cf{C['reset']}"
            n_errors += 1
        elif has_warns:
            dot = f"{C['yellow']}\u25cf{C['reset']}"
            n_warnings += 1
        else:
            dot = f"{C['green']}\u25cf{C['reset']}"
            n_clean += 1

        print(f"  {dot} {C['bold']}{repo['name']}{C['reset']}  {C['dim']}{repo['category']}{C['reset']}")

        for f in display_findings:
            if f["level"] == "ERROR":
                icon = f"{C['red']}\u2717{C['reset']}"
                error_count += 1
            else:
                icon = f"{C['yellow']}!{C['reset']}"

            # Format: file path -- description
            desc = f["message"]
            # Strip redundant prefixes for cleaner display
            for prefix in ["forbidden file is tracked by git: ", "potential secret detected: ",
                           "gitleaks: "]:
                if desc.startswith(prefix):
                    desc = desc[len(prefix):]
                    break

            file_str = f["file"]
            if file_str != "-":
                print(f"    {icon} {file_str} {C['dim']}\u2014{C['reset']} {desc}")
            else:
                print(f"    {icon} {desc}")

        print()

    # Summary
    print(f"  {C['dim']}{'\u2500' * 50}{C['reset']}")
    parts = [f"  {C['bold']}{total} repos{C['reset']}"]
    parts.append(f"  {C['green']}\u25cf {n_clean} clean{C['reset']}")
    if n_warnings:
        parts.append(f"  {C['yellow']}\u25cf {n_warnings} with warnings{C['reset']}")
    if n_errors:
        parts.append(f"  {C['red']}\u25cf {n_errors} with findings{C['reset']}")
    if error_count:
        parts.append(f"  {C['red']}{error_count} errors{C['reset']}")
    print("".join(parts))
    print()

    if error_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
