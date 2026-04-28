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


@main.command("sync")
@click.option("--files", default=None, help="Comma-separated template files to sync")
@click.option("--repo", default=None, help="Sync to specific repo only")
@click.option("--force", is_flag=True, help="Overwrite existing files")
@click.option("--dry-run", is_flag=True, help="Show what would be synced")
@click.option("--all-templates", is_flag=True, help="Sync INTENT.md, .env.example, .gitignore")
def sync_cmd(files, repo, force, dry_run, all_templates):
    """Sync control plane templates to managed repos."""
    sys.path.insert(0, str(SCRIPTS_DIR))
    from repo_sync import sync_all
    file_list = None
    if files:
        file_list = [f.strip() for f in files.split(",")]
    elif all_templates:
        file_list = ["INTENT.md", ".env.example", ".gitignore"]
    sync_all(files=file_list, repo_filter=repo, force=force, dry_run=dry_run)


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


@main.command("ingest-sessions")
@click.option("--repo", default=None, help="Only ingest sessions from this repo")
@click.option("--all", "ingest_all", is_flag=True, help="Re-ingest all sessions (ignore state)")
@click.option("--dry-run", is_flag=True, help="Count what would be ingested without doing it")
def ingest_sessions_cmd(repo, ingest_all, dry_run):
    """Ingest Claude Code sessions into Qdrant for semantic search."""
    sys.path.insert(0, str(SCRIPTS_DIR))
    from ingest_sessions import ingest_sessions
    ingest_sessions(
        repo_filter=repo,
        incremental=not ingest_all,
        dry_run=dry_run,
    )


@main.command("search-sessions")
@click.argument("query")
@click.option("--repo", default=None, help="Filter to a specific repo")
@click.option("--role", default=None, type=click.Choice(["user", "assistant"]), help="Filter by role")
@click.option("--limit", default=10, help="Number of results")
@click.option("--full", is_flag=True, help="Show full chunk text")
def search_sessions_cmd(query, repo, role, limit, full):
    """Semantic search across Claude Code sessions."""
    sys.path.insert(0, str(SCRIPTS_DIR))
    from search_sessions import search_sessions
    search_sessions(
        query=query,
        repo_filter=repo,
        role_filter=role,
        limit=limit,
        show_full=full,
    )


@main.command("log-feedback")
@click.option("--type", "event_type", required=True,
              type=click.Choice(["correction", "confirmation", "mode_shift", "observation"]))
@click.option("--signal", required=True, help="What the user said/did")
@click.option("--action", default="", help="What the agent did")
@click.option("--delta", default="", help="What was wrong / what changed")
@click.option("--rule", default="", help="The learned calibration rule")
@click.option("--repo", default="", help="Which repo this applies to")
@click.option("--scope", default="all_sessions", type=click.Choice(["all_sessions", "repo_specific"]))
def log_feedback_cmd(event_type, signal, action, delta, rule, repo, scope):
    """Log a calibration event to the feedback_events collection."""
    sys.path.insert(0, str(SCRIPTS_DIR))
    from log_feedback import log_feedback
    log_feedback(event_type=event_type, user_signal=signal, agent_action=action,
                 delta=delta, learned_rule=rule, repo=repo, scope=scope)


@main.command("query-feedback")
@click.argument("query", required=False, default=None)
@click.option("--repo", default=None, help="Filter to repo")
@click.option("--type", "event_type", default=None,
              type=click.Choice(["correction", "confirmation", "mode_shift", "observation"]))
@click.option("--limit", default=5)
def query_feedback_cmd(query, repo, event_type, limit):
    """Query feedback events for calibration notes."""
    sys.path.insert(0, str(SCRIPTS_DIR))
    from log_feedback import query_feedback
    query_feedback(query=query, repo=repo, event_type=event_type, limit=limit)


@main.command("log-fact")
@click.option("--fact", required=True, help="The factual claim")
@click.option("--source-type", required=True,
              type=click.Choice(["financial_download", "court_document", "tax_document", "email",
                                 "text_message", "conversation", "medical_record", "legal_filing",
                                 "calculation", "public_record", "photograph", "other"]))
@click.option("--confidence", required=True,
              type=click.Choice(["verified", "documented", "asserted", "disputed", "inferred", "unknown"]))
@click.option("--domain", required=True,
              type=click.Choice(["financial", "legal", "medical", "personal", "technical", "property", "employment"]))
@click.option("--source-ref", default="", help="File path or document reference")
@click.option("--source-date", default="", help="Date the fact pertains to (YYYY-MM-DD)")
@click.option("--claimed-by", default="", help="Who made this claim")
@click.option("--contradicts", default="", help="What this contradicts")
@click.option("--repo", default="", help="Originating repo")
@click.option("--notes", default="", help="Additional context")
def log_fact_cmd(fact, source_type, confidence, domain, source_ref, source_date,
                 claimed_by, contradicts, repo, notes):
    """Log a classified fact with provenance and confidence level."""
    sys.path.insert(0, str(SCRIPTS_DIR))
    from log_fact import log_fact
    log_fact(fact=fact, source_type=source_type, confidence=confidence, domain=domain,
             source_ref=source_ref, source_date=source_date, claimed_by=claimed_by,
             contradicts=contradicts, repo=repo, notes=notes)


@main.command("query-facts")
@click.argument("query", required=False, default=None)
@click.option("--domain", default=None,
              type=click.Choice(["financial", "legal", "medical", "personal", "technical", "property", "employment"]))
@click.option("--confidence", default=None,
              type=click.Choice(["verified", "documented", "asserted", "disputed", "inferred", "unknown"]))
@click.option("--min-confidence", default=None,
              type=click.Choice(["verified", "documented", "asserted", "disputed", "inferred"]),
              help="Show facts at this confidence or higher")
@click.option("--source-type", default=None)
@click.option("--repo", default=None)
@click.option("--limit", default=10)
@click.option("--all", "show_all", is_flag=True, help="Show all fields including notes")
def query_facts_cmd(query, domain, confidence, min_confidence, source_type, repo, limit, show_all):
    """Query the fact registry with optional confidence filtering."""
    sys.path.insert(0, str(SCRIPTS_DIR))
    from log_fact import query_facts
    query_facts(query=query, domain=domain, confidence=confidence, min_confidence=min_confidence,
                source_type=source_type, repo=repo, limit=limit, show_all=show_all)


if __name__ == "__main__":
    main()
