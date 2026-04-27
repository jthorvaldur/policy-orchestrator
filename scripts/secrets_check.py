#!/usr/bin/env python3
"""Check repos for secret hygiene."""

import re
import subprocess
import sys
from pathlib import Path

import yaml

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

    for tracked_file in tracked.stdout.strip().split("\n"):
        if not tracked_file:
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
    else:
        findings.append({
            "level": "INFO",
            "file": "-",
            "message": "gitleaks not installed — install with: brew install gitleaks",
        })

    return findings


def main():
    registry = load_registry()
    repos = registry.get("repos", [])

    filter_repo = None
    for arg in sys.argv[1:]:
        if arg.startswith("--repo="):
            filter_repo = arg.split("=", 1)[1]

    error_count = 0

    for repo in repos:
        if filter_repo and repo["name"] != filter_repo:
            continue

        findings = check_repo_secrets(repo)

        if findings:
            print(f"\n  {repo['name']}  [{repo['category']}]")
            print(f"  {'-' * 50}")
            for f in findings:
                icon = {"ERROR": "ERROR", "WARN": " WARN", "INFO": " INFO"}[f["level"]]
                print(f"  [{icon}] {f['file']}: {f['message']}")
                if f["level"] == "ERROR":
                    error_count += 1
        elif filter_repo:
            print(f"\n  {repo['name']}: all secret checks passed")

    print(f"\n--- Secrets Check Summary ---")
    print(f"Errors: {error_count}")

    if error_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
