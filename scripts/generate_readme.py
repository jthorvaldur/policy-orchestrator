#!/usr/bin/env python3
"""Generate or augment README.md for a managed repo.

Modes:
  --init    Generate from scratch (repos with no/stub README)
  --update  Augment existing README — add missing sections, refresh auto-generated
            sections (between <!-- AUTO:X --> markers), preserve everything else
  (default) If README exists and is >100 bytes, uses --update. Otherwise --init.

Sources: CLAUDE.md, pyproject.toml/package.json, directory tree, git log,
CLI --help output, existing README content.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

REGISTRIES = Path(__file__).parent.parent / "registries"


def load_repos():
    with open(REGISTRIES / "repos.yaml") as f:
        return {r["name"]: r for r in yaml.safe_load(f).get("repos", [])}


def run(cmd, cwd=None, timeout=10):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def get_description(repo_path):
    """Extract description from CLAUDE.md or pyproject.toml."""
    claude_md = repo_path / "CLAUDE.md"
    if claude_md.exists():
        content = claude_md.read_text()
        in_overview = False
        desc_lines = []
        for line in content.split("\n"):
            if line.startswith("## Overview"):
                in_overview = True
                continue
            if in_overview:
                if line.startswith("##"):
                    break
                if line.strip() and not line.startswith(">") and not line.startswith("#"):
                    desc_lines.append(line.strip())
        if desc_lines:
            return " ".join(desc_lines)

    pyproject = repo_path / "pyproject.toml"
    if pyproject.exists():
        for line in pyproject.read_text().split("\n"):
            if line.strip().startswith("description"):
                return line.split("=", 1)[1].strip().strip('"')

    return ""


def detect_cli(repo_path):
    """Try to detect CLI tools and get their --help output."""
    cli_help = {}

    # Check for executable scripts
    for candidate in ["gpu", "devctl", "main.py"]:
        path = repo_path / candidate
        if path.exists() and (path.stat().st_mode & 0o111 or candidate.endswith(".py")):
            if candidate.endswith(".py"):
                help_text = run(["python3", str(path), "--help"], cwd=str(repo_path), timeout=5)
            else:
                help_text = run([str(path), "--help"], cwd=str(repo_path), timeout=5)
            if help_text and len(help_text) > 20:
                cli_help[candidate] = help_text

    # Check pyproject.toml [project.scripts]
    pyproject = repo_path / "pyproject.toml"
    if pyproject.exists():
        content = pyproject.read_text()
        if "[project.scripts]" in content:
            in_scripts = False
            for line in content.split("\n"):
                if "[project.scripts]" in line:
                    in_scripts = True
                    continue
                if in_scripts:
                    if line.startswith("["):
                        break
                    if "=" in line:
                        cmd_name = line.split("=")[0].strip().strip('"')
                        help_text = run([cmd_name, "--help"], cwd=str(repo_path), timeout=5)
                        if help_text and len(help_text) > 20:
                            cli_help[cmd_name] = help_text

    # Check package.json scripts
    pkg_json = repo_path / "package.json"
    if pkg_json.exists():
        try:
            pkg = json.loads(pkg_json.read_text())
            for script_name in pkg.get("scripts", {}):
                if script_name in ("start", "dev", "build", "test"):
                    cli_help[f"npm run {script_name}"] = pkg["scripts"][script_name]
        except Exception:
            pass

    return cli_help


def get_tree_annotated(repo_path, max_depth=2):
    """Get directory tree with annotations from CLAUDE.md key files section."""
    skip = {".git", ".venv", "venv", "node_modules", "__pycache__", "target",
            ".ruff_cache", ".mypy_cache", ".pytest_cache", "dist", "build",
            ".DS_Store", ".claude-flow", ".swarm", ".dual-graph", ".claude",
            ".cursor", ".egg-info", "wheels", "uv.lock", ".control",
            ".env.example", ".gitignore"}

    lines = []

    def _walk(path, prefix, depth):
        if depth > max_depth:
            return
        try:
            entries = sorted(path.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
        except PermissionError:
            return

        dirs = [e for e in entries if e.is_dir() and e.name not in skip
                and not e.name.startswith(".")]
        files = [e for e in entries if e.is_file() and e.name not in skip
                 and not e.name.startswith(".")
                 and not e.name.endswith(".pyc")
                 and not e.name.endswith(".lock")]

        for f in files[:12]:
            lines.append(f"{prefix}├── {f.name}")
        if len(files) > 12:
            lines.append(f"{prefix}├── ... +{len(files) - 12} more")

        for i, d in enumerate(dirs[:8]):
            connector = "└── " if i == len(dirs) - 1 and not (len(files) > 12) else "├── "
            lines.append(f"{prefix}{connector}{d.name}/")
            child_prefix = prefix + ("    " if connector.startswith("└") else "│   ")
            _walk(d, child_prefix, depth + 1)

    lines.append(f"{repo_path.name}/")
    _walk(repo_path, "", 0)
    return lines


def generate_init(repo_name, repo_path, repo_config):
    """Generate a full README from scratch for repos without one."""
    desc = get_description(repo_path) or f"{repo_name} project."
    cli = detect_cli(repo_path)
    tree = get_tree_annotated(repo_path)
    category = repo_config.get("category", "")
    commit_count = run(["git", "rev-list", "--count", "HEAD"], cwd=str(repo_path)) or "?"

    sections = [f"# {repo_name}\n", f"{desc}\n"]

    # Quick start / CLI
    if cli:
        sections.append("## Quick Start\n")
        sections.append("```bash")
        for cmd_name, help_text in cli.items():
            # Extract just the usage line and first few commands
            for line in help_text.split("\n"):
                line = line.strip()
                if line.startswith("Usage:") or line.startswith("usage:"):
                    sections.append(f"# {line}")
                elif line and not line.startswith("-") and not line.startswith("Options"):
                    sections.append(f"  {line}")
            break  # just first CLI tool
        sections.append("```\n")

    # Architecture / Structure
    if tree:
        sections.append("## Structure\n")
        sections.append("```")
        for line in tree[:25]:
            sections.append(line)
        if len(tree) > 25:
            sections.append(f"... +{len(tree) - 25} more")
        sections.append("```\n")

    # Setup
    has_py = (repo_path / "pyproject.toml").exists()
    has_npm = (repo_path / "package.json").exists()
    has_cargo = (repo_path / "Cargo.toml").exists()
    has_go = (repo_path / "go.mod").exists()

    if has_py or has_npm or has_cargo or has_go:
        sections.append("## Setup\n")
        sections.append("```bash")
        if has_py:
            sections.append("uv sync")
        if has_npm:
            sections.append("npm install")
        if has_cargo:
            sections.append("cargo build --release")
        if has_go:
            sections.append("go build ./...")
        sections.append("```\n")

    # Footer
    sections.append("## Part of\n")
    sections.append(f"Managed by [policy-orchestrator](https://github.com/jthorvaldur/policy-orchestrator).")
    if category:
        sections.append(f"Category: {category}. {commit_count} commits.")
    sections.append("")

    return "\n".join(sections)


def generate_update(repo_name, repo_path, repo_config, existing):
    """Update an existing README — add auto-generated sections, keep everything else.

    Auto sections are wrapped in <!-- AUTO:section_name --> ... <!-- /AUTO:section_name -->
    Everything outside auto markers is preserved exactly.
    """
    commit_count = run(["git", "rev-list", "--count", "HEAD"], cwd=str(repo_path)) or "?"
    last_commit = run(["git", "log", "-1", "--format=%ar"], cwd=str(repo_path)) or "?"
    category = repo_config.get("category", "")

    # Build auto footer
    auto_footer = (
        f"<!-- AUTO:footer -->\n"
        f"Managed by [policy-orchestrator](https://github.com/jthorvaldur/policy-orchestrator). "
        f"Category: {category}. {commit_count} commits, last updated {last_commit}.\n"
        f"<!-- /AUTO:footer -->"
    )

    # Replace existing auto sections
    result = existing
    result = re.sub(
        r"<!-- AUTO:footer -->.*?<!-- /AUTO:footer -->",
        auto_footer,
        result,
        flags=re.DOTALL,
    )

    # If no auto footer exists, append it
    if "<!-- AUTO:footer -->" not in result:
        result = result.rstrip() + "\n\n" + auto_footer + "\n"

    return result


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Generate or augment README.md")
    parser.add_argument("--repo", required=True, help="Repo name from registry")
    parser.add_argument("--init", action="store_true", help="Force full generation (even if README exists)")
    parser.add_argument("--update", action="store_true", help="Only update auto-generated sections")
    parser.add_argument("--dry-run", action="store_true", help="Print to stdout, don't write")
    args = parser.parse_args()

    repos = load_repos()
    if args.repo not in repos:
        print(f"Repo '{args.repo}' not in registry", file=sys.stderr)
        sys.exit(1)

    repo_config = repos[args.repo]
    repo_path = Path(repo_config["path"]).expanduser()

    if not repo_path.exists():
        print(f"Repo path not found: {repo_path}", file=sys.stderr)
        sys.exit(1)

    readme_path = repo_path / "README.md"
    existing = readme_path.read_text() if readme_path.exists() else ""
    has_content = len(existing.strip()) > 100

    if args.init or not has_content:
        content = generate_init(args.repo, repo_path, repo_config)
        mode = "init"
    elif args.update or has_content:
        content = generate_update(args.repo, repo_path, repo_config, existing)
        mode = "update"

    if args.dry_run:
        print(content)
        print(f"\n(mode: {mode})", file=sys.stderr)
    else:
        readme_path.write_text(content)
        print(f"Written ({mode}): {readme_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
