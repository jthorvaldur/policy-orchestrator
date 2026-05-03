#!/usr/bin/env python3
"""Show database status: repos → collections → data sources → live point counts."""

import sys
from collections import defaultdict
from pathlib import Path

import yaml
from qdrant_client import QdrantClient

REGISTRIES = Path(__file__).parent.parent / "registries"


def load_repos():
    with open(REGISTRIES / "repos.yaml") as f:
        return {r["name"]: r for r in yaml.safe_load(f).get("repos", [])}


def load_collections():
    with open(REGISTRIES / "vector-collections.yaml") as f:
        return yaml.safe_load(f).get("collections", {})


def get_live_counts():
    """Query actual point counts from all Qdrant ports."""
    counts = {}
    for port in [6333, 7333]:
        try:
            client = QdrantClient(host="localhost", port=port, timeout=5)
            for col in client.get_collections().collections:
                info = client.get_collection(col.name)
                counts[(port, col.name)] = info.points_count
        except Exception:
            pass
    return counts


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Database status: repos → collections → sources")
    parser.add_argument("--repo", default=None, help="Show only this repo")
    parser.add_argument("--port", type=int, default=None, help="Show only this port")
    args = parser.parse_args()

    repos = load_repos()
    collections = load_collections()
    live = get_live_counts()

    # Group collections by owner repo
    by_repo = defaultdict(list)
    for col_name, col_config in collections.items():
        owner = col_config.get("owner_repo", "?")
        by_repo[owner].append((col_name, col_config))

    # Also track which repos READ from collections they don't own
    reads_from = defaultdict(list)
    for col_name, col_config in collections.items():
        owner = col_config.get("owner_repo")
        for reader in col_config.get("allowed_readers", []):
            if reader != owner and reader != "all":
                reads_from[reader].append(col_name)

    total_points = 0

    # Print by repo
    repo_order = sorted(by_repo.keys(), key=lambda r: -sum(
        live.get((c[1].get("port", 6333), c[0]), 0) for c in by_repo[r]
    ))

    for repo_name in repo_order:
        if args.repo and repo_name != args.repo:
            continue

        repo_cols = by_repo[repo_name]
        repo_info = repos.get(repo_name, {})
        category = repo_info.get("category", "?")

        print(f"\n{'=' * 70}")
        print(f"  {repo_name}  [{category}]")
        if repo_name in reads_from:
            print(f"  Also reads: {', '.join(reads_from[repo_name])}")
        print(f"{'=' * 70}")

        for col_name, col_config in repo_cols:
            port = col_config.get("port", 6333)
            if args.port and port != args.port:
                continue

            actual = live.get((port, col_name))
            expected = col_config.get("points_expected", 0)
            model = col_config.get("embedding_model", "?")
            vtype = col_config.get("vector_type", "flat")
            quant = col_config.get("quantization", "none")
            desc = col_config.get("description", "")
            migration = col_config.get("migration_note", "")

            if actual is not None:
                total_points += actual
                status = f"{actual:>10,} pts"
                if expected > 0:
                    pct = (actual / expected) * 100
                    if pct < 80:
                        status += f"  ({pct:.0f}% of expected)"
            else:
                status = "  NOT FOUND"

            print(f"\n  {col_name}  :{port}")
            print(f"    {status}  |  {vtype}  {quant}  {model}")
            if migration:
                print(f"    {migration}")
            if desc:
                print(f"    {desc}")

            # Data sources
            sources = col_config.get("data_sources", [])
            if sources:
                print(f"    Sources:")
                for src in sources:
                    print(f"      {src['type']:<15} {src['name']}")
                    print(f"      {'':15} method: {src['method']}")

    # Unregistered collections
    registered_keys = {(c.get("port", 6333), n) for n, c in collections.items()}
    unregistered = [(port, name, count) for (port, name), count in live.items()
                    if (port, name) not in registered_keys]

    if unregistered:
        print(f"\n{'=' * 70}")
        print(f"  UNREGISTERED COLLECTIONS")
        print(f"{'=' * 70}")
        for port, name, count in sorted(unregistered):
            total_points += count
            print(f"  {name:<25} :{port}  {count:>10,} pts  (not in registry)")

    print(f"\n{'─' * 70}")
    print(f"  Total: {total_points:,} vectors across {len(live)} collections on {len(set(p for p,_ in live))} ports")


if __name__ == "__main__":
    main()
