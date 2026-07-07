#!/usr/bin/env python3
"""devctl — control plane CLI for multi-repo management."""

import os
import subprocess
import sys
from pathlib import Path

import click

SCRIPTS_DIR = Path(__file__).parent.parent.parent / "scripts"
REGISTRIES_DIR = Path(__file__).parent.parent.parent / "registries"

# ANSI
C = {
    "reset": "\033[0m", "bold": "\033[1m", "dim": "\033[90m",
    "green": "\033[32m", "yellow": "\033[33m", "cyan": "\033[36m",
    "red": "\033[31m", "mag": "\033[35m",
}


def _show_overview():
    """Show a quick dashboard when devctl is called with no args."""
    import yaml

    print(f"\n{C['bold']}  devctl{C['reset']} — control plane\n")

    # Repos
    try:
        with open(REGISTRIES_DIR / "repos.yaml") as f:
            repos = yaml.safe_load(f).get("repos", [])
        categories = {}
        for r in repos:
            cat = r.get("category", "?")
            categories[cat] = categories.get(cat, 0) + 1
        cat_str = "  ".join(f"{C['dim']}{c}:{C['reset']}{n}" for c, n in sorted(categories.items()))
        print(f"  {C['bold']}{len(repos)}{C['reset']} repos  {cat_str}")
    except Exception:
        print(f"  {C['red']}could not load repos.yaml{C['reset']}")

    # Vector DB
    try:
        from qdrant_client import QdrantClient
        total = 0
        cols = 0
        for port in [6333, 7333, 8333]:
            try:
                # :8333 runs an older server (1.14); skip the compat check to
                # avoid a cosmetic version-mismatch UserWarning on connect.
                kw = {"check_compatibility": False} if port == 8333 else {}
                client = QdrantClient(host="localhost", port=port, timeout=3, **kw)
                for col in client.get_collections().collections:
                    info = client.get_collection(col.name)
                    total += info.points_count
                    cols += 1
            except Exception:
                pass
        print(f"  {C['bold']}{total:,}{C['reset']} vectors  {C['dim']}across{C['reset']} {cols} collections")
    except ImportError:
        pass

    # Pages
    try:
        with open(REGISTRIES_DIR / "pages.yaml") as f:
            pages_data = yaml.safe_load(f)
        deployed = len(pages_data.get("sections", {}))
        pending = len(pages_data.get("pending", {}))
        pages_str = f"{C['green']}{deployed} deployed{C['reset']}"
        if pending:
            pages_str += f"  {C['yellow']}{pending} pending{C['reset']}"
        print(f"  {C['bold']}{deployed + pending}{C['reset']} page sections  {pages_str}")
    except Exception:
        pass

    # Commands by category
    print(f"\n  {C['bold']}Commands{C['reset']}\n")
    groups = {
        "Repos":    ["status", "list", "audit", "discover", "inventory"],
        "Data":     ["db-status", "search", "embed", "audit-vectors"],
        "Pages":    ["deploy-pages", "audit-pages", "verify-pages"],
        "Secrets":  ["secrets", "validate-secrets"],
        "Facts":    ["log-fact", "query-facts", "log-feedback", "query-feedback"],
        "Build":    ["provenance", "benchmark", "health"],
        "Traffic":  ["traffic"],
        "Finance":  ["subscriptions"],
        "Tools":    ["sync", "dashboard", "readme", "diagram", "policy", "ingest-sessions", "search-sessions"],
    }
    for group, cmds in groups.items():
        cmd_str = f"{C['dim']}, {C['reset']}".join(cmds)
        print(f"  {C['cyan']}{group:<10}{C['reset']} {cmd_str}")

    # Quick start cheat sheet
    print(f"\n  {C['bold']}Quick Start{C['reset']}\n")
    cheat = [
        ("Check everything",        "devctl health"),
        ("What's dirty?",           "devctl status --dirty"),
        ("Search docs/facts/algos", 'devctl search "query"'),
        ("Search Claude/AI chats",  'devctl search "query" --claude'),
        ("Deploy pages from cwd",   "devctl deploy-pages --auto --verify --push"),
        ("Run benchmarks",          "devctl benchmark"),
        ("Scale projection",        "devctl benchmark --project=100000"),
        ("Vector DB overview",      "devctl db-status"),
        ("Security audit pages",    "devctl audit-pages"),
        ("Live page verification",  "devctl verify-pages --quick"),
        ("What generated a file?",  "devctl provenance show path/file.html"),
        ("Stale outputs?",          "devctl provenance stale"),
        ("Log a verified fact",     'devctl log-fact --fact "X" --source-type email --confidence verified --domain legal'),
        ("Subscription burn rate",   "devctl subscriptions costs"),
        ("Init a new repo",         "devctl init --name=my_repo --category=research"),
    ]
    for desc, cmd in cheat:
        print(f"  {C['dim']}{desc:<26}{C['reset']} {cmd}")

    print(f"\n  {C['dim']}Full reference: docs/DEVCTL.md  |  devctl <command> --help{C['reset']}\n")


_PO_ROOT = Path(__file__).resolve().parents[2]


