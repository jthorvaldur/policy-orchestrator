#!/usr/bin/env python3
"""Initialize a new repo into the control plane.

Scaffolds standard files, creates GitHub remote, registers in repos.yaml,
and runs first audit.

Usage:
    python scripts/init_repo.py --name=lectures_sloan
    python scripts/init_repo.py --name=lectures_sloan --category=research --visibility=private
    python scripts/init_repo.py --name=lectures_sloan --dry-run
"""

import os
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent
TEMPLATES = ROOT / "templates"
REGISTRIES = ROOT / "registries"
GITHUB_DIR = Path.home() / "GitHub"


def run(cmd, cwd=None, check=False):
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, timeout=30)
    if check and r.returncode != 0:
        print(f"  FAILED: {' '.join(cmd)}")
        print(f"  {r.stderr.strip()}")
    return r


def detect_language(repo_path):
    """Auto-detect primary language from files."""
    p = Path(repo_path)
    if (p / "pyproject.toml").exists() or list(p.glob("*.py")):
        return "python"
    if (p / "package.json").exists():
        return "javascript"
    if (p / "Cargo.toml").exists():
        return "rust"
    if (p / "go.mod").exists():
        return "go"
    return "python"


def detect_package_manager(repo_path, language):
    if language == "python":
        if (Path(repo_path) / "uv.lock").exists():
            return "uv"
        if (Path(repo_path) / "poetry.lock").exists():
            return "poetry"
        return "uv"
    if language == "javascript":
        return "npm"
    return ""


def detect_description(repo_path, name):
    """Try to read description from README or pyproject.toml."""
    p = Path(repo_path)
    # pyproject.toml
    pyproject = p / "pyproject.toml"
    if pyproject.exists():
        content = pyproject.read_text()
        for line in content.split("\n"):
            if line.strip().startswith("description"):
                desc = line.split("=", 1)[1].strip().strip('"').strip("'")
                if desc:
                    return desc
    # README first line
    readme = p / "README.md"
    if readme.exists():
        lines = readme.read_text().strip().split("\n")
        for line in lines:
            line = line.strip().lstrip("#").strip()
            if line and len(line) > 5:
                return line
    return f"{name} project"


def scaffold_file(repo_path, template_name, target_name, replacements, dry_run=False):
    """Copy a template file with variable substitution."""
    target = Path(repo_path) / target_name
    if target.exists():
        print(f"  SKIP  {target_name} (already exists)")
        return False

    template = TEMPLATES / template_name
    if not template.exists():
        print(f"  MISS  {target_name} (template not found: {template_name})")
        return False

    content = template.read_text()
    for key, value in replacements.items():
        content = content.replace(f"{{{{{key}}}}}", value)

    if dry_run:
        print(f"  WOULD {target_name}")
        return True

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    print(f"  DONE  {target_name}")
    return True


def register_in_repos_yaml(name, category, language, visibility, dry_run=False):
    """Add repo entry to registries/repos.yaml."""
    repos_file = REGISTRIES / "repos.yaml"
    with open(repos_file) as f:
        data = yaml.safe_load(f)

    repos = data.get("repos", [])
    existing = [r for r in repos if r["name"] == name]
    if existing:
        print(f"  SKIP  repos.yaml (already registered)")
        return

    entry = {
        "name": name,
        "path": f"~/GitHub/{name}",
        "github": f"git@github.com:jthorvaldur/{name}.git",
        "category": category,
        "priority": "active",
        "language": language,
        "visibility": visibility,
        "vector_namespace": None,
        "secret_profile": None,
        "update_policy": "manual-review",
        "status": "active",
    }

    if dry_run:
        print(f"  WOULD repos.yaml (add {name})")
        return

    repos.append(entry)
    data["repos"] = repos
    with open(repos_file, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, width=120)
    print(f"  DONE  repos.yaml (registered as {category}/{visibility})")


def create_github_remote(name, visibility, description, repo_path, dry_run=False):
    """Create GitHub repo and set remote."""
    # Check if remote already exists
    r = run(["git", "remote", "get-url", "origin"], cwd=repo_path)
    if r.returncode == 0 and r.stdout.strip():
        print(f"  SKIP  GitHub remote (already set: {r.stdout.strip()})")
        return

    if dry_run:
        print(f"  WOULD GitHub repo (jthorvaldur/{name}, {visibility})")
        return

    # Check if repo exists on GitHub
    r = run(["gh", "repo", "view", f"jthorvaldur/{name}", "--json", "name"])
    if r.returncode == 0:
        print(f"  EXISTS GitHub repo jthorvaldur/{name}")
    else:
        vis_flag = "--private" if visibility == "private" else "--public"
        r = run([
            "gh", "repo", "create", f"jthorvaldur/{name}",
            vis_flag, f"--description={description}",
        ], check=True)
        if r.returncode == 0:
            print(f"  DONE  GitHub repo created ({visibility})")
        else:
            return

    # Set remote
    run(["git", "remote", "add", "origin", f"git@github.com:jthorvaldur/{name}.git"], cwd=repo_path)
    print(f"  DONE  remote set to git@github.com:jthorvaldur/{name}.git")


