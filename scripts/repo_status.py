#!/usr/bin/env python3
"""Report status of all registered repos."""

import subprocess
import sys
from pathlib import Path

import yaml

C = {
    "reset": "\033[0m", "bold": "\033[1m", "dim": "\033[90m",
    "green": "\033[32m", "yellow": "\033[33m", "red": "\033[31m",
    "cyan": "\033[36m",
}


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
        "dirty_count": 0,
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
        dirty_lines = [l for l in status.stdout.strip().split("\n") if l]
        result["git_clean"] = len(dirty_lines) == 0
        result["dirty_count"] = len(dirty_lines)

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


def _dedup_repos(repos: list[dict]) -> list[dict]:
    """Deduplicate repos by name, keeping the first occurrence."""
    seen = set()
    out = []
    for r in repos:
        if r["name"] not in seen:
            seen.add(r["name"])
            out.append(r)
    return out


def main():
    registry = load_registry()
    repos = _dedup_repos(registry.get("repos", []))

    filter_category = None
    filter_dirty = False
    for arg in sys.argv[1:]:
        if arg.startswith("--category="):
            filter_category = arg.split("=", 1)[1]
        elif arg == "--dirty":
            filter_dirty = True

    if filter_category:
        repos = [r for r in repos if r["category"] == filter_category]

    total = len(repos)
    print(f"\n{C['bold']}  devctl status{C['reset']}  {C['dim']}{total} repos{C['reset']}\n")

    results = []
    for repo in repos:
        info = check_repo(repo)
        results.append(info)

    # Separate into categories
    dirty = [r for r in results if r["git_clean"] is False]
    unpushed = [r for r in results if isinstance(r.get("unpushed"), int) and r["unpushed"] > 0 and r["git_clean"] is not False]
    errored = [r for r in results if r["errors"]]
    clean = [r for r in results if r["git_clean"] is True and not r["errors"] and not (isinstance(r.get("unpushed"), int) and r["unpushed"] > 0)]

    if filter_dirty:
        # Only show dirty repos
        display = dirty
    else:
        # Show issues: errors first, then dirty, then unpushed
        display = errored + dirty + unpushed

    for info in display:
        if info["errors"]:
            dot = f"{C['red']}\u25cf{C['reset']}"
        elif info["git_clean"] is False:
            dot = f"{C['yellow']}\u25cf{C['reset']}"
        else:
            dot = f"{C['green']}\u25cf{C['reset']}"

        branch = info["branch"] or ""
        cat = info["category"]
        branch_str = f" {C['dim']}\u00b7{C['reset']} {branch}" if branch else ""
        print(f"  {dot} {C['bold']}{info['name']}{C['reset']}  {C['dim']}{cat}{branch_str}{C['reset']}")

        for err in info["errors"]:
            print(f"    {C['red']}\u2717{C['reset']} {err}")

        if info["git_clean"] is False:
            n = info["dirty_count"]
            label = "file" if n == 1 else "files"
            print(f"    {C['yellow']}\u2717{C['reset']} dirty ({n} {label})")

        if isinstance(info.get("unpushed"), int) and info["unpushed"] > 0:
            n = info["unpushed"]
            label = "commit" if n == 1 else "commits"
            print(f"    {C['yellow']}!{C['reset']} {n} unpushed {label}")

        print()

    # Summary
    n_clean = len(clean)
    n_dirty = len(dirty)
    n_unpushed = len(unpushed)
    n_errors = len(errored)

    print(f"  {C['dim']}{'\u2500' * 50}{C['reset']}")
    parts = [f"  {C['bold']}{total} repos{C['reset']}"]
    parts.append(f"  {C['green']}\u25cf {n_clean} clean{C['reset']}")
    if n_dirty:
        parts.append(f"  {C['yellow']}\u25cf {n_dirty} dirty{C['reset']}")
    if n_unpushed:
        parts.append(f"  {C['yellow']}\u25cf {n_unpushed} unpushed{C['reset']}")
    if n_errors:
        parts.append(f"  {C['red']}\u25cf {n_errors} errors{C['reset']}")
    print("".join(parts))
    print()


if __name__ == "__main__":
    main()
