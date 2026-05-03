#!/usr/bin/env python3
"""Generate or regenerate README.md for a managed repo.

Reads CLAUDE.md, pyproject.toml/package.json, directory structure, and
git history to produce a comprehensive README. Won't overwrite human prose
sections marked with <!-- HUMAN --> ... <!-- /HUMAN -->.
"""

import json
import subprocess
import sys
from pathlib import Path

import yaml

REGISTRIES = Path(__file__).parent.parent / "registries"


def load_repos():
    with open(REGISTRIES / "repos.yaml") as f:
        return {r["name"]: r for r in yaml.safe_load(f).get("repos", [])}


def run(cmd, cwd=None):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10, cwd=cwd)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def detect_stack(repo_path):
    """Detect language, package manager, and key files."""
    stack = {"language": [], "pm": None, "entry": None, "test_cmd": None, "build_cmd": None}

    if (repo_path / "pyproject.toml").exists():
        stack["language"].append("Python")
        stack["pm"] = "uv"
        stack["build_cmd"] = "uv sync"
        stack["test_cmd"] = "uv run pytest"
        try:
            content = (repo_path / "pyproject.toml").read_text()
            if "[project.scripts]" in content:
                for line in content.split("\n"):
                    if "=" in line and "[" not in line and "requires" not in line:
                        line = line.strip()
                        if line and not line.startswith("#") and not line.startswith("["):
                            if "=" in line and '"' in line:
                                parts = line.split("=", 1)
                                if "." in parts[1]:
                                    stack["entry"] = parts[0].strip().strip('"')
                                    break
        except Exception:
            pass

    if (repo_path / "package.json").exists():
        stack["language"].append("JavaScript/TypeScript")
        stack["pm"] = "npm"
        stack["build_cmd"] = "npm install"
        try:
            pkg = json.loads((repo_path / "package.json").read_text())
            scripts = pkg.get("scripts", {})
            if "test" in scripts:
                stack["test_cmd"] = "npm test"
            if "dev" in scripts:
                stack["entry"] = "npm run dev"
            elif "start" in scripts:
                stack["entry"] = "npm start"
        except Exception:
            pass

    if (repo_path / "Cargo.toml").exists():
        stack["language"].append("Rust")
        stack["pm"] = "cargo"
        stack["build_cmd"] = "cargo build --release"
        stack["test_cmd"] = "cargo test"

    if (repo_path / "go.mod").exists():
        stack["language"].append("Go")
        stack["pm"] = "go"
        stack["build_cmd"] = "go build ./..."
        stack["test_cmd"] = "go test ./..."

    if (repo_path / "Dockerfile").exists():
        stack["language"].append("Docker")

    return stack