def _repo_local_devctl_root() -> Path | None:
    """If cwd is inside a managed repo whose pyproject declares its own
    `devctl` console script, return that repo's root. That repo's devctl is
    a *plugin*: the global binary forwards unknown subcommands to it."""
    d = Path.cwd()
    while d != d.parent:
        pyproject = d / "pyproject.toml"
        if pyproject.exists():
            if d == _PO_ROOT:
                return None  # never forward to ourselves
            try:
                import tomllib

                scripts = (tomllib.loads(pyproject.read_text())
                           .get("project", {}).get("scripts", {}))
            except Exception:
                return None
            return d if "devctl" in scripts else None
        d = d.parent
    return None


class RepoPluginGroup(click.Group):
    """Unknown subcommands fall through to the current repo's own devctl
    (`uv run --project <repo> devctl <cmd> …`). Repo-local commands stay
    repo-local; the control plane needs no knowledge of them."""

    def get_command(self, ctx, cmd_name):
        cmd = super().get_command(ctx, cmd_name)
        if cmd is not None:
            return cmd
        repo = _repo_local_devctl_root()
        if repo is None:
            return None

        @click.command(name=cmd_name, context_settings={
            "ignore_unknown_options": True, "allow_extra_args": True,
            "help_option_names": [],
        })
        @click.argument("args", nargs=-1, type=click.UNPROCESSED)
        def _forward(args):
            print(f"{C['dim']}→ {repo.name} plugin: devctl {cmd_name}{C['reset']}",
                  file=sys.stderr)
            raise SystemExit(subprocess.call(
                ["uv", "run", "--project", str(repo), "devctl", cmd_name, *args],
                cwd=repo,
            ))

        return _forward


@click.group(cls=RepoPluginGroup, invoke_without_command=True)
@click.pass_context
def main(ctx):
    """devctl — multi-repo development control plane."""
    if ctx.invoked_subcommand is None:
        _show_overview()


@main.command("init")
@click.option("--name", required=True, help="Repo directory name in ~/GitHub/")
@click.option("--category", default=None, help="Category (legal, ai-agents, quant-finance, infrastructure, research, creative-math, web-portfolio)")
@click.option("--visibility", default="private", type=click.Choice(["public", "private"]))
@click.option("--no-github", is_flag=True, help="Skip GitHub repo creation")
@click.option("--no-push", is_flag=True, help="Skip initial push")
@click.option("--dry-run", is_flag=True, help="Show what would be done")
def init_cmd(name, category, visibility, no_github, no_push, dry_run):
    """Initialize a new repo into the control plane."""
    args = [sys.executable, str(SCRIPTS_DIR / "init_repo.py"), f"--name={name}"]
    if category:
        args.append(f"--category={category}")
    args.append(f"--visibility={visibility}")
    if no_github:
        args.append("--no-github")
    if no_push:
        args.append("--no-push")
    if dry_run:
        args.append("--dry-run")
    subprocess.run(args)


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
@click.option("--claude-hooks", is_flag=True,
              help="Sync .claude session hooks that inject INTENT/CLAUDE md files "
                   "into every agent session (anti-drift)")
@click.option("--agent-processes", is_flag=True,
              help="Sync the full agent operating process pack: enforcement hooks, "
                   "agent contracts, model routing, process docs, evals scaffold")
def sync_cmd(files, repo, force, dry_run, all_templates, claude_hooks, agent_processes):
    """Sync control plane templates to managed repos."""
    sys.path.insert(0, str(SCRIPTS_DIR))
    from repo_sync import AGENT_PROCESS_PACK, sync_all
    file_list = None
    if files:
        file_list = [f.strip() for f in files.split(",")]
    elif all_templates:
        file_list = ["INTENT.md", ".env.example", ".gitignore"]
    if claude_hooks:
        file_list = (file_list or []) + [
            "claude/settings.json",
            "claude/hooks/session-start-intent.sh",
            "claude/hooks/post-compact-reinject.sh",
        ]
    if agent_processes:
        file_list = list(dict.fromkeys((file_list or []) + AGENT_PROCESS_PACK))
    sync_all(files=file_list, repo_filter=repo, force=force, dry_run=dry_run)


@main.command("dashboard")
def dashboard():
    """Generate HTML dashboard and deploy to GitHub Pages."""
    sys.path.insert(0, str(SCRIPTS_DIR))
    from generate_dashboard import main as gen
    gen()


@main.command("diagram")
@click.option("--repo", default=None, help="Path to a specific repo to diagram (default: cwd)")
@click.option("--all", "diagram_all", is_flag=True, help="Diagram all repos in the registry")
@click.option("--model", default="claude-haiku-4-5", show_default=True,
              help="Claude model to use")
@click.option("--commit", is_flag=True, help="Commit docs/architecture.md to the repo after writing")
def diagram_cmd(repo, diagram_all, model, commit):
    """Generate Mermaid architecture diagrams for a managed repo.

    Reads .control/repo.yaml, scans the repo, calls Claude API, and writes
    docs/architecture.md with flowchart/data-flow/CLI-tree/module diagrams.
    """
    sys.path.insert(0, str(SCRIPTS_DIR))
    from diagram import run
    run(repo=repo, all_repos=diagram_all, model=model, commit=commit)


