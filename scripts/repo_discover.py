#!/usr/bin/env python3
"""Discover and classify all git repos on the filesystem."""

import json
import re
import subprocess
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SCAN_ROOTS = [
    ("~/GitHub", 2),
    ("~/projects", 4),
    ("~/ruv_repos", 3),
    ("~/rprojects", 2),
    ("~/.vim/plugged", 1),
    ("~", 1),  # top-level only
]

SKIP_DIRS = {
    "node_modules", ".venv", "venv", "__pycache__", "target",
    ".tox", ".nox", "dist", "build", ".hg", ".svn",
    "Library", "Applications", "Music", "Movies", "Pictures",
    "Downloads", ".Trash", ".cache", ".local", ".cargo",
    ".rustup", ".npm", ".bun",
}

# Directories scanned by their own root entry — don't recurse into them from ~
DEDICATED_ROOTS = {"GitHub", "projects", "ruv_repos", "rprojects", ".vim"}

USER_ORGS = {"jthorvaldur", "EislerSysJT"}
PERSONAL_ORG = "jthorvaldur"
WORK_ORG = "EislerSysJT"

BACKUP_PATTERNS = re.compile(r"(backup|_old|old_|_bak|_archive)", re.IGNORECASE)
DEPENDENCY_PATHS = {".vim/plugged", ".codex", ".unsloth", ".nvm", ".oh-my-zsh"}
LEGAL_NAMES = {"legal", "legal_good", "div_legal", "legal-tax-ops", "divorce"}

STALE_MONTHS = 12
GIT_TIMEOUT = 5

# ---------------------------------------------------------------------------
# Filesystem discovery
# ---------------------------------------------------------------------------


def discover_repos(roots: list[tuple[str, int]]) -> list[Path]:
    """Walk scan roots and find directories containing .git/."""
    found = []
    seen = set()

    for root_str, max_depth in roots:
        root = Path(root_str).expanduser().resolve()
        if not root.exists():
            continue

        _walk(root, root, max_depth, found, seen, is_home_root=(root_str == "~"))

    return sorted(set(found))


def _walk(base: Path, current: Path, remaining_depth: int,
          found: list[Path], seen: set[str], is_home_root: bool = False):
    """Recursive walker that respects depth limits and skip lists."""
    if remaining_depth < 0:
        return

    resolved = str(current.resolve())
    if resolved in seen:
        return
    seen.add(resolved)

    try:
        entries = list(current.iterdir())
    except (PermissionError, OSError):
        return

    has_git = any(e.name == ".git" and e.is_dir() for e in entries)
    if has_git:
        found.append(current)
        return  # don't recurse into repos

    for entry in entries:
        if not entry.is_dir():
            continue

        name = entry.name

        # Skip hidden dirs, except .vim when scanning home
        if name.startswith("."):
            if name == ".vim" and is_home_root:
                pass  # allow .vim at home level
            else:
                continue

        if name in SKIP_DIRS:
            continue

        # When scanning ~, skip directories that have their own dedicated root
        if is_home_root and name in DEDICATED_ROOTS:
            continue

        _walk(base, entry, remaining_depth - 1, found, seen)


# ---------------------------------------------------------------------------
# Git metadata extraction (all read-only)
# ---------------------------------------------------------------------------


