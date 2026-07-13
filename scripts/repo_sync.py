#!/usr/bin/env python3
"""Sync control plane templates to managed repos.

Pushes .control/repo.yaml templates and .env.example to repos
that are missing them. Does NOT overwrite existing files unless --force.
"""

import shutil
import sys
from pathlib import Path

import yaml

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

# Agent operating process pack (templates/processes/README.md):
# enforcement hooks, agent contracts, model routing, process docs, evals.
AGENT_PROCESS_PACK = [
    "claude/settings.json",
    "claude/hooks/session-start-intent.sh",
    "claude/hooks/post-compact-reinject.sh",
    "claude/hooks/session-routing-audit.sh",
    "claude/hooks/pre-tool-risk-guard.sh",
    "claude/hooks/post-tool-evidence-logger.sh",
    "claude/hooks/delivery-gate.sh",
    "claude/hooks/pre-compact-handoff.sh",
    "contracts/agents.yaml",
    "contracts/model-routing.yaml",
    "processes/README.md",
    "processes/01-outside-audit.md",
    "processes/02-chief-operator.md",
    "processes/03-agent-team-contracts.md",
    "processes/04-hooks-over-instructions.md",
    "processes/05-improvement-loop.md",
    "processes/06-model-routing.md",
    "evals/README.md",
    "evals/e000-template.sh",
    "evals/e001-enforcement-files-exist.sh",
    "scripts/test.sh",
]


def load_registry() -> list[dict]:
    registry_path = Path(__file__).parent.parent / "registries" / "repos.yaml"
    with open(registry_path) as f:
        data = yaml.safe_load(f)
    return data.get("repos", [])


def sync_file(template_name: str, dest_path: Path, force: bool = False) -> str:
    """Copy a template file to a destination if missing. Returns status."""
    src = TEMPLATES_DIR / template_name
    if not src.exists():
        return "template_missing"
    if dest_path.exists() and not force:
        return "exists"
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest_path)
    if dest_path.suffix == ".sh":
        dest_path.chmod(0o755)
    return "synced"


def sync_repo(repo: dict, files: list[str], force: bool = False, dry_run: bool = False) -> list[dict]:
    """Sync template files to a single repo. Returns list of actions."""
    path = repo.get("path")
    if not path:
        return [{"file": "*", "status": "no_path"}]

    repo_path = Path(path).expanduser()
    if not repo_path.exists():
        return [{"file": "*", "status": "not_found"}]

    actions = []
    for template_file in files:
        # Map template names to repo destinations
        if template_file == "repo.yaml":
            dest = repo_path / ".control" / "repo.yaml"
        elif template_file.startswith("claude/"):
            # claude/* templates land under .claude/ (hooks that inject the
            # repo's md files into every agent session — anti-drift)
            dest = repo_path / ".claude" / template_file.removeprefix("claude/")
        else:
            dest = repo_path / template_file

        if dry_run:
            exists = dest.exists()
            actions.append({
                "file": template_file,
                "status": "would_skip (exists)" if exists and not force else "would_sync",
            })
        else:
            status = sync_file(template_file, dest, force=force)
            actions.append({"file": template_file, "status": status})

    return actions


def sync_all(
    files: list[str] | None = None,
    repo_filter: str | None = None,
    force: bool = False,
    dry_run: bool = False,
):
    """Sync templates to all managed repos."""
    if files is None:
        files = [".env.example"]

    repos = load_registry()
    if repo_filter:
        repos = [r for r in repos if r["name"] == repo_filter]

    synced_count = 0
    skip_count = 0

    print(f"Syncing {len(files)} template(s) to {len(repos)} repo(s)" +
          (" (dry run)" if dry_run else ""), file=sys.stderr)

    for repo in repos:
        name = repo["name"]
        actions = sync_repo(repo, files, force=force, dry_run=dry_run)

        has_work = any(a["status"] in ("synced", "would_sync") for a in actions)
        if has_work or repo_filter:
            print(f"\n  {name}:")
            for a in actions:
                icon = {"synced": "+", "would_sync": "+", "exists": "=",
                         "would_skip (exists)": "=", "no_path": "-", "not_found": "!",
                         "template_missing": "?"}.get(a["status"], "?")
                print(f"    [{icon}] {a['file']}: {a['status']}")
                if "sync" in a["status"]:
                    synced_count += 1
                elif a["status"] in ("exists", "would_skip (exists)"):
                    skip_count += 1

    print(f"\nSynced: {synced_count}  Skipped (exists): {skip_count}", file=sys.stderr)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Sync templates to managed repos")
    parser.add_argument("--files", default=None,
                        help="Comma-separated template files (default: .env.example)")
    parser.add_argument("--repo", default=None, help="Sync to specific repo only")
    parser.add_argument("--force", action="store_true", help="Overwrite existing files")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be synced")
    parser.add_argument("--all-templates", action="store_true",
                        help="Sync all templates: .env.example, .gitignore")

    args = parser.parse_args()

    files = None
    if args.files:
        files = [f.strip() for f in args.files.split(",")]
    elif args.all_templates:
        files = [".env.example", ".gitignore"]

    sync_all(
        files=files,
        repo_filter=args.repo,
        force=args.force,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
