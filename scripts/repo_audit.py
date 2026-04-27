#!/usr/bin/env python3
"""Audit repos for policy compliance."""

import subprocess
import sys
from pathlib import Path

import yaml

REQUIRED_FILES = ["README.md", ".gitignore"]
RECOMMENDED_FILES = ["INTENT.md", "CLAUDE.md", ".env.example"]
FORBIDDEN_PATTERNS = [
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


def audit_repo(repo: dict) -> list[dict]:
    """Audit a single repo. Returns list of findings."""
    findings = []
    path = repo.get("path")

    if not path:
        findings.append({
            "level": "INFO",
            "message": "not cloned locally — cannot audit",
        })
        return findings

    repo_path = Path(path).expanduser()
    if not repo_path.exists():
        findings.append({
            "level": "ERROR",
            "message": f"registered path does not exist: {repo_path}",
        })
        return findings

    # Check required files
    for f in REQUIRED_FILES:
        if not (repo_path / f).exists():
            findings.append({
                "level": "ERROR",
                "message": f"missing required file: {f}",
            })

    # Check recommended files
    for f in RECOMMENDED_FILES:
        if not (repo_path / f).exists():
            findings.append({
                "level": "WARN",
                "message": f"missing recommended file: {f}",
            })

    # Check forbidden files (committed)
    for pattern in FORBIDDEN_PATTERNS:
        target = repo_path / pattern
        if target.exists():
            # Check if it's tracked by git
            result = subprocess.run(
                ["git", "ls-files", pattern],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.stdout.strip():
                findings.append({
                    "level": "ERROR",
                    "message": f"forbidden file committed: {pattern}",
                })
            else:
                findings.append({
                    "level": "WARN",
                    "message": f"forbidden file exists (but not tracked): {pattern}",
                })

    # Check git state
    if (repo_path / ".git").exists():
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if status.stdout.strip():
            findings.append({
                "level": "WARN",
                "message": "dirty git tree",
            })

        # Check for no upstream
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            findings.append({
                "level": "WARN",
                "message": "no upstream remote configured",
            })
    else:
        findings.append({
            "level": "ERROR",
            "message": "not a git repository",
        })

    # Check for .control/repo.yaml
    if not (repo_path / ".control" / "repo.yaml").exists():
        findings.append({
            "level": "WARN",
            "message": "missing .control/repo.yaml — not registered with control plane",
        })

    # Check for scripts
    scripts_dir = repo_path / "scripts"
    if not scripts_dir.exists():
        findings.append({
            "level": "INFO",
            "message": "no scripts/ directory",
        })
    else:
        for script in ["dev.sh", "test.sh"]:
            if not (scripts_dir / script).exists():
                findings.append({
                    "level": "INFO",
                    "message": f"missing scripts/{script}",
                })

    if not findings:
        findings.append({"level": "OK", "message": "all checks passed"})

    return findings


def main():
    registry = load_registry()
    repos = registry.get("repos", [])

    filter_repo = None
    for arg in sys.argv[1:]:
        if arg.startswith("--repo="):
            filter_repo = arg.split("=", 1)[1]

    error_count = 0
    warn_count = 0

    for repo in repos:
        if filter_repo and repo["name"] != filter_repo:
            continue

        findings = audit_repo(repo)
        has_issues = any(f["level"] in ("ERROR", "WARN") for f in findings)

        if has_issues or not filter_repo:
            print(f"\n{'=' * 60}")
            print(f"  {repo['name']}  [{repo['category']}]  ({repo.get('visibility', 'unknown')})")
            print(f"{'=' * 60}")

            for f in findings:
                icon = {"ERROR": "ERROR", "WARN": " WARN", "INFO": " INFO", "OK": "   OK"}[f["level"]]
                print(f"  [{icon}] {f['message']}")
                if f["level"] == "ERROR":
                    error_count += 1
                elif f["level"] == "WARN":
                    warn_count += 1

    print(f"\n--- Summary ---")
    print(f"Repos audited: {len(repos) if not filter_repo else 1}")
    print(f"Errors: {error_count}")
    print(f"Warnings: {warn_count}")

    if error_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