@main.command("readme")
@click.option("--repo", required=True, help="Repo name from registry")
@click.option("--init", is_flag=True, help="Generate from scratch (even if README exists)")
@click.option("--update", is_flag=True, help="Only refresh auto-generated sections")
@click.option("--dry-run", is_flag=True, help="Print to stdout, don't write")
def readme_cmd(repo, init, update, dry_run):
    """Generate or augment README.md for a managed repo.

    Default: if README exists and has content, updates auto-sections only.
    If README is missing/stub, generates from scratch using CLAUDE.md, CLI --help, and dir tree.
    """
    args = [sys.executable, str(SCRIPTS_DIR / "generate_readme.py"), f"--repo={repo}"]
    if init:
        args.append("--init")
    if update:
        args.append("--update")
    if dry_run:
        args.append("--dry-run")
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

    # Deduplicate by name
    seen = set()
    deduped = []
    for r in repos:
        if r["name"] not in seen:
            seen.add(r["name"])
            deduped.append(r)
    repos = deduped

    if category:
        repos = [r for r in repos if r["category"] == category]

    total = len(repos)
    print(f"\n{C['bold']}  devctl list{C['reset']}  {C['dim']}{total} repos{C['reset']}\n")

    # Group by category
    groups: dict[str, list] = {}
    for repo in repos:
        cat = repo.get("category", "other")
        groups.setdefault(cat, []).append(repo)

    for cat in sorted(groups):
        cat_repos = groups[cat]
        print(f"  {C['bold']}{cat}{C['reset']} {C['dim']}({len(cat_repos)}){C['reset']}")
        for repo in cat_repos:
            vis = repo.get("visibility", "private")
            dot = f"{C['green']}\u25cf{C['reset']}" if vis == "private" else f"{C['yellow']}\u25cf{C['reset']}"
            name = repo["name"]
            lang = repo.get("language", "-")
            priority = repo.get("priority", "-")
            print(f"    {dot} {name:<20s} {C['dim']}{lang:<10s} {vis:<10s}{C['reset']} {priority}")
        print()


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


@main.command("validate-secrets")
@click.option("--repo", default=None, help="Validate a specific repo")
@click.option("--live", is_flag=True, help="Ping endpoints to verify keys work")
@click.option("--keys-only", is_flag=True, help="Just show key inventory")
def validate_secrets_cmd(repo, live, keys_only):
    """Validate that repos have the API keys their profiles require."""
    args = [sys.executable, str(SCRIPTS_DIR / "validate_secrets.py")]
    if repo:
        args.append(f"--repo={repo}")
    if live:
        args.append("--live")
    if keys_only:
        args.append("--keys-only")
    subprocess.run(args)


@main.command("deploy-pages")
@click.option("--section", default=None, help="Deploy a specific section")
@click.option("--pending", is_flag=True, help="Include pending (not yet deployed) sections")
@click.option("--dry-run", is_flag=True, help="Show what would be deployed")
@click.option("--push", is_flag=True, help="Commit + push the hub repo after deploy")
@click.option("--verify", is_flag=True, help="Verify encrypted pages decrypt correctly")
@click.option("--auto", is_flag=True, help="Auto-detect section from current directory")
def deploy_pages_cmd(section, pending, dry_run, push, verify, auto):
    """Deploy encrypted HTML pages to jthorvaldur.github.io."""
    args = [sys.executable, str(SCRIPTS_DIR / "deploy_pages.py")]
    if section:
        args.append(f"--section={section}")
    if pending:
        args.append("--pending")
    if dry_run:
        args.append("--dry-run")
    if push:
        args.append("--push")
    if verify:
        args.append("--verify")
    if auto:
        args.append("--auto")
    subprocess.run(args)


@main.command("audit-pages")
def audit_pages_cmd():
    """Audit GitHub Pages for encryption and security policy compliance."""
    subprocess.run([sys.executable, str(SCRIPTS_DIR / "audit_pages_security.py")])


@main.command("verify-pages")
@click.option("--section", default=None, help="Verify a specific section")
@click.option("--quick", is_flag=True, help="One page per section")
def verify_pages_cmd(section, quick):
    """Live-verify deployed pages decrypt correctly via HTTPS."""
    args = [sys.executable, str(SCRIPTS_DIR / "verify_pages_live.py")]
    if section:
        args.append(f"--section={section}")
    if quick:
        args.append("--quick")
    subprocess.run(args)