def _git(repo_path: Path, *args) -> tuple[int, str]:
    """Run a git command and return (returncode, stdout)."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path)] + list(args),
            capture_output=True, text=True, timeout=GIT_TIMEOUT,
        )
        return result.returncode, result.stdout.strip()
    except (subprocess.TimeoutExpired, Exception):
        return -1, ""


def extract_git_metadata(repo_path: Path) -> dict:
    """Extract read-only git metadata from a repo."""
    meta = {
        "path": str(repo_path),
        "name": repo_path.name,
        "has_remote": False,
        "remote_url": None,
        "remote_org": None,
        "branch": None,
        "has_commits": False,
        "commit_count": 0,
        "last_commit_date": None,
        "last_commit_message": None,
        "initial_commit_hash": None,
        "ahead": None,
        "behind": None,
        "clean": None,
    }

    # Remote
    rc, out = _git(repo_path, "remote", "get-url", "origin")
    if rc == 0 and out:
        meta["has_remote"] = True
        meta["remote_url"] = out
        meta["remote_org"] = _parse_org(out)

    # Branch
    rc, out = _git(repo_path, "rev-parse", "--abbrev-ref", "HEAD")
    if rc == 0:
        meta["branch"] = out

    # Commit count
    rc, out = _git(repo_path, "rev-list", "--count", "HEAD")
    if rc == 0 and out.isdigit():
        meta["has_commits"] = int(out) > 0
        meta["commit_count"] = int(out)

    # Last commit
    rc, out = _git(repo_path, "log", "-1", "--format=%aI|%s")
    if rc == 0 and "|" in out:
        parts = out.split("|", 1)
        meta["last_commit_date"] = parts[0]
        meta["last_commit_message"] = parts[1][:80]

    # Initial commit hash (for duplicate detection)
    rc, out = _git(repo_path, "rev-list", "--max-parents=0", "HEAD")
    if rc == 0 and out:
        meta["initial_commit_hash"] = out.split("\n")[0]

    # Ahead/behind
    if meta["has_remote"]:
        rc, out = _git(repo_path, "rev-list", "--left-right", "--count", "@{u}...HEAD")
        if rc == 0 and "\t" in out:
            parts = out.split("\t")
            meta["behind"] = int(parts[0])
            meta["ahead"] = int(parts[1])

    # Clean/dirty
    rc, out = _git(repo_path, "status", "--porcelain")
    if rc == 0:
        meta["clean"] = len(out) == 0

    return meta


def _parse_org(url: str) -> str | None:
    """Extract organization/user from a GitHub URL."""
    # SSH: git@github.com:org/repo.git
    m = re.match(r"git@github\.com:([^/]+)/", url)
    if m:
        return m.group(1)
    # HTTPS: https://github.com/org/repo
    m = re.match(r"https?://github\.com/([^/]+)/", url)
    if m:
        return m.group(1)
    return None


def _normalize_remote(url: str) -> str:
    """Normalize a remote URL for duplicate comparison."""
    url = url.strip().lower()
    url = re.sub(r"\.git$", "", url)
    url = re.sub(r"^git@github\.com:", "https://github.com/", url)
    url = re.sub(r"/$", "", url)
    return url


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def _location_group(path: Path) -> str:
    """Determine which location group a repo path belongs to."""
    home = Path.home()
    rel = str(path.relative_to(home)) if path.is_relative_to(home) else str(path)

    if rel.startswith("GitHub/"):
        return "github"
    if rel.startswith("projects/"):
        return "projects"
    if rel.startswith("ruv_repos/"):
        return "ruv_repos"
    if rel.startswith("rprojects/"):
        return "rprojects"
    if rel.startswith(".vim/plugged/"):
        return "vim-plugins"
    for dep_path in DEPENDENCY_PATHS:
        if rel.startswith(dep_path):
            return "dependency"
    return "home-root"


def classify_lifecycle(repo: dict, registry_names: set[str]) -> str:
    """Assign a lifecycle category to a repo."""
    path = Path(repo["path"])
    loc = _location_group(path)

    # Dependencies first
    if loc in ("vim-plugins", "dependency"):
        return "dependency"

    # Reference repos (not owned)
    if loc == "ruv_repos":
        return "reference"
    if repo["remote_org"] and repo["remote_org"] not in USER_ORGS:
        return "reference"

    # Empty repos
    if not repo["has_commits"]:
        return "empty"

    # Backups
    rel_path = str(path.relative_to(Path.home())) if path.is_relative_to(Path.home()) else str(path)
    if BACKUP_PATTERNS.search(rel_path):
        return "backup"
    if "/old_" in rel_path or "/old/" in rel_path:
        return "backup"

    # Work org
    if repo["remote_org"] == WORK_ORG:
        return "work-org"

    # Orphan (has commits, no remote)
    if not repo["has_remote"]:
        return "orphan"

    # Stale (remote + personal org + old)
    if repo["remote_org"] == PERSONAL_ORG and repo["last_commit_date"]:
        try:
            last = datetime.fromisoformat(repo["last_commit_date"])
            cutoff = datetime.now(timezone.utc) - timedelta(days=STALE_MONTHS * 30)
            if last < cutoff:
                return "stale"
        except (ValueError, TypeError):
            pass

    # Active
    return "active"


def detect_duplicates(repos: list[dict]) -> dict[str, list[str]]:
    """Find repos that share the same remote URL or initial commit."""
    by_remote = defaultdict(list)
    by_initial = defaultdict(list)

    for repo in repos:
        if repo["remote_url"]:
            key = _normalize_remote(repo["remote_url"])
            by_remote[key].append(repo["path"])
        elif repo["initial_commit_hash"]:
            by_initial[repo["initial_commit_hash"]].append(repo["path"])

    groups = {}
    for key, paths in by_remote.items():
        if len(paths) > 1:
            groups[key] = paths
    for key, paths in by_initial.items():
        if len(paths) > 1:
            groups[f"commit:{key[:12]}"] = paths

    return groups


def assess_risk(repo: dict) -> tuple[str, list[str]]:
    """Assess data loss risk. Returns (level, [reasons])."""
    reasons = []

    if not repo["has_commits"]:
        return "none", []

    if not repo["has_remote"]:
        name_lower = repo["name"].lower()
        is_legal = any(ln in name_lower for ln in LEGAL_NAMES)
        if is_legal or repo["commit_count"] >= 20:
            reasons.append(f"no remote with {repo['commit_count']} commits")
            if is_legal:
                reasons.append("legal data with no backup strategy")
            return "critical", reasons
        elif repo["commit_count"] >= 5:
            reasons.append(f"no remote with {repo['commit_count']} commits")
            return "high", reasons
        else:
            reasons.append(f"no remote ({repo['commit_count']} commits)")
            return "medium", reasons

    if repo.get("behind") and repo["behind"] > 0:
        reasons.append(f"behind remote by {repo['behind']} commits")

    if repo.get("clean") is False:
        reasons.append("dirty working tree")

    if reasons:
        return "medium", reasons

    return "low", []


# ---------------------------------------------------------------------------
# Cross-reference with repos.yaml
# ---------------------------------------------------------------------------


def load_registry() -> dict[str, dict]:
    """Load repos.yaml and return dict keyed by repo name."""
    registry_path = Path(__file__).parent.parent / "registries" / "repos.yaml"
    if not registry_path.exists():
        return {}
    with open(registry_path) as f:
        data = yaml.safe_load(f)
    return {r["name"]: r for r in data.get("repos", [])}


def cross_reference(repos: list[dict], registry: dict[str, dict]) -> dict:
    """Compare discovered repos against registry."""
    report = {
        "path_corrections": [],
        "not_registered": [],
        "registered_not_found": [],
    }

    found_names = set()
    for repo in repos:
        if repo["lifecycle"] in ("reference", "dependency", "empty"):
            continue

        name = repo["name"]
        found_names.add(name)

        if name in registry:
            reg = registry[name]
            reg_path = reg.get("path")
            if reg_path is None and repo["path"]:
                report["path_corrections"].append({
                    "name": name,
                    "registry_path": "null",
                    "actual_path": repo["path"],
                })
        else:
            report["not_registered"].append({
                "name": name,
                "path": repo["path"],
                "lifecycle": repo["lifecycle"],
                "risk": repo["risk"]["level"],
            })

    for name, reg in registry.items():
        if name not in found_names:
            report["registered_not_found"].append({
                "name": name,
                "registry_path": reg.get("path"),
            })

    return report


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def print_table(repos: list[dict], duplicates: dict, xref: dict,
                lifecycle_filter: str | None = None,
                risk_filter: str | None = None,
                duplicates_only: bool = False,
                unregistered_only: bool = False):
    """Print a human-readable table."""

    risk_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "none": 4}

    filtered = repos
    if lifecycle_filter:
        filtered = [r for r in filtered if r["lifecycle"] == lifecycle_filter]
    if risk_filter:
        max_level = risk_order.get(risk_filter, 4)
        filtered = [r for r in filtered if risk_order.get(r["risk"]["level"], 4) <= max_level]
    if unregistered_only:
        filtered = [r for r in filtered if not r.get("registered")]

    # Summary
    counts = defaultdict(int)
    risk_counts = defaultdict(int)
    for r in repos:
        counts[r["lifecycle"]] += 1
        if r["risk"]["level"] in ("critical", "high"):
            risk_counts[r["risk"]["level"]] += 1

    print(f"\nRepository Inventory — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'=' * 70}")
    print(f"Total: {len(repos)} repos across {len(set(r['location_group'] for r in repos))} locations\n")

    print("Lifecycle Summary:")
    for cat in ["active", "work-org", "stale", "reference", "duplicate",
                 "backup", "orphan", "empty", "dependency"]:
        if counts[cat]:
            print(f"  {cat:<14} {counts[cat]:>4}")

    if risk_counts:
        print(f"\nData Loss Risk:")
        for level in ["critical", "high"]:
            if risk_counts[level]:
                print(f"  {level:<10} {risk_counts[level]}")
                for r in repos:
                    if r["risk"]["level"] == level:
                        reasons = "; ".join(r["risk"]["reasons"])
                        print(f"    {r['path']}  ({reasons})")

    # Duplicates
    if duplicates:
        print(f"\nDuplicate Groups ({len(duplicates)}):")
        for key, paths in duplicates.items():
            label = key.split("/")[-1] if "/" in key else key
            print(f"  {label}:")
            for p in paths:
                marker = ""
                for r in repos:
                    if r["path"] == p:
                        if r.get("registered"):
                            marker = " (registered)"
                        if r["location_group"] == "github":
                            marker += " (canonical)"
                        break
                print(f"    {p}{marker}")

    if duplicates_only:
        return

    # Cross-reference
    if xref.get("path_corrections"):
        print(f"\nRegistry Path Corrections Needed:")
        for c in xref["path_corrections"]:
            print(f"  {c['name']}: path: null -> path: {c['actual_path']}")

    # Table
    print(f"\n{'Repo':<30} {'Location':<14} {'Lifecycle':<12} {'Remote':<6} {'A/B':<8} {'Risk':<10} {'Reg'}")
    print("-" * 100)

    for r in filtered:
        remote = "yes" if r["has_remote"] else "no"
        ab = ""
        if r["ahead"] is not None and r["behind"] is not None:
            ab = f"+{r['ahead']}/-{r['behind']}"
        reg = "yes" if r.get("registered") else ""
        risk = r["risk"]["level"] if r["risk"]["level"] != "none" else ""

        print(f"{r['name']:<30} {r['location_group']:<14} {r['lifecycle']:<12} {remote:<6} {ab:<8} {risk:<10} {reg}")

    print(f"\nShowing {len(filtered)} of {len(repos)} repos")


def generate_yaml(repos: list[dict], duplicates: dict, xref: dict,
                  reference_only: bool = False) -> str:
    """Generate YAML output for saving."""
    if reference_only:
        entries = [r for r in repos if r["lifecycle"] == "reference"]
    else:
        entries = [r for r in repos if r["lifecycle"] != "reference"]

    # Clean up for YAML serialization
    clean = []
    for r in entries:
        clean.append({
            "name": r["name"],
            "path": r["path"],
            "location_group": r["location_group"],
            "remote_url": r["remote_url"],
            "remote_org": r["remote_org"],
            "lifecycle": r["lifecycle"],
            "registered": r.get("registered", False),
            "git": {
                "has_commits": r["has_commits"],
                "commit_count": r["commit_count"],
                "branch": r["branch"],
                "has_remote": r["has_remote"],
                "ahead": r["ahead"],
                "behind": r["behind"],
                "clean": r["clean"],
                "last_commit_date": r["last_commit_date"],
                "last_commit_message": r["last_commit_message"],
            },
            "risk": r["risk"],
        })

    output = {
        "generated": datetime.now().isoformat(),
        "scanner_version": "1.0.0",
        "total": len(clean),
        "repos": clean,
    }

    if not reference_only and duplicates:
        output["duplicate_groups"] = {k: v for k, v in duplicates.items()}

    if not reference_only and xref:
        output["cross_reference"] = xref

    return yaml.dump(output, default_flow_style=False, sort_keys=False, width=120)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run_discovery(lifecycle_filter=None, risk_filter=None,
                  duplicates_only=False, unregistered_only=False,
                  save=False, output_format="table"):
    """Run the full discovery pipeline."""

    print("Scanning filesystem for git repos...", file=sys.stderr)
    repo_paths = discover_repos(SCAN_ROOTS)
    print(f"Found {len(repo_paths)} repos. Extracting metadata...", file=sys.stderr)

    # Extract metadata in parallel
    repos = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(extract_git_metadata, p): p for p in repo_paths}
        for future in as_completed(futures):
            try:
                repos.append(future.result())
            except Exception as e:
                print(f"  Error scanning {futures[future]}: {e}", file=sys.stderr)

    # Load registry and classify
    registry = load_registry()
    registry_names = set(registry.keys())

    for repo in repos:
        repo["location_group"] = _location_group(Path(repo["path"]))
        repo["lifecycle"] = classify_lifecycle(repo, registry_names)
        level, reasons = assess_risk(repo)
        repo["risk"] = {"level": level, "reasons": reasons}
        repo["registered"] = repo["name"] in registry_names

    # Detect duplicates
    dup_groups = detect_duplicates(repos)

    # Mark duplicate lifecycle
    dup_paths = set()
    for paths in dup_groups.values():
        dup_paths.update(paths)
    for repo in repos:
        if repo["path"] in dup_paths and repo["lifecycle"] == "active":
            # Only mark as duplicate if it's not the canonical copy
            loc = repo["location_group"]
            if loc != "github" and not repo["registered"]:
                repo["lifecycle"] = "duplicate"

    # Cross-reference
    xref = cross_reference(repos, registry)

    # Sort: risk desc, then lifecycle, then name
    risk_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "none": 4}
    lifecycle_order = {"orphan": 0, "active": 1, "work-org": 2, "stale": 3,
                       "duplicate": 4, "backup": 5, "reference": 6, "empty": 7, "dependency": 8}
    repos.sort(key=lambda r: (
        risk_order.get(r["risk"]["level"], 4),
        lifecycle_order.get(r["lifecycle"], 9),
        r["name"],
    ))

    # Output
    if output_format == "table":
        print_table(repos, dup_groups, xref,
                    lifecycle_filter=lifecycle_filter,
                    risk_filter=risk_filter,
                    duplicates_only=duplicates_only,
                    unregistered_only=unregistered_only)
    elif output_format == "json":
        print(json.dumps([r for r in repos], indent=2, default=str))
    elif output_format == "yaml":
        print(generate_yaml(repos, dup_groups, xref))

    # Save
    if save:
        base = Path(__file__).parent.parent / "registries"

        inv_path = base / "inventory.yaml"
        inv_content = generate_yaml(repos, dup_groups, xref, reference_only=False)
        inv_path.write_text(inv_content)
        print(f"\nSaved inventory to {inv_path}", file=sys.stderr)

        ref_path = base / "reference-repos.yaml"
        ref_content = generate_yaml(repos, dup_groups, xref, reference_only=True)
        ref_path.write_text(ref_content)
        print(f"Saved reference repos to {ref_path}", file=sys.stderr)

    return repos, dup_groups, xref


def main():
    """CLI entry point."""
    import argparse
    parser = argparse.ArgumentParser(description="Discover and classify all git repos")
    parser.add_argument("--lifecycle", default=None, help="Filter by lifecycle category")
    parser.add_argument("--risk", default=None, help="Filter by minimum risk level")
    parser.add_argument("--duplicates-only", action="store_true", help="Show only duplicate groups")
    parser.add_argument("--unregistered-only", action="store_true", help="Show only unregistered repos")
    parser.add_argument("--save", action="store_true", help="Write to registries/")
    parser.add_argument("--format", choices=["table", "json", "yaml"], default="table")

    args = parser.parse_args()
    run_discovery(
        lifecycle_filter=args.lifecycle,
        risk_filter=args.risk,
        duplicates_only=args.duplicates_only,
        unregistered_only=args.unregistered_only,
        save=args.save,
        output_format=args.format,
    )


if __name__ == "__main__":
    main()