def get_tree(repo_path, max_depth=2):
    """Get directory tree, excluding common noise."""
    skip = {".git", ".venv", "venv", "node_modules", "__pycache__", "target",
            ".ruff_cache", ".mypy_cache", ".pytest_cache", "dist", "build",
            ".DS_Store", ".claude-flow", ".swarm", ".dual-graph", ".claude",
            ".cursor", ".egg-info", "wheels"}

    lines = []

    def _walk(path, prefix, depth):
        if depth > max_depth:
            return
        try:
            entries = sorted(path.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
        except PermissionError:
            return
        dirs = [e for e in entries if e.is_dir() and e.name not in skip and not e.name.startswith(".")]
        files = [e for e in entries if e.is_file() and e.name not in skip
                 and not e.name.startswith(".") and e.name != "uv.lock"
                 and not e.name.endswith(".pyc")]

        # Show key files at this level
        for f in files[:10]:
            lines.append(f"{prefix}{f.name}")
        if len(files) > 10:
            lines.append(f"{prefix}... +{len(files) - 10} more")

        for d in dirs[:8]:
            lines.append(f"{prefix}{d.name}/")
            _walk(d, prefix + "  ", depth + 1)
        if len(dirs) > 8:
            lines.append(f"{prefix}... +{len(dirs) - 8} more dirs")

    _walk(repo_path, "", 0)
    return lines


def generate_readme(repo_name, repo_path, repo_config):
    """Generate README content."""
    stack = detect_stack(repo_path)

    # Read CLAUDE.md for description
    description = ""
    claude_md = repo_path / "CLAUDE.md"
    if claude_md.exists():
        content = claude_md.read_text()
        # Extract overview section
        for line in content.split("\n"):
            if line.startswith("## Overview"):
                continue
            if line.startswith("##"):
                break
            if line.strip() and not line.startswith(">") and not line.startswith("#"):
                description += line.strip() + " "
        description = description.strip()

    if not description:
        # Fallback to pyproject.toml description
        pyproject = repo_path / "pyproject.toml"
        if pyproject.exists():
            for line in pyproject.read_text().split("\n"):
                if line.strip().startswith("description"):
                    description = line.split("=", 1)[1].strip().strip('"')
                    break

    if not description:
        description = f"{repo_name} project."

    # Git stats
    commit_count = run(["git", "rev-list", "--count", "HEAD"], cwd=str(repo_path)) or "?"
    last_commit = run(["git", "log", "-1", "--format=%ar"], cwd=str(repo_path)) or "?"

    # Category
    category = repo_config.get("category", "")

    # Build README
    sections = []

    # Title + description
    sections.append(f"# {repo_name}\n")
    sections.append(f"{description}\n")

    # Stack
    if stack["language"]:
        sections.append("## Stack\n")
        sections.append(f"- **Language**: {', '.join(stack['language'])}")
        if stack["pm"]:
            sections.append(f"- **Package manager**: {stack['pm']}")
        sections.append("")

    # Setup
    if stack["build_cmd"]:
        sections.append("## Setup\n")
        sections.append("```bash")
        sections.append(f"git clone git@github.com:jthorvaldur/{repo_name}.git")
        sections.append(f"cd {repo_name}")
        sections.append(stack["build_cmd"])
        sections.append("```\n")

    # Usage
    if stack["entry"] or stack["test_cmd"]:
        sections.append("## Usage\n")
        sections.append("```bash")
        if stack["entry"]:
            sections.append(stack["entry"])
        if stack["test_cmd"]:
            sections.append(f"# Run tests")
            sections.append(stack["test_cmd"])
        sections.append("```\n")

    # Structure
    tree = get_tree(repo_path, max_depth=2)
    if tree:
        sections.append("## Structure\n")
        sections.append("```")
        for line in tree[:30]:
            sections.append(line)
        if len(tree) > 30:
            sections.append(f"... +{len(tree) - 30} more entries")
        sections.append("```\n")

    # Footer
    sections.append("## Part of\n")
    sections.append(f"Managed by [policy-orchestrator](https://github.com/jthorvaldur/policy-orchestrator).")
    if category:
        sections.append(f"Category: {category}.")
    sections.append(f"{commit_count} commits, last updated {last_commit}.")
    sections.append("")

    return "\n".join(sections)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Generate README.md for a repo")
    parser.add_argument("--repo", required=True, help="Repo name from registry")
    parser.add_argument("--dry-run", action="store_true", help="Print to stdout, don't write")
    parser.add_argument("--force", action="store_true", help="Overwrite even if README has human sections")
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

    # Check for human sections
    readme_path = repo_path / "README.md"
    if readme_path.exists() and not args.force:
        existing = readme_path.read_text()
        if "<!-- HUMAN -->" in existing:
            print("README has <!-- HUMAN --> sections. Use --force to overwrite.", file=sys.stderr)
            sys.exit(1)

    content = generate_readme(args.repo, repo_path, repo_config)

    if args.dry_run:
        print(content)
    else:
        readme_path.write_text(content)
        print(f"Written: {readme_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
