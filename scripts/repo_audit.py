#!/usr/bin/env python3
"""Audit repos for policy compliance — modern CLI output."""

import subprocess
import sys
from pathlib import Path

import yaml

REQUIRED_FILES = ["README.md", ".gitignore"]
RECOMMENDED_FILES = ["CLAUDE.md", ".env.example"]
FORBIDDEN_PATTERNS = [
    ".env", "secrets.json", "id_rsa", "id_ed25519",
    "service_account.json", "credentials.json", "token.json",
]

# ANSI
C = {
    "reset": "\033[0m", "bold": "\033[1m", "dim": "\033[90m",
    "green": "\033[32m", "yellow": "\033[33m", "red": "\033[31m",
    "cyan": "\033[36m", "white": "\033[97m",
}


def load_registry() -> dict:
    registry_path = Path(__file__).parent.parent / "registries" / "repos.yaml"
    with open(registry_path) as f:
        return yaml.safe_load(f)


def audit_repo(repo: dict) -> list[dict]:
    """Audit a single repo. Returns list of findings."""
    findings = []
    path = repo.get("path")

    if not path:
        return [{"level": "SKIP", "message": "not cloned locally"}]

    repo_path = Path(path).expanduser()
    if not repo_path.exists():
        return [{"level": "ERROR", "message": f"path does not exist: {repo_path}"}]

    # Required files
    for f in REQUIRED_FILES:
        if not (repo_path / f).exists():
            findings.append({"level": "ERROR", "message": f"missing {f}"})

    # Recommended files
    for f in RECOMMENDED_FILES:
        if not (repo_path / f).exists():
            findings.append({"level": "WARN", "message": f"missing {f}"})

    # Forbidden files
    for pattern in FORBIDDEN_PATTERNS:
        target = repo_path / pattern
        if target.exists():
            try:
                result = subprocess.run(
                    ["git", "ls-files", pattern],
                    cwd=repo_path, capture_output=True, text=True, timeout=10,
                )
                if result.stdout.strip():
                    findings.append({"level": "ERROR", "message": f"{pattern} committed to git"})
                else:
                    findings.append({"level": "WARN", "message": f"{pattern} exists (not tracked)"})
            except Exception:
                findings.append({"level": "WARN", "message": f"{pattern} exists (git check failed)"})

    # Git state
    if (repo_path / ".git").exists():
        try:
            status = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=repo_path, capture_output=True, text=True, timeout=10,
            )
            if status.stdout.strip():
                n = len(status.stdout.strip().splitlines())
                findings.append({"level": "WARN", "message": f"dirty git tree ({n} files)"})
        except Exception:
            pass
    else:
        findings.append({"level": "ERROR", "message": "not a git repository"})

    # Control plane
    if not (repo_path / ".control" / "repo.yaml").exists():
        findings.append({"level": "WARN", "message": "no .control/repo.yaml"})

    # Agent operating process pack (skip reference/frozen repos — no active
    # agent work there, no need for enforcement hooks)
    if repo.get("priority") != "reference":
        pack_core = [
            ".claude/settings.json",
            "contracts/agents.yaml",
            "contracts/model-routing.yaml",
            "evals",
            "scripts/test.sh",
        ]
        missing = [f for f in pack_core if not (repo_path / f).exists()]
        if missing:
            findings.append({
                "level": "WARN",
                "message": (
                    f"agent-process pack incomplete ({len(missing)}/{len(pack_core)} missing) "
                    "— devctl sync --agent-processes"
                ),
            })

    return findings


def main():
    registry = load_registry()
    repos = registry.get("repos", [])

    # Deduplicate
    seen = set()
    unique_repos = []
    for r in repos:
        if r["name"] not in seen:
            seen.add(r["name"])
            unique_repos.append(r)
    repos = unique_repos

    filter_repo = None
    for arg in sys.argv[1:]:
        if arg.startswith("--repo="):
            filter_repo = arg.split("=", 1)[1]

    if filter_repo:
        repos = [r for r in repos if r["name"] == filter_repo]

    # Run all audits
    results = []
    for repo in repos:
        findings = audit_repo(repo)
        errors = [f for f in findings if f["level"] == "ERROR"]
        warns = [f for f in findings if f["level"] == "WARN"]
        results.append({
            "repo": repo,
            "findings": findings,
            "errors": len(errors),
            "warns": len(warns),
            "clean": len(errors) == 0 and len(warns) == 0,
        })

    # Sort: errors first, then warnings, then clean
    results.sort(key=lambda r: (-r["errors"], -r["warns"], r["repo"]["name"]))

    total_errors = sum(r["errors"] for r in results)
    total_warns = sum(r["warns"] for r in results)
    total_clean = sum(1 for r in results if r["clean"])

    # Header
    print(f"\n{C['bold']}  devctl audit{C['reset']}  {C['dim']}{len(results)} repos{C['reset']}\n")

    # Print repos with issues first
    for r in results:
        repo = r["repo"]
        name = repo["name"]
        cat = repo.get("category", "?")
        vis = repo.get("visibility", "?")

        if r["clean"]:
            if not filter_repo:
                continue  # skip clean repos in summary view
            dot = f"{C['green']}●{C['reset']}"
            print(f"  {dot} {C['bold']}{name}{C['reset']}  {C['dim']}{cat} · {vis}{C['reset']}  {C['green']}clean{C['reset']}")
            continue

        # Determine repo dot color
        if r["errors"] > 0:
            dot = f"{C['red']}●{C['reset']}"
        else:
            dot = f"{C['yellow']}●{C['reset']}"

        print(f"  {dot} {C['bold']}{name}{C['reset']}  {C['dim']}{cat} · {vis}{C['reset']}")

        for f in r["findings"]:
            if f["level"] == "ERROR":
                icon = f"{C['red']}✗{C['reset']}"
            elif f["level"] == "WARN":
                icon = f"{C['yellow']}!{C['reset']}"
            elif f["level"] == "SKIP":
                icon = f"{C['dim']}–{C['reset']}"
            else:
                continue
            print(f"      {icon} {f['message']}")

    # Summary bar
    print(f"\n  {'─' * 50}")
    parts = []
    if total_clean > 0:
        parts.append(f"{C['green']}● {total_clean} clean{C['reset']}")
    if total_warns > 0:
        parts.append(f"{C['yellow']}● {total_warns} warnings{C['reset']}")
    if total_errors > 0:
        parts.append(f"{C['red']}● {total_errors} errors{C['reset']}")
    print(f"  {C['bold']}{len(results)} repos{C['reset']}  {'  '.join(parts)}")
    print()

    if total_errors > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
