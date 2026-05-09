#!/usr/bin/env python3
"""traffic.py — GitHub traffic stats across all registered repos.

Shows clone counts, view counts, popular paths, and referrers.
Uses the GitHub API (requires `gh` CLI authenticated).
"""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import yaml

REGISTRIES_DIR = Path(__file__).parent.parent / "registries"

# ANSI
C = {
    "reset": "\033[0m", "bold": "\033[1m", "dim": "\033[90m",
    "green": "\033[32m", "yellow": "\033[33m", "cyan": "\033[36m",
    "red": "\033[31m", "mag": "\033[35m", "white": "\033[97m",
}


def gh_api(endpoint: str) -> dict | list | None:
    """Call GitHub API via gh CLI."""
    try:
        result = subprocess.run(
            ["gh", "api", endpoint],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
    except Exception:
        pass
    return None


def get_repo_github(repo: dict) -> str | None:
    """Extract owner/name from github URL."""
    gh = repo.get("github", "")
    # git@github.com:owner/name.git or https://github.com/owner/name
    if "github.com" not in gh:
        return None
    gh = gh.replace("git@github.com:", "").replace("https://github.com/", "")
    gh = gh.replace(".git", "").strip("/")
    return gh if "/" in gh else None


def main():
    import argparse

    parser = argparse.ArgumentParser(description="GitHub traffic stats")
    parser.add_argument("--repo", default=None, help="Single repo name")
    parser.add_argument("--sort", default="clones", choices=["clones", "views", "name"],
                        help="Sort by (default: clones)")
    parser.add_argument("--json", dest="as_json", action="store_true", help="JSON output")
    args = parser.parse_args()

    with open(REGISTRIES_DIR / "repos.yaml") as f:
        repos = yaml.safe_load(f).get("repos", [])

    if args.repo:
        repos = [r for r in repos if r["name"] == args.repo]
        if not repos:
            print(f"{C['red']}Repo '{args.repo}' not found in registry.{C['reset']}")
            sys.exit(1)

    # Deduplicate (energy_texas appears twice in repos.yaml)
    seen = set()
    unique_repos = []
    for r in repos:
        if r["name"] not in seen:
            seen.add(r["name"])
            unique_repos.append(r)
    repos = unique_repos

    print(f"\n{C['bold']}  GitHub Traffic{C['reset']}  {C['dim']}(last 14 days){C['reset']}\n")

    results = []
    errors = []

    for r in repos:
        slug = get_repo_github(r)
        if not slug:
            continue

        clones_data = gh_api(f"repos/{slug}/traffic/clones")
        views_data = gh_api(f"repos/{slug}/traffic/views")

        if clones_data is None and views_data is None:
            errors.append(r["name"])
            continue

        clone_count = clones_data.get("count", 0) if clones_data else 0
        clone_uniques = clones_data.get("uniques", 0) if clones_data else 0
        view_count = views_data.get("count", 0) if views_data else 0
        view_uniques = views_data.get("uniques", 0) if views_data else 0

        results.append({
            "name": r["name"],
            "slug": slug,
            "category": r.get("category", ""),
            "visibility": r.get("visibility", ""),
            "clones": clone_count,
            "clone_uniques": clone_uniques,
            "views": view_count,
            "view_uniques": view_uniques,
        })

    if args.as_json:
        print(json.dumps(results, indent=2))
        return

    # Sort
    if args.sort == "clones":
        results.sort(key=lambda x: x["clones"], reverse=True)
    elif args.sort == "views":
        results.sort(key=lambda x: x["views"], reverse=True)
    else:
        results.sort(key=lambda x: x["name"])

    # Table header
    print(f"  {'Repo':<28} {'Vis':<7} {'Clones':>8} {'Unique':>8} {'Views':>8} {'Unique':>8}")
    print(f"  {'─'*28} {'─'*7} {'─'*8} {'─'*8} {'─'*8} {'─'*8}")

    total_clones = 0
    total_clone_uniques = 0
    total_views = 0
    total_view_uniques = 0
    flagged = []

    for r in results:
        total_clones += r["clones"]
        total_clone_uniques += r["clone_uniques"]
        total_views += r["views"]
        total_view_uniques += r["view_uniques"]

        # Color coding
        if r["clones"] > 100:
            clone_color = C["red"]
        elif r["clones"] > 10:
            clone_color = C["yellow"]
        elif r["clones"] > 0:
            clone_color = C["green"]
        else:
            clone_color = C["dim"]

        vis_color = C["green"] if r["visibility"] == "private" else C["yellow"]
        vis_label = "priv" if r["visibility"] == "private" else "pub"

        # Skip repos with zero activity unless single repo mode
        if r["clones"] == 0 and r["views"] == 0 and not args.repo:
            continue

        name = r["name"][:28]
        print(
            f"  {name:<28} {vis_color}{vis_label:<7}{C['reset']} "
            f"{clone_color}{r['clones']:>8}{C['reset']} {r['clone_uniques']:>8} "
            f"{r['views']:>8} {r['view_uniques']:>8}"
        )

        if r["clones"] > 50 and r["visibility"] == "public":
            flagged.append(r)

    # Totals
    print(f"  {'─'*28} {'─'*7} {'─'*8} {'─'*8} {'─'*8} {'─'*8}")
    print(
        f"  {C['bold']}{'TOTAL':<28}{C['reset']} {'':7} "
        f"{C['bold']}{total_clones:>8}{C['reset']} {total_clone_uniques:>8} "
        f"{C['bold']}{total_views:>8}{C['reset']} {total_view_uniques:>8}"
    )

    # Flags
    if flagged:
        print(f"\n  {C['red']}{C['bold']}⚠ High-clone public repos:{C['reset']}")
        for r in flagged:
            print(
                f"    {C['red']}{r['name']}{C['reset']}  "
                f"{r['clones']} clones from {r['clone_uniques']} unique sources  "
                f"{C['dim']}({r['visibility']}){C['reset']}"
            )

    if errors:
        print(f"\n  {C['dim']}Skipped (no access): {', '.join(errors)}{C['reset']}")

    # Detailed view for single repo
    if args.repo and results:
        r = results[0]
        slug = r["slug"]

        print(f"\n  {C['bold']}Popular Paths{C['reset']}")
        paths = gh_api(f"repos/{slug}/traffic/popular/paths")
        if paths:
            for p in paths[:10]:
                print(f"    {p['count']:>5}  {p['uniques']:>3} unique  {C['dim']}{p['path']}{C['reset']}")
        else:
            print(f"    {C['dim']}no data{C['reset']}")

        print(f"\n  {C['bold']}Referrers{C['reset']}")
        refs = gh_api(f"repos/{slug}/traffic/popular/referrers")
        if refs:
            for ref in refs[:10]:
                print(f"    {ref['count']:>5}  {ref['uniques']:>3} unique  {C['dim']}{ref['referrer']}{C['reset']}")
        else:
            print(f"    {C['dim']}no data{C['reset']}")

        print(f"\n  {C['bold']}Daily Clones{C['reset']}")
        clones_data = gh_api(f"repos/{slug}/traffic/clones")
        if clones_data and clones_data.get("clones"):
            for day in clones_data["clones"]:
                if day["count"] > 0:
                    date = day["timestamp"][:10]
                    bar = "█" * min(day["count"] // 5, 40) if day["count"] > 0 else ""
                    print(f"    {date}  {day['count']:>5}  {day['uniques']:>3} unique  {C['dim']}{bar}{C['reset']}")

    print()


if __name__ == "__main__":
    main()
