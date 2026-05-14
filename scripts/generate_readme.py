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
    """Extract description from pyproject.toml, package.json, or CLAUDE.md."""
    # Prefer pyproject.toml — most likely to have a real description
    pyproject = repo_path / "pyproject.toml"
    if pyproject.exists():
        for line in pyproject.read_text().split("\n"):
            if line.strip().startswith("description"):
                desc = line.split("=", 1)[1].strip().strip('"').strip("'")
                if desc and "your description" not in desc.lower() and len(desc) > 10:
                    return desc

    # package.json
    pkg_json = repo_path / "package.json"
    if pkg_json.exists():
        try:
            pkg = json.loads(pkg_json.read_text())
            desc = pkg.get("description", "")
            if desc and len(desc) > 10:
                return desc
        except Exception:
            pass

    # CLAUDE.md overview section
    claude_md = repo_path / "CLAUDE.md"
    if claude_md.exists():
        content = claude_md.read_text()
        in_overview = False
        desc_lines = []
        for line in content.split("\n"):
            if "## Overview" in line or "## Project Overview" in line:
                in_overview = True
                continue
            if in_overview:
                if line.startswith("##"):
                    break
                stripped = line.strip()
                if stripped and not stripped.startswith(">") and not stripped.startswith("#"):
                    if "your description" not in stripped.lower() and "{{" not in stripped:
                        desc_lines.append(stripped)
        if desc_lines:
            return " ".join(desc_lines)

    # GitHub repo description
    repo_name = repo_path.name
    gh_desc = run(["gh", "repo", "view", f"jthorvaldur/{repo_name}", "--json", "description", "--jq", ".description"])
    if gh_desc and len(gh_desc) > 10:
        return gh_desc

    return ""


def _get_py_docstring(path):
    """Extract the module docstring from a Python file (first triple-quoted string)."""
    try:
        content = path.read_text()
        # Match triple-quoted docstring at top of file (after optional from __future__)
        m = re.search(r'^(?:from __future__.*?\n)?(?:#[^\n]*\n)*\s*"""(.*?)"""', content, re.DOTALL)
        if m:
            # Return first paragraph only
            doc = m.group(1).strip()
            first_para = doc.split("\n\n")[0].replace("\n", " ").strip()
            return first_para[:200]
    except Exception:
        pass
    return ""


def _has_argparse(path):
    """Check if a Python file uses argparse (likely a CLI script)."""
    try:
        content = path.read_text()
        return "argparse" in content or "click" in content or "typer" in content
    except Exception:
        return False


def detect_cli(repo_path):
    """Try to detect CLI tools and get their --help output."""
    cli_help = {}

    # Check for named executables first
    for candidate in ["gpu", "devctl"]:
        path = repo_path / candidate
        if path.exists() and (path.stat().st_mode & 0o111):
            help_text = run([str(path), "--help"], cwd=str(repo_path), timeout=5)
            if help_text and len(help_text) > 20:
                cli_help[candidate] = help_text

    # Discover all top-level Python scripts with argparse/click/typer
    skip_py = {"setup.py", "conftest.py", "__init__.py"}
    for py in sorted(repo_path.glob("*.py")):
        if py.name in skip_py or py.name in cli_help:
            continue
        if _has_argparse(py):
            help_text = run(["python3", str(py), "--help"], cwd=str(repo_path), timeout=8)
            if help_text and len(help_text) > 20:
                cli_help[py.name] = help_text
            elif not help_text:
                # Fallback: use docstring as description
                doc = _get_py_docstring(py)
                if doc:
                    cli_help[py.name] = doc

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


def get_dependencies(repo_path):
    """Extract key dependencies from pyproject.toml or package.json."""
    deps = []
    pyproject = repo_path / "pyproject.toml"
    if pyproject.exists():
        content = pyproject.read_text()
        in_deps = False
        for line in content.split("\n"):
            if line.strip().startswith("dependencies") and "=" in line:
                in_deps = True
                continue
            if line.strip() == "]":
                in_deps = False
            if in_deps and line.strip().startswith('"'):
                dep = line.strip().strip('",').split(">=")[0].split(">")[0].split("<")[0].split("[")[0].strip()
                if dep and not dep.startswith("#"):
                    deps.append(dep)
    return deps[:15]


def get_notebooks(repo_path):
    """Find Jupyter notebooks, deduplicated by filename, organized by directory."""
    notebooks = {}
    seen_names = set()
    for nb in sorted(repo_path.rglob("*.ipynb")):
        if ".venv" in str(nb) or "node_modules" in str(nb) or ".ipynb_checkpoints" in str(nb):
            continue
        if nb.stem in seen_names:
            continue
        seen_names.add(nb.stem)
        parent = nb.parent.name
        notebooks.setdefault(parent, []).append(nb.stem)
    return notebooks


def generate_init(repo_name, repo_path, repo_config):
    """Generate a full README from scratch for repos without one."""
    desc = get_description(repo_path) or f"{repo_name} project."
    cli = detect_cli(repo_path)
    tree = get_tree_annotated(repo_path)
    category = repo_config.get("category", "")
    language = repo_config.get("language", "python")
    commit_count = run(["git", "rev-list", "--count", "HEAD"], cwd=str(repo_path)) or "?"
    deps = get_dependencies(repo_path)
    notebooks = get_notebooks(repo_path)

    sections = [f"# {repo_name}\n", f"{desc}\n"]

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
            # Check for optional dep groups
            pyproject = repo_path / "pyproject.toml"
            if pyproject.exists() and "[project.optional-dependencies]" in pyproject.read_text():
                content = pyproject.read_text()
                groups = []
                for line in content.split("\n"):
                    if line.strip().endswith("= [") and not line.strip().startswith("[") and not line.strip().startswith("dependencies"):
                        group = line.strip().split("=")[0].strip()
                        if group and group != "dependencies":
                            groups.append(group)
                if groups:
                    sections.append(f"# Optional: uv sync --extra {groups[0]}")
                    if "all" in groups:
                        sections.append(f"# Full stack: uv sync --all-extras")
        if has_npm:
            sections.append("npm install")
        if has_cargo:
            sections.append("cargo build --release")
        if has_go:
            sections.append("go build ./...")
        sections.append("```\n")

    # CLI
    if cli:
        sections.append("## Commands\n")
        for cmd_name, help_text in cli.items():
            sections.append(f"### `{cmd_name}`\n")
            sections.append("```")
            for line in help_text.split("\n")[:20]:
                sections.append(line)
            if len(help_text.split("\n")) > 20:
                sections.append("...")
            sections.append("```\n")

    # Notebooks
    if notebooks:
        sections.append("## Notebooks\n")
        for folder, nbs in sorted(notebooks.items()):
            sections.append(f"**{folder}/**")
            for nb in nbs[:10]:
                title = nb.replace("_", " ").replace("-", " ")
                sections.append(f"- `{nb}.ipynb` — {title}")
            if len(nbs) > 10:
                sections.append(f"- ... +{len(nbs) - 10} more")
            sections.append("")

    # Dependencies
    if deps:
        sections.append("## Key Dependencies\n")
        sections.append(", ".join(f"`{d}`" for d in deps))
        sections.append("")

    # Structure
    if tree:
        sections.append("## Structure\n")
        sections.append("```")
        for line in tree[:30]:
            sections.append(line)
        if len(tree) > 30:
            sections.append(f"... +{len(tree) - 30} more")
        sections.append("```\n")

    # Footer
    sections.append("---\n")
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