@main.command("search")
@click.argument("query")
@click.option("--limit", "-n", default=20, help="Number of results")
@click.option("--collection", "-c", default=None, help="Search specific collection")
@click.option("--collections", default=None, help="Comma-separated collection names")
@click.option("--claude", is_flag=True, help="Search AI-assistant chats (Claude Code sessions, Claude.ai, ChatGPT)")
@click.option("--algos", is_flag=True, help="Search the algorithms collection")
@click.option("--facts", is_flag=True, help="Search fact collections (fact_registry, case facts)")
@click.option("--all", "everything", is_flag=True, help="Include AI chats alongside the default scope")
@click.option("--rerank/--no-rerank", default=True, help="Cross-encoder reranking (default: on)")
@click.option("--tau", type=float, default=None, help="Recency decay τ in days (default: 180)")
@click.option("--recency", type=float, default=None, help="Recency weight λ in [0,1] (default: 0.25)")
@click.option("--recent", is_flag=True, help="Aggressive recency preset (τ=14d, λ=0.6)")
@click.option("--no-recency", is_flag=True, help="Disable recency kernel")
@click.option("--today", default=None, help="Override today as YYYY-MM-DD (for testing)")
def search_cmd(query, limit, collection, collections, claude, algos, facts, everything,
               rerank, tau, recency, recent, no_recency, today):
    """Unified search across vector collections.

    Default scope: ingested docs, court files, facts, and algorithms —
    AI-assistant chats are excluded so they don't crowd out source documents.
    Use --claude to search chats, --all to include everything.
    """
    args = [sys.executable, str(SCRIPTS_DIR / "search_unified.py"), query]
    if limit != 20:
        args.extend(["--limit", str(limit)])
    if collection:
        args.extend(["--collection", collection])
    if collections:
        args.extend(["--collections", collections])
    if claude:
        args.append("--claude")
    if algos:
        args.append("--algos")
    if facts:
        args.append("--facts")
    if everything:
        args.append("--all")
    if not rerank:
        args.append("--no-rerank")
    if recent:
        args.append("--recent")
    if no_recency:
        args.append("--no-recency")
    if tau is not None:
        args.extend(["--tau", str(tau)])
    if recency is not None:
        args.extend(["--recency", str(recency)])
    if today:
        args.extend(["--today", today])
    subprocess.run(args)


@main.command("embed")
@click.option("--repo", required=True, help="Repo name from registry")
@click.option("--full", is_flag=True, help="Full re-embed (clear state)")
@click.option("--gpu", is_flag=True, help="Offload to Vast.ai GPU")
@click.option("--collection", default=None, help="Specific collection")
def embed_cmd(repo, full, gpu, collection):
    """Trigger embedding for a repo's vector collection."""
    args = [sys.executable, str(SCRIPTS_DIR / "embed.py"), f"--repo={repo}"]
    if full:
        args.append("--full")
    if gpu:
        args.append("--gpu")
    if collection:
        args.extend(["--collection", collection])
    subprocess.run(args)


@main.command("db-status")
@click.option("--repo", default=None, help="Show only this repo's collections")
@click.option("--port", type=int, default=None, help="Show only this port")
def db_status_cmd(repo, port):
    """Show database status: repos, collections, data sources, live counts."""
    args = [sys.executable, str(SCRIPTS_DIR / "db_status.py")]
    if repo:
        args.append(f"--repo={repo}")
    if port:
        args.append(f"--port={port}")
    subprocess.run(args)


@main.command("audit-vectors")
@click.option("--repo", default=None, help="Filter to a specific repo's collections")
def audit_vectors_cmd(repo):
    """Audit vector collection health across all Qdrant instances."""
    args = [sys.executable, str(SCRIPTS_DIR / "audit_vectors.py")]
    if repo:
        args.append(f"--repo={repo}")
    subprocess.run(args)


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


@main.command("provenance")
@click.argument("action", type=click.Choice(["show", "stale", "rebuild", "list"]))
@click.argument("path", required=False, default=None)
@click.option("--repo", default=None, help="Filter to a specific repo")
def provenance_cmd(action, path, repo):
    """Track build provenance — what generated each output and how to recreate it."""
    args = [sys.executable, str(SCRIPTS_DIR / "provenance_index.py")]
    if action == "show" and path:
        args.extend(["show", path])
    elif action == "rebuild":
        args.append("rebuild")
    elif action == "stale":
        args.append("stale")
    elif action == "list":
        args.append("list")
        if repo:
            args.append(f"--repo={repo}")
    else:
        args.append(action)
    subprocess.run(args)


@main.command("benchmark")
@click.option("--category", default=None, help="Only run this category (embed, db_upsert, db_query, generate)")
@click.option("--compare", is_flag=True, help="Compare against historical results")
@click.option("--project", type=int, default=None, help="Project time at this scale (number of items)")
def benchmark_cmd(category, compare, project):
    """Benchmark system operations — embed, upsert, query, encrypt."""
    args = [sys.executable, str(SCRIPTS_DIR / "benchmark.py")]
    if category:
        args.append(f"--category={category}")
    if compare:
        args.append("--compare")
    if project:
        args.append(f"--project={project}")
    subprocess.run(args)


@main.command("traffic")
@click.option("--repo", default=None, help="Show detailed traffic for a specific repo")
@click.option("--sort", default="clones", type=click.Choice(["clones", "views", "name"]),
              help="Sort order (default: clones)")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
def traffic_cmd(repo, sort, as_json):
    """GitHub traffic stats — clones, views, referrers across all repos."""
    args = [sys.executable, str(SCRIPTS_DIR / "traffic.py")]
    if repo:
        args.append(f"--repo={repo}")
    if sort != "clones":
        args.append(f"--sort={sort}")
    if as_json:
        args.append("--json")
    subprocess.run(args)


