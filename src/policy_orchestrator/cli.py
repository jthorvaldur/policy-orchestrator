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


@main.command("discover")
@click.option("--lifecycle", default=None, help="Filter by lifecycle (active, work-org, reference, duplicate, backup, orphan, empty, dependency, stale)")
@click.option("--risk", default=None, help="Filter by minimum risk (critical, high, medium, low)")
@click.option("--duplicates-only", is_flag=True, help="Show only duplicate groups")
@click.option("--unregistered-only", is_flag=True, help="Show only repos not in registry")
@click.option("--save", is_flag=True, help="Write results to registries/inventory.yaml")
@click.option("--format", "fmt", type=click.Choice(["table", "json", "yaml"]), default="table")
def discover(lifecycle, risk, duplicates_only, unregistered_only, save, fmt):
    """Discover and classify all git repos on the filesystem."""
    sys.path.insert(0, str(SCRIPTS_DIR))
    from repo_discover import run_discovery
    run_discovery(
        lifecycle_filter=lifecycle,
        risk_filter=risk,
        duplicates_only=duplicates_only,
        unregistered_only=unregistered_only,
        save=save,
        output_format=fmt,
    )


@main.command("inventory")
@click.option("--lifecycle", default=None, help="Filter by lifecycle category")
@click.option("--risk", default=None, help="Filter by minimum risk level")
def inventory(lifecycle, risk):
    """Query the saved inventory from last discovery run."""
    import yaml as _yaml

    inv_path = Path(__file__).parent.parent.parent / "registries" / "inventory.yaml"
    if not inv_path.exists():
        print("No inventory found. Run 'devctl discover --save' first.")
        return

    with open(inv_path) as f:
        data = _yaml.safe_load(f)

    repos = data.get("repos", [])
    if lifecycle:
        repos = [r for r in repos if r["lifecycle"] == lifecycle]
    if risk:
        risk_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "none": 4}
        max_level = risk_order.get(risk, 4)
        repos = [r for r in repos if risk_order.get(r.get("risk", {}).get("level", "none"), 4) <= max_level]

    print(f"{'Name':<30} {'Location':<14} {'Lifecycle':<12} {'Risk':<10} {'Registered'}")
    print("-" * 80)
    for r in repos:
        risk_level = r.get("risk", {}).get("level", "")
        if risk_level == "none":
            risk_level = ""
        reg = "yes" if r.get("registered") else ""
        print(f"{r['name']:<30} {r['location_group']:<14} {r['lifecycle']:<12} {risk_level:<10} {reg}")

    print(f"\nShowing {len(repos)} repos (from {data.get('generated', 'unknown')})")


if __name__ == "__main__":
    main()
