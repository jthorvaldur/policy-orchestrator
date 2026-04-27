#!/usr/bin/env python3
"""Lint repos against hard and soft policies."""

import subprocess
import sys
from pathlib import Path

import yaml


def load_registry() -> dict:
    registry_path = Path(__file__).parent.parent / "registries" / "repos.yaml"
    with open(registry_path) as f:
        return yaml.safe_load(f)


def lint_repo(repo: dict) -> list[dict]:
    """Lint a repo against all policies. Returns classified findings."""
    findings = []
    path = repo.get("path")

    if not path:
        return findings

    repo_path = Path(path).expanduser()
    if not repo_path.exists():
        return findings

    # === HARD POLICIES (ERROR) ===

    # secrets.md: .env must be gitignored
    gitignore = repo_path / ".gitignore"
    if gitignore.exists():
        content = gitignore.read_text()
        if ".env" not in content:
            findings.append({
                "level": "ERROR",
                "policy": "secrets",
                "message": ".gitignore does not exclude .env",
            })
    else:
        findings.append({
            "level": "ERROR",
            "policy": "secrets",
            "message": "no .gitignore file",
        })

    # Check CLAUDE.md for secret patterns
    claude_md = repo_path / "CLAUDE.md"
    if claude_md.exists():
        content = claude_md.read_text()
        import re
        for pattern in [r"sk-[a-zA-Z0-9]{20,}", r"sk-ant-", r"AKIA", r"ghp_", r"AIza"]:
            if re.search(pattern, content):
                findings.append({
                    "level": "ERROR",
                    "policy": "secrets",
                    "message": "CLAUDE.md may contain API keys",
                })
                break

    # git-main.md: check for force-push evidence is runtime, skip in lint

    # === SOFT POLICIES (WARN) ===

    # docs.md: README should have minimum content
    readme = repo_path / "README.md"
    if readme.exists():
        content = readme.read_text()
        if len(content.strip()) < 50:
            findings.append({
                "level": "WARN",
                "policy": "docs",
                "message": "README.md appears too short (< 50 chars)",
            })
    else:
        findings.append({
            "level": "ERROR",
            "policy": "docs",
            "message": "missing README.md",
        })

    # style.md: Python repos should have pyproject.toml
    if repo.get("language", "").startswith("python"):
        if not (repo_path / "pyproject.toml").exists():
            findings.append({
                "level": "WARN",
                "policy": "style",
                "message": "Python repo lacks pyproject.toml",
            })

    # llm-prompts.md: repos using LLM should declare providers
    if repo.get("secret_profile") in ("base_llm", "legal_local"):
        control_yaml = repo_path / ".control" / "repo.yaml"
        if not control_yaml.exists():
            findings.append({
                "level": "WARN",
                "policy": "llm-prompts",
                "message": "repo uses LLM but has no .control/repo.yaml declaring providers",
            })

    return findings


def main():
    registry = load_registry()
    repos = registry.get("repos", [])

    filter_repo = None
    for arg in sys.argv[1:]:
        if arg.startswith("--repo="):
            filter_repo = arg.split("=", 1)[1]

    total_errors = 0
    total_warns = 0

    for repo in repos:
        if filter_repo and repo["name"] != filter_repo:
            continue

        findings = lint_repo(repo)

        if findings:
            print(f"\n  {repo['name']}  [{repo['category']}]")
            for f in findings:
                icon = {"ERROR": "ERROR", "WARN": " WARN", "INFO": " INFO"}[f["level"]]
                print(f"  [{icon}] [{f['policy']}] {f['message']}")
                if f["level"] == "ERROR":
                    total_errors += 1
                elif f["level"] == "WARN":
                    total_warns += 1

    print(f"\n--- Policy Lint Summary ---")
    print(f"Errors: {total_errors}")
    print(f"Warnings: {total_warns}")

    if total_errors > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
