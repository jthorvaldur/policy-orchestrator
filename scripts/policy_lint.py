#!/usr/bin/env python3
"""Lint repos against hard and soft policies — modern CLI output."""

import re
import subprocess
import sys
from pathlib import Path

import yaml

# ANSI
C = {
    "reset": "\033[0m", "bold": "\033[1m", "dim": "\033[90m",
    "green": "\033[32m", "yellow": "\033[33m", "red": "\033[31m",
    "cyan": "\033[36m",
}


def load_registry() -> dict:
    registry_path = Path(__file__).parent.parent / "registries" / "repos.yaml"
    with open(registry_path) as f:
        return yaml.safe_load(f)


def lint_repo(repo: dict) -> list[dict]:
    """Lint a repo against all policies. Returns classified findings."""
    findings = []
    path = repo.get("path")

    if not path:
        return []

    repo_path = Path(path).expanduser()
    if not repo_path.exists():
        return []

    # === HARD POLICIES (ERROR) ===

    # secrets: .env must be gitignored
    gitignore = repo_path / ".gitignore"
    if gitignore.exists():
        content = gitignore.read_text()
        # Check for .env exclusion — any of these patterns work
        has_env_exclude = any(
            line.strip() in (".env", ".env*", ".env.*")
            or line.strip().startswith(".env")
            for line in content.splitlines()
            if line.strip() and not line.strip().startswith("#") and not line.strip().startswith("!")
        )
        if not has_env_exclude:
            findings.append({
                "level": "ERROR",
                "policy": "secrets",
                "message": ".gitignore missing .env exclusion",
            })
    else:
        findings.append({
            "level": "ERROR",
            "policy": "secrets",
            "message": "no .gitignore file",
        })

    # secrets: check for API keys in tracked files
    for check_file in ["CLAUDE.md", "README.md", ".control/repo.yaml"]:
        fpath = repo_path / check_file
        if fpath.exists():
            try:
                content = fpath.read_text(errors="replace")
                for pattern in [r"sk-[a-zA-Z0-9]{20,}", r"sk-ant-", r"AKIA[A-Z0-9]", r"ghp_[a-zA-Z0-9]", r"AIza[a-zA-Z0-9]"]:
                    if re.search(pattern, content):
                        findings.append({
                            "level": "ERROR",
                            "policy": "secrets",
                            "message": f"possible API key in {check_file}",
                        })
                        break
            except Exception:
                pass

    # === SOFT POLICIES (WARN) ===

    # docs: README should have minimum content
    readme = repo_path / "README.md"
    if readme.exists():
        content = readme.read_text(errors="replace")
        if len(content.strip()) < 50:
            findings.append({
                "level": "WARN",
                "policy": "docs",
                "message": "README.md too short (< 50 chars)",
            })
    else:
        findings.append({
            "level": "WARN",
            "policy": "docs",
            "message": "missing README.md",
        })

    # style: Python repos should have pyproject.toml
    lang = repo.get("language", "")
    if lang == "python" or (isinstance(lang, str) and lang.startswith("python")):
        if not (repo_path / "pyproject.toml").exists():
            # Only warn if there are actual .py files (not empty repos)
            py_files = list(repo_path.glob("**/*.py"))
            if len(py_files) > 0:
                findings.append({
                    "level": "WARN",
                    "policy": "style",
                    "message": "Python repo lacks pyproject.toml",
                })

    # llm-prompts: repos using LLM should declare providers
    if repo.get("secret_profile") in ("base_llm", "legal_local"):
        control_yaml = repo_path / ".control" / "repo.yaml"
        if not control_yaml.exists():
            findings.append({
                "level": "WARN",
                "policy": "llm",
                "message": "uses LLM but no .control/repo.yaml",
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

    # Run all lints
    results = []
    for repo in repos:
        findings = lint_repo(repo)
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
    print(f"\n{C['bold']}  devctl policy{C['reset']}  {C['dim']}{len(results)} repos{C['reset']}\n")

    for r in results:
        repo = r["repo"]
        name = repo["name"]
        cat = repo.get("category", "?")

        if r["clean"]:
            if not filter_repo:
                continue
            print(f"  {C['green']}●{C['reset']} {C['bold']}{name}{C['reset']}  {C['dim']}{cat}{C['reset']}  {C['green']}clean{C['reset']}")
            continue

        if r["errors"] > 0:
            dot = f"{C['red']}●{C['reset']}"
        else:
            dot = f"{C['yellow']}●{C['reset']}"

        print(f"  {dot} {C['bold']}{name}{C['reset']}  {C['dim']}{cat}{C['reset']}")

        for f in r["findings"]:
            if f["level"] == "ERROR":
                icon = f"{C['red']}✗{C['reset']}"
            elif f["level"] == "WARN":
                icon = f"{C['yellow']}!{C['reset']}"
            else:
                continue
            policy_tag = f"{C['dim']}[{f['policy']}]{C['reset']}"
            print(f"      {icon} {policy_tag} {f['message']}")

    # Summary
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
