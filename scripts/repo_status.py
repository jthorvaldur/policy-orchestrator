#!/usr/bin/env python3
"""Report status of all registered repos."""

import subprocess
import sys
from pathlib import Path

import yaml


def load_registry() -> dict:
    registry_path = Path(__file__).parent.parent / "registries" / "repos.yaml"
    with open(registry_path) as f:
        return yaml.safe_load(f)


def check_repo(repo: dict) -> dict:
    """Check the status of a single repo."""
    result = {
        "name": repo["name"],
        "category": repo["category"],
        "priority": repo["priority"],
        "status": repo["status"],
        "local": False,
        "git_clean": None,
        "branch": None,
        "unpushed": None,
        "errors": [],
    }

    path = repo.get("path")
    if not path:
        result["errors"].append("not cloned locally")
        return result

    repo_path = Path(path).expanduser()
    if not repo_path.exists():
        result["errors"].append(f"path does not exist: {repo_path}")
        return result

    if not (repo_path / ".git").exists():
        result["errors"].append("not a git repository")
        return result

    result["local"] = True

    try:
        # Check git status
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=10,
        )
        result["git_clean"] = len(status.stdout.strip()) == 0

        # Check current branch
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=10,
        )
        result["branch"] = branch.stdout.strip()

        # Check unpushed commits
        unpushed = subprocess.run(
            ["git", "log", "--oneline", "@{u}..HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if unpushed.returncode == 0:
            lines = [l for l in unpushed.stdout.strip().split("\n") if l]
            result["unpushed"] = len(lines)
        else:
            result["unpushed"] = "no upstream"

    except subprocess.TimeoutExpired:
        result["errors"].append("git command timed out")
    except Exception as e:
        result["errors"].append(str(e))

    return result


def main():
    registry = load_registry()
    repos = registry.get("repos", [])

    filter_category = None
    filter_dirty = False
    for arg in sys.argv[1:]:
        if arg.startswith("--category="):
            filter_category = arg.split("=", 1)[1]
        elif arg == "--dirty":
            filter_dirty = True

    print(f"{'Repo':<30} {'Category':<18} {'Branch':<12} {'Clean':<8} {'Unpushed':<10} {'Issues'}")
    print("-" * 110)

    for repo in repos:
        if filter_category and repo["category"] != filter_category:
            continue

        info = check_repo(repo)

        if filter_dirty and info.get("git_clean") is not False:
            continue

        clean = "yes" if info["git_clean"] else ("no" if info["git_clean"] is False else "-")
        branch = info["branch"] or "-"
        unpushed = str(info["unpushed"]) if info["unpushed"] is not None else "-"
        issues = "; ".join(info["errors"]) if info["errors"] else "ok"

        print(f"{info['name']:<30} {info['category']:<18} {branch:<12} {clean:<8} {unpushed:<10} {issues}")


if __name__ == "__main__":
    main()
