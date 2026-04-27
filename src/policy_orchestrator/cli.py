#!/usr/bin/env python3
"""devctl — control plane CLI for multi-repo management."""

import subprocess
import sys
from pathlib import Path

import click

SCRIPTS_DIR = Path(__file__).parent.parent.parent / "scripts"


@click.group()
def main():
    """devctl — multi-repo development control plane."""
    pass


@main.command()
@click.option("--category", default=None, help="Filter by repo category")
@click.option("--dirty", is_flag=True, help="Show only repos with dirty git trees")
def status(category, dirty):
    """Show status of all registered repos."""
    args = [sys.executable, str(SCRIPTS_DIR / "repo_status.py")]
    if category:
        args.append(f"--category={category}")
    if dirty:
        args.append("--dirty")
    subprocess.run(args)


@main.command()
@click.option("--repo", default=None, help="Audit a specific repo")
@click.option("--all", "audit_all", is_flag=True, default=True, help="Audit all repos")
def audit(repo, audit_all):
    """Audit repos for policy compliance."""
    args = [sys.executable, str(SCRIPTS_DIR / "repo_audit.py")]
    if repo:
        args.append(f"--repo={repo}")
    subprocess.run(args)


@main.command("secrets")
@click.option("--repo", default=None, help="Check a specific repo")
def secrets_check(repo):
    """Check repos for secret hygiene violations."""
    args = [sys.executable, str(SCRIPTS_DIR / "secrets_check.py")]
    if repo:
        args.append(f"--repo={repo}")
    subprocess.run(args)


@main.command("policy")
@click.option("--repo", default=None, help="Lint a specific repo")
def policy_lint(repo):
    """Lint repos against hard and soft policies."""
    args = [sys.executable, str(SCRIPTS_DIR / "policy_lint.py")]
    if repo:
        args.append(f"--repo={repo}")
    subprocess.run(args)


@main.command("list")
@click.option("--category", default=None, help="Filter by category")
def list_repos(category):
    """List all registered repos."""
    import yaml

    registry_path = Path(__file__).parent.parent.parent / "registries" / "repos.yaml"
    with open(registry_path) as f:
        registry = yaml.safe_load(f)

    repos = registry.get("repos", [])
    if category:
        repos = [r for r in repos if r["category"] == category]

    print(f"{'Name':<30} {'Category':<18} {'Language':<15} {'Visibility':<12} {'Priority'}")
    print("-" * 95)
    for repo in repos:
        print(
            f"{repo['name']:<30} {repo['category']:<18} {repo.get('language', '-'):<15} "
            f"{repo.get('visibility', '-'):<12} {repo.get('priority', '-')}"
        )
    print(f"\nTotal: {len(repos)} repos")


if __name__ == "__main__":
    main()