def create_env_example(repo_path, dry_run=False):
    """Create a minimal .env.example."""
    target = Path(repo_path) / ".env.example"
    if target.exists():
        print(f"  SKIP  .env.example (already exists)")
        return

    content = f"""# {Path(repo_path).name} — required environment variables
# Copy to .env and fill in values. Never commit .env.

# LLM (optional — for AI-assisted features)
# ANTHROPIC_API_KEY=
# OLLAMA_BASE_URL=http://localhost:11434
"""

    if dry_run:
        print(f"  WOULD .env.example")
        return

    target.write_text(content)
    print(f"  DONE  .env.example")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Initialize a repo into the control plane")
    parser.add_argument("--name", required=True, help="Repo directory name in ~/GitHub/")
    parser.add_argument("--category", default=None, help="Category (legal, ai-agents, quant-finance, infrastructure, creative-math, web-portfolio, research)")
    parser.add_argument("--visibility", default="private", choices=["public", "private"])
    parser.add_argument("--no-github", action="store_true", help="Skip GitHub repo creation")
    parser.add_argument("--no-push", action="store_true", help="Skip initial push")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done")
    args = parser.parse_args()

    name = args.name
    repo_path = GITHUB_DIR / name

    if not repo_path.exists():
        print(f"  ERROR: {repo_path} not found. Clone or create it first.")
        sys.exit(1)

    # Auto-detect
    language = detect_language(repo_path)
    pkg_mgr = detect_package_manager(repo_path, language)
    description = detect_description(repo_path, name)
    category = args.category or ("research" if "lecture" in name or "course" in name else "infrastructure")

    print(f"\n  Initializing {name}")
    print(f"  {'─'*50}")
    print(f"  path:       {repo_path}")
    print(f"  language:   {language}")
    print(f"  pkg_mgr:    {pkg_mgr}")
    print(f"  category:   {category}")
    print(f"  visibility: {args.visibility}")
    print(f"  desc:       {description}")
    print(f"  {'─'*50}\n")

    replacements = {
        "PROJECT_NAME": name,
        "PROJECT_DESCRIPTION": description,
        "PRIMARY_LANGUAGE": language,
        "PACKAGE_MANAGER": pkg_mgr,
        "REPO_NAME": name,
        "CATEGORY": category,
        "VISIBILITY": args.visibility,
    }

    # Core deps by category — the common stack across the ecosystem
    CORE_DEPS = {
        "_base": ["httpx", "pyyaml", "click", "tqdm"],
        "legal": ["anthropic", "qdrant-client", "jinja2", "pymupdf", "beautifulsoup4", "markdownify", "python-frontmatter"],
        "ai-agents": ["anthropic", "qdrant-client", "sentence-transformers"],
        "quant-finance": ["pandas", "numpy", "matplotlib", "polars"],
        "infrastructure": ["qdrant-client", "anthropic"],
        "research": ["pandas", "numpy", "matplotlib"],
        "creative-math": ["numpy", "matplotlib"],
        "web-portfolio": [],
        "product": ["anthropic", "qdrant-client", "sentence-transformers", "jinja2"],
    }

    # 0. Ensure uv project + venv + core deps
    print("  Python setup:")
    if language == "python":
        pyproject = repo_path / "pyproject.toml"
        if not pyproject.exists():
            if not args.dry_run:
                run(["uv", "init"], cwd=repo_path, check=True)
                print(f"  DONE  uv init")
            else:
                print(f"  WOULD uv init")
        else:
            print(f"  SKIP  pyproject.toml (already exists)")

        # Add core deps for this category
        deps_to_add = CORE_DEPS.get("_base", []) + CORE_DEPS.get(category, [])
        # Check which are already in pyproject.toml
        pyproject = repo_path / "pyproject.toml"
        existing_deps = ""
        if pyproject.exists():
            existing_deps = pyproject.read_text().lower()
        new_deps = [d for d in deps_to_add if d.lower() not in existing_deps]

        if new_deps and not args.dry_run:
            run(["uv", "add"] + new_deps, cwd=repo_path, check=True)
            print(f"  DONE  uv add {', '.join(new_deps)}")
        elif new_deps:
            print(f"  WOULD uv add {', '.join(new_deps)}")
        else:
            print(f"  SKIP  core deps (already present)")

        if not args.dry_run:
            run(["uv", "sync"], cwd=repo_path, check=True)
            print(f"  DONE  uv sync (.venv ready)")
        else:
            print(f"  WOULD uv sync")
    else:
        print(f"  SKIP  not python ({language})")

    # 1. Scaffold standard files
    print("\n  Scaffolding:")
    scaffold_file(repo_path, "CLAUDE.md", "CLAUDE.md", replacements, args.dry_run)
    scaffold_file(repo_path, "repo.yaml", ".control/repo.yaml", replacements, args.dry_run)
    create_env_example(repo_path, args.dry_run)

    # Ensure .gitignore has basics
    gitignore = repo_path / ".gitignore"
    if gitignore.exists():
        content = gitignore.read_text()
        additions = []
        for pattern in [".env", ".venv", "__pycache__", ".DS_Store", ".provenance/", ".profiling/"]:
            if pattern not in content:
                additions.append(pattern)
        if additions and not args.dry_run:
            with open(gitignore, "a") as f:
                f.write("\n" + "\n".join(additions) + "\n")
            print(f"  DONE  .gitignore (+{len(additions)} patterns)")
        elif additions:
            print(f"  WOULD .gitignore (+{len(additions)} patterns)")
        else:
            print(f"  SKIP  .gitignore (already complete)")
    else:
        if not args.dry_run:
            gitignore.write_text(".env\n.venv\n__pycache__\n.DS_Store\n*.py[oc]\n.provenance/\n.profiling/\n")
            print(f"  DONE  .gitignore (created)")
        else:
            print(f"  WOULD .gitignore (create)")

    # Create scripts/ directory
    scripts_dir = repo_path / "scripts"
    if not scripts_dir.exists() and not args.dry_run:
        scripts_dir.mkdir()
        print(f"  DONE  scripts/ (created)")
    elif not scripts_dir.exists():
        print(f"  WOULD scripts/ (create)")

    # Agent operating process pack: hooks, contracts, routing, evals
    # (templates/processes/README.md). Never overwrites existing files.
    print("\n  Agent process pack:")
    from repo_sync import AGENT_PROCESS_PACK, sync_file
    for template_file in AGENT_PROCESS_PACK:
        if template_file.startswith("claude/"):
            dest = repo_path / ".claude" / template_file.removeprefix("claude/")
        else:
            dest = repo_path / template_file
        if args.dry_run:
            print(f"  {'SKIP ' if dest.exists() else 'WOULD'} {template_file}")
        else:
            status = sync_file(template_file, dest)
            icon = {"synced": "DONE ", "exists": "SKIP ", "template_missing": "MISS "}.get(status, "?    ")
            print(f"  {icon} {template_file}")

    # 2. Register in repos.yaml
    print("\n  Registry:")
    register_in_repos_yaml(name, category, language, args.visibility, args.dry_run)

    # 3. Create GitHub remote
    if not args.no_github:
        print("\n  GitHub:")
        create_github_remote(name, args.visibility, description, repo_path, args.dry_run)

    # 4. Generate/update README
    print("\n  README:")
    readme_script = ROOT / "scripts" / "generate_readme.py"
    if readme_script.exists() and not args.dry_run:
        r = run([sys.executable, str(readme_script), f"--repo={name}", "--init"], cwd=ROOT)
        if r.returncode == 0:
            print(f"  DONE  README.md generated")
        else:
            print(f"  SKIP  README generation ({r.stderr.strip()[:60] if r.stderr else 'error'})")
    elif args.dry_run:
        print(f"  WOULD README.md (devctl readme --repo={name} --init)")

    # 5. Initial commit + push
    if not args.no_push and not args.dry_run:
        print("\n  Git:")
        # Ensure we're on main branch
        branch = run(["git", "branch", "--show-current"], cwd=repo_path).stdout.strip()
        if branch != "main":
            run(["git", "branch", "-M", "main"], cwd=repo_path)
            print(f"  DONE  branch renamed to main (was '{branch or 'unborn'}')")

        run(["git", "add", "-A", "."], cwd=repo_path)
        status = run(["git", "status", "--short"], cwd=repo_path)
        if status.stdout.strip():
            run(["git", "commit", "-m", "init: add control plane contract (CLAUDE.md, .control/)"], cwd=repo_path, check=True)
            print(f"  DONE  committed scaffold files")
            r = run(["git", "push", "-u", "origin", "main"], cwd=repo_path)
            if r.returncode == 0:
                print(f"  DONE  pushed to origin/main")
            else:
                print(f"  SKIP  push ({r.stderr.strip()[:60]})")
        else:
            print(f"  SKIP  nothing to commit")

    # 5. Summary
    print(f"\n  {'─'*50}")
    print(f"  {name} initialized.")
    print(f"\n  Next steps:")
    print(f"    devctl audit --repo={name}    # verify compliance")
    print(f"    devctl status --dirty          # check git state")
    if args.dry_run:
        print(f"\n  {' '*2}(dry run — no changes made)")
    print()


if __name__ == "__main__":
    main()