@main.command("graph")
@click.argument("action", type=click.Choice(["status", "populate", "query", "demo"]))
@click.argument("query_text", required=False)
def graph_cmd(action, query_text):
    """Knowledge graph — status, populate, query, demo."""
    if action == "populate":
        args = [sys.executable, str(SCRIPTS_DIR / "populate_graph.py"), "--facts", "--entities"]
        subprocess.run(args)
        # Also load CaseLedger data
        args2 = [sys.executable, str(SCRIPTS_DIR / "populate_graph_caseledger.py")]
        subprocess.run(args2)
    elif action == "status":
        args = [sys.executable, str(SCRIPTS_DIR / "populate_graph.py"), "--stats"]
        subprocess.run(args)
    elif action == "demo":
        args = [sys.executable, str(SCRIPTS_DIR / "populate_graph.py"), "--demo"]
        subprocess.run(args)
    elif action == "query":
        if not query_text:
            print(f"  {C['red']}Usage: devctl graph query \"concept name or topic\"{C['reset']}")
            return
        import base64
        import json
        import urllib.request
        creds = base64.b64encode(b"neo4j:devctl-graph").decode()
        # Search across Concepts, Facts, and Categories
        qt = query_text.replace("'", "")
        cypher_concept = (
            f"MATCH (c:Concept) WHERE toLower(c.name) CONTAINS toLower('{qt}') "
            f"OR ANY(t IN c.tags WHERE toLower(t) CONTAINS toLower('{qt}')) "
            "OPTIONAL MATCH (c)-[r]-(other) WHERE other:Concept OR other:Category "
            "RETURN 'Concept' AS type, c.name AS name, c.domain AS domain, "
            "collect(DISTINCT {rel: type(r), target: other.name, desc: r.description}) AS connections "
            "LIMIT 5"
        )
        cypher_fact = (
            f"MATCH (f:Fact) WHERE toLower(f.name) CONTAINS toLower('{qt}') "
            f"OR toLower(f.text) CONTAINS toLower('{qt}') "
            "OPTIONAL MATCH (f)-[:IN_CATEGORY]->(cat:Category) "
            "OPTIONAL MATCH (f)-[:RELATES_TO]->(c:Concept) "
            "RETURN 'Fact' AS type, f.name AS name, f.confidence AS domain, "
            "collect(DISTINCT {rel: 'IN_CATEGORY', target: cat.name, desc: ''}) + "
            "collect(DISTINCT {rel: 'RELATES_TO', target: c.name, desc: ''}) AS connections "
            "LIMIT 10"
        )
        cypher_cat = (
            f"MATCH (cat:Category) WHERE toLower(cat.name) CONTAINS toLower('{qt}') "
            "OPTIONAL MATCH (f:Fact)-[:IN_CATEGORY]->(cat) "
            "RETURN 'Category' AS type, cat.name AS name, cat.fact_count + ' facts' AS domain, "
            "collect(DISTINCT {rel: 'contains', target: f.name, desc: ''}) AS connections "
            "LIMIT 5"
        )
        # CaseFacts from CaseLedger
        cypher_casefact = (
            f"MATCH (f:CaseFact) WHERE toLower(f.statement) CONTAINS toLower('{qt}') "
            "RETURN 'CaseFact' AS type, f.statement AS name, f.confidence + ' / ' + f.category AS domain, "
            "[] AS connections "
            f"LIMIT 20"
        )
        # Parties — show the party with full mention count + sample facts
        cypher_party = (
            f"MATCH (p:Party) WHERE toLower(p.name) CONTAINS toLower('{qt}') "
            "OPTIONAL MATCH (f:CaseFact)-[:MENTIONS_PARTY]->(p) "
            "WITH p, count(f) AS total, collect(f.statement)[0..8] AS samples "
            "RETURN 'Party' AS type, p.name AS name, p.party_type + ' (' + toString(total) + ' facts)' AS domain, "
            "[s IN samples | {rel: 'mentioned in', target: left(s, 80), desc: ''}] AS connections "
            "LIMIT 5"
        )
        payload = json.dumps({"statements": [
            {"statement": cypher_concept},
            {"statement": cypher_fact},
            {"statement": cypher_cat},
            {"statement": cypher_casefact},
            {"statement": cypher_party},
        ]}).encode()
        req = urllib.request.Request(
            "http://localhost:7474/db/neo4j/tx/commit", data=payload,
            headers={"Content-Type": "application/json", "Authorization": f"Basic {creds}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            all_results = []
            for result_set in data["results"]:
                all_results.extend(result_set["data"])
            if not all_results:
                print(f"  No results matching '{query_text}'")
                return
            for row in all_results:
                node_type, name, domain, conns = row["row"]
                label = f"{C['cyan']}{node_type}{C['reset']}" if node_type != "Concept" else f"{C['mag']}{node_type}{C['reset']}"
                print(f"\n  {label}  {C['bold']}{name}{C['reset']}  {C['dim']}({domain}){C['reset']}")
                shown = 0
                for conn in conns:
                    if conn.get("target") and shown < 8:
                        print(f"    {conn['rel']:>20}  {conn['target']}")
                        if conn.get("desc"):
                            print(f"    {' ' * 20}  {C['dim']}{conn['desc']}{C['reset']}")
                        shown += 1
                if len(conns) > 8:
                    print(f"    {C['dim']}... +{len(conns) - 8} more{C['reset']}")
            print()
        except Exception as e:
            print(f"  {C['red']}Neo4j unreachable: {e}{C['reset']}")


FASTAPI_SERVICES = {
    "daylight": {
        "port": 8000,
        "repo": "daylight",
        "cmd": ["uv", "run", "uvicorn", "src.api.main:app", "--host", "127.0.0.1", "--port", "8000"],
        "desc": "Document intelligence API",
    },
    "docvec": {
        "port": 8100,
        "repo": "docvec",
        "cmd": ["uv", "run", "--extra", "service", "uvicorn", "docvec.service:app", "--host", "127.0.0.1", "--port", "8100"],
        "desc": "Embedding & reranking service",
    },
}


@main.command("services")
@click.argument("action", type=click.Choice(["status", "start", "stop"]))
@click.argument("name", required=False)
def services_cmd(action, name):
    """Manage FastAPI services — status, start, stop."""
    import json
    import signal
    import urllib.request

    github_dir = Path.home() / "GitHub"

    def _check(svc_name, svc):
        try:
            req = urllib.request.Request(f"http://localhost:{svc['port']}/health")
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read())
                return True, data
        except Exception:
            return False, {}

    def _find_pid(port):
        try:
            result = subprocess.run(
                ["lsof", "-ti", f":{port}"],
                capture_output=True, text=True, timeout=5,
            )
            pids = result.stdout.strip().split("\n")
            return [int(p) for p in pids if p.strip()]
        except Exception:
            return []

    if action == "status":
        targets = {name: FASTAPI_SERVICES[name]} if name and name in FASTAPI_SERVICES else FASTAPI_SERVICES
        print(f"\n{C['bold']}  FastAPI Services{C['reset']}\n")
        for svc_name, svc in targets.items():
            alive, data = _check(svc_name, svc)
            if alive:
                version = data.get("version", "")
                models = data.get("models", {})
                detail = f"v{version}" if version else ", ".join(models.keys()) if models else "ok"
                pids = _find_pid(svc["port"])
                pid_str = f"  pid {pids[0]}" if pids else ""
                print(f"  {C['green']}●{C['reset']} {svc_name:<12} :{svc['port']}  {detail}{pid_str}  {C['dim']}{svc['desc']}{C['reset']}")
            else:
                print(f"  {C['red']}●{C['reset']} {svc_name:<12} :{svc['port']}  stopped  {C['dim']}{svc['desc']}{C['reset']}")
        print()

    elif action == "start":
        targets = {name: FASTAPI_SERVICES[name]} if name and name in FASTAPI_SERVICES else FASTAPI_SERVICES
        for svc_name, svc in targets.items():
            alive, _ = _check(svc_name, svc)
            if alive:
                print(f"  {C['green']}●{C['reset']} {svc_name} already running on :{svc['port']}")
                continue
            repo_dir = github_dir / svc["repo"]
            if not repo_dir.exists():
                print(f"  {C['red']}●{C['reset']} {svc_name}: repo not found at {repo_dir}")
                continue
            log_dir = Path.home() / ".local" / "share" / "devctl" / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / f"{svc_name}.log"
            with open(log_file, "a") as lf:
                proc = subprocess.Popen(
                    svc["cmd"], cwd=repo_dir,
                    stdout=lf, stderr=lf,
                    start_new_session=True,
                )
            print(f"  {C['green']}●{C['reset']} {svc_name} started on :{svc['port']}  pid {proc.pid}  {C['dim']}log: {log_file}{C['reset']}")

    elif action == "stop":
        targets = {name: FASTAPI_SERVICES[name]} if name and name in FASTAPI_SERVICES else FASTAPI_SERVICES
        for svc_name, svc in targets.items():
            pids = _find_pid(svc["port"])
            if not pids:
                print(f"  {C['dim']}●{C['reset']} {svc_name} not running")
                continue
            for pid in pids:
                try:
                    os.kill(pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            print(f"  {C['yellow']}●{C['reset']} {svc_name} stopped  {C['dim']}pid {', '.join(str(p) for p in pids)}{C['reset']}")


@main.command("health")
def health_cmd():
    """System health check — services, data, repos, pages, disk."""
    import json
    import shutil
    import urllib.request

    import yaml

    print(f"\n{C['bold']}  System Health{C['reset']}")
    print(f"  {'─'*60}\n")

    # ── Services ──
    print(f"  {C['bold']}Services{C['reset']}")

    # Docker
    try:
        result = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}\t{{.Status}}"],
            capture_output=True, text=True, timeout=5,
        )
        containers = [l.split("\t") for l in result.stdout.strip().split("\n") if l]
        print(f"  {C['green']}●{C['reset']} Docker       {len(containers)} containers  {C['dim']}{', '.join(c[0] for c in containers)}{C['reset']}")
    except Exception:
        print(f"  {C['red']}●{C['reset']} Docker       unreachable  {C['dim']}fix: open Docker Desktop{C['reset']}")

    # Ollama
    try:
        url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        req = urllib.request.Request(f"{url}/api/tags")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())
            model_names = [m.get("name", "?") for m in data.get("models", [])]
            print(f"  {C['green']}●{C['reset']} Ollama       {len(model_names)} models  {C['dim']}{', '.join(model_names)}{C['reset']}")
    except Exception:
        print(f"  {C['red']}●{C['reset']} Ollama       unreachable  {C['dim']}fix: ollama serve{C['reset']}")

    # FastAPI services
    fastapi_services = [
        ("Daylight", 8000, "daylight", "uv run uvicorn src.api.main:app --host 127.0.0.1 --port 8000"),
        ("Docvec", 8100, "docvec", "uv run --extra service uvicorn docvec.service:app --host 127.0.0.1 --port 8100"),
    ]
    for name, port, repo, start_cmd in fastapi_services:
        try:
            req = urllib.request.Request(f"http://localhost:{port}/health")
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read())
                version = data.get("version", "")
                models = data.get("models", {})
                detail = f"v{version}" if version else ", ".join(f"{k}" for k in models)
                print(f"  {C['green']}●{C['reset']} {name:<12} :{port}  {C['dim']}{detail}{C['reset']}")
        except Exception:
            print(f"  {C['red']}●{C['reset']} {name:<12} :{port} unreachable  {C['dim']}fix: devctl services start {repo}{C['reset']}")

    # ── Data ──
    print(f"\n  {C['bold']}Data{C['reset']}")

    # Qdrant — live counts per collection with drift detection
    try:
        from qdrant_client import QdrantClient

        # Load registry for expected counts
        try:
            with open(REGISTRIES_DIR / "vector-collections.yaml") as f:
                vcols_reg = yaml.safe_load(f).get("collections", {})
        except Exception:
            vcols_reg = {}

        for port in [6333, 7333, 8333]:
            try:
                # :8333 runs an older server (1.14); skip the compat check to
                # avoid a cosmetic version-mismatch UserWarning on connect.
                kw = {"check_compatibility": False} if port == 8333 else {}
                client = QdrantClient(host="localhost", port=port, timeout=5, **kw)
                cols = client.get_collections().collections
                total = 0
                drifted = []
                for c in cols:
                    info = client.get_collection(c.name)
                    count = info.points_count or 0
                    total += count
                    reg_entry = vcols_reg.get(c.name, {})
                    expected = reg_entry.get("points_expected", 0) if reg_entry.get("port", 6333) == port else 0
                    if expected and abs(count - expected) / max(expected, 1) > 0.05:
                        drifted.append(f"{c.name}:{count:,}(exp {expected:,})")
                status = C["green"]
                extra = ""
                if drifted:
                    status = C["yellow"]
                    extra = f"  {C['dim']}drift: {', '.join(drifted)}{C['reset']}"
                print(f"  {status}●{C['reset']} Qdrant :{port}  {len(cols)} collections  {total:,} vectors{extra}")
            except Exception:
                print(f"  {C['red']}●{C['reset']} Qdrant :{port}  unreachable  {C['dim']}fix: docker start qdrant{C['reset']}")
    except ImportError:
        pass

    # Source files backing the vectors
    try:
        with open(REGISTRIES_DIR / "vector-collections.yaml") as f:
            vcols = yaml.safe_load(f).get("collections", {})

        source_dirs = {
            "div_legal": ("~/GitHub/div_legal/sdata/md", "*.md"),
            "contacts": ("~/GitHub/contacts/data", "**/*.jsonl"),
            "energy_texas": ("~/GitHub/energy_texas/reports", "*.html"),
        }
        file_counts = []
        for repo, (dir_pattern, glob) in source_dirs.items():
            d = Path(dir_pattern).expanduser()
            if d.exists():
                count = len(list(d.glob(glob)))
                file_counts.append(f"{repo}:{count}")
        if file_counts:
            print(f"  {C['dim']}  source files  {', '.join(file_counts)}{C['reset']}")
    except Exception:
        pass

    # Postgres
    try:
        result = subprocess.run(
            ["docker", "exec", "infra-postgres-1", "psql", "-U", "caseledger", "-d", "caseledger",
             "-t", "-c", "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'"],
            capture_output=True, text=True, timeout=5,
        )
        tables = result.stdout.strip()
        if tables:
            print(f"  {C['green']}●{C['reset']} Postgres     :5433  {tables} tables  {C['dim']}caseledger{C['reset']}")
    except Exception:
        pass

    # Neo4j
    try:
        import base64
        creds = base64.b64encode(b"neo4j:devctl-graph").decode()
        req = urllib.request.Request(
            "http://localhost:7474/db/neo4j/tx/commit",
            data=json.dumps({"statements": [
                {"statement": "MATCH (n) RETURN count(n) AS nodes"},
                {"statement": "MATCH ()-[r]->() RETURN count(r) AS edges"},
            ]}).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Basic {creds}"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            nodes = data["results"][0]["data"][0]["row"][0]
            edges = data["results"][1]["data"][0]["row"][0]
            print(f"  {C['green']}●{C['reset']} Neo4j        :7687  {nodes} nodes  {edges} edges  {C['dim']}knowledge graph{C['reset']}")
    except Exception:
        print(f"  {C['red']}●{C['reset']} Neo4j        :7687  unreachable  {C['dim']}fix: docker compose -f infra/docker-compose.yml up -d neo4j{C['reset']}")

    # ── Repos ──
    print(f"\n  {C['bold']}Repos{C['reset']}")
    try:
        import concurrent.futures

        with open(REGISTRIES_DIR / "repos.yaml") as f:
            repos = yaml.safe_load(f).get("repos", [])
        github_dir = Path.home() / "GitHub"
        git_dirs = [d for d in github_dir.iterdir() if d.is_dir() and (d / ".git").exists()] if github_dir.exists() else []
        on_disk = len(git_dirs)

        def _is_dirty(d):
            try:
                r = subprocess.run(["git", "status", "-s"], cwd=d, capture_output=True, text=True, timeout=5)
                return bool(r.stdout.strip())
            except Exception:
                return False

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            dirty = sum(pool.map(_is_dirty, git_dirs))
        clean = on_disk - dirty
        print(f"  {C['green']}●{C['reset']} Repos        {len(repos)} registered  {on_disk} on disk  "
              f"{C['green']}{clean} clean{C['reset']}  {C['yellow']}{dirty} dirty{C['reset']}")
    except Exception:
        pass

    # ── Pages ──
    print(f"\n  {C['bold']}Pages{C['reset']}")
    try:
        with open(REGISTRIES_DIR / "pages.yaml") as f:
            pages_data = yaml.safe_load(f)
        deployed = pages_data.get("sections", {})
        pending = pages_data.get("pending", {})

        # Count actual HTML files on disk in hub
        hub = Path.home() / "GitHub" / "jthorvaldur.github.io" / "r"
        html_files = [f for f in hub.rglob("*.html") if "_originals" not in str(f)] if hub.exists() else []
        html_on_disk = len(html_files)
        encrypted = 0
        for f in html_files:
            try:
                with open(f, "r", errors="ignore") as fh:
                    head = fh.read(4000)
                if "const SALT" in head or "AES-GCM" in head:
                    encrypted += 1
            except Exception:
                pass

        print(f"  {C['green']}●{C['reset']} GitHub Pages  {len(deployed)} deployed  {len(pending)} pending  "
              f"{html_on_disk} HTML files  {C['green']}{encrypted} encrypted{C['reset']}")
    except Exception:
        pass

    # ── Build ──
    print(f"\n  {C['bold']}Build{C['reset']}")

    # Provenance
    prov_db = Path.home() / ".local" / "share" / "devctl" / "provenance.db"
    if prov_db.exists():
        import sqlite3
        conn = sqlite3.connect(str(prov_db))
        count = conn.execute("SELECT COUNT(*) FROM builds").fetchone()[0]
        repos_tracked = conn.execute("SELECT COUNT(DISTINCT repo) FROM builds").fetchone()[0]
        conn.close()
        print(f"  {C['green']}●{C['reset']} Provenance   {count} builds tracked  {repos_tracked} repos")
    else:
        print(f"  {C['yellow']}●{C['reset']} Provenance   no index  {C['dim']}fix: devctl provenance rebuild{C['reset']}")

    # Benchmarks
    bench_file = Path(__file__).parent.parent.parent / ".profiling" / "benchmarks.jsonl"
    if bench_file.exists():
        lines = sum(1 for _ in open(bench_file))
        print(f"  {C['green']}●{C['reset']} Benchmarks   {lines} measurements on file")
    else:
        print(f"  {C['yellow']}●{C['reset']} Benchmarks   none  {C['dim']}fix: devctl benchmark{C['reset']}")

    # ── Disk ──
    print(f"\n  {C['bold']}Disk{C['reset']}")
    import platform
    total, used, free = shutil.disk_usage(str(Path.home()))
    if platform.system() == "Darwin":
        try:
            result = subprocess.run(
                ["df", "-k", str(Path.home())],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                parts = result.stdout.strip().split("\n")[-1].split()
                if len(parts) >= 4:
                    df_free = int(parts[3]) * 1024
                    df_total = int(parts[1]) * 1024
                    if df_free > free:
                        free = df_free
                        total = df_total
        except Exception:
            pass
    pct = ((total - free) / total) * 100
    color = C["green"] if pct < 80 else C["yellow"] if pct < 90 else C["red"]
    try:
        result = subprocess.run(
            ["du", "-sh", str(Path.home() / "GitHub")],
            capture_output=True, text=True, timeout=30,
        )
        github_size = result.stdout.split("\t")[0].strip() if result.returncode == 0 else "?"
    except subprocess.TimeoutExpired:
        github_size = "?"
    except Exception:
        github_size = "?"
    print(f"  {color}●{C['reset']} Storage      {free // (1024**3)}GB free ({100 - pct:.0f}%)  ~/GitHub = {github_size}")

    print()


@main.group("subscriptions", invoke_without_command=True)
@click.pass_context
def subscriptions_group(ctx):
    """Subscription registry — list, check health, show costs."""
    if ctx.invoked_subcommand is None:
        # Default: show list
        subprocess.run([sys.executable, str(SCRIPTS_DIR / "subscriptions.py"), "list"])


@subscriptions_group.command("list")
@click.option("--status", default=None,
              type=click.Choice(["active", "overdue", "review", "expiring", "expired"]),
              help="Filter by status")
@click.option("--category", default=None, help="Filter by category")
def subscriptions_list(status, category):
    """List all subscriptions grouped by status."""
    args = [sys.executable, str(SCRIPTS_DIR / "subscriptions.py"), "list"]
    if status:
        args.append(f"--status={status}")
    if category:
        args.append(f"--category={category}")
    subprocess.run(args)


@subscriptions_group.command("check")
def subscriptions_check():
    """Run health checks and balance checks for services."""
    subprocess.run([sys.executable, str(SCRIPTS_DIR / "subscriptions.py"), "check"])


@subscriptions_group.command("costs")
def subscriptions_costs():
    """Show cost breakdown with annual projections and savings opportunities."""
    subprocess.run([sys.executable, str(SCRIPTS_DIR / "subscriptions.py"), "costs"])


if __name__ == "__main__":
    main()
