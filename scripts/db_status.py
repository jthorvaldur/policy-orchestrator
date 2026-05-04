#!/usr/bin/env python3
"""Show database status: repos → collections → data sources → live point counts."""

import sys
from collections import defaultdict
from pathlib import Path

import yaml
from qdrant_client import QdrantClient

REGISTRIES = Path(__file__).parent.parent / "registries"

# ANSI colors
C = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[90m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "mag": "\033[35m",
    "cyan": "\033[36m",
    "white": "\033[37m",
}


def fmt(n):
    """Format number with commas."""
    return f"{n:,}"


def load_repos():
    with open(REGISTRIES / "repos.yaml") as f:
        return {r["name"]: r for r in yaml.safe_load(f).get("repos", [])}


def load_collections():
    with open(REGISTRIES / "vector-collections.yaml") as f:
        return yaml.safe_load(f).get("collections", {})


def get_live_state():
    """Query actual state from all Qdrant ports — points, vector config, quantization."""
    state = {}
    for port in [6333, 7333]:
        try:
            client = QdrantClient(host="localhost", port=port, timeout=5)
            for col in client.get_collections().collections:
                info = client.get_collection(col.name)
                cfg = info.config.params

                # Detect hybrid (named vectors with sparse)
                sparse = cfg.sparse_vectors
                has_sparse = bool(sparse) and len(sparse) > 0
                vtype = "hybrid" if has_sparse else "flat"

                # Quantization
                quant = info.config.quantization_config
                quant_str = "int8" if quant and "Scalar" in type(quant).__name__ else \
                            "binary" if quant and "Binary" in type(quant).__name__ else "none"

                # Dimension
                vectors = cfg.vectors
                if hasattr(vectors, 'size'):
                    dim = vectors.size
                elif isinstance(vectors, dict) and vectors:
                    first = next(iter(vectors.values()))
                    dim = first.size if hasattr(first, 'size') else 0
                else:
                    dim = 0

                state[(port, col.name)] = {
                    "points": info.points_count,
                    "status": info.status.value if hasattr(info.status, 'value') else str(info.status),
                    "vector_type": vtype,
                    "quantization": quant_str,
                    "dimension": dim,
                }
        except Exception:
            pass
    return state


def size_color(points):
    """Color based on collection size."""
    if points >= 100_000:
        return C["green"]
    if points >= 10_000:
        return C["cyan"]
    if points >= 1_000:
        return C["white"]
    if points >= 100:
        return C["dim"]
    return C["yellow"]


def status_icon(status_str):
    if status_str == "green":
        return f"{C['green']}●{C['reset']}"
    if status_str == "yellow":
        return f"{C['yellow']}●{C['reset']}"
    return f"{C['red']}●{C['reset']}"


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Database status: repos → collections → sources")
    parser.add_argument("--repo", default=None, help="Show only this repo")
    parser.add_argument("--port", type=int, default=None, help="Show only this port")
    args = parser.parse_args()

    repos = load_repos()
    collections = load_collections()
    live = get_live_state()

    # Group collections by owner repo
    by_repo = defaultdict(list)
    for col_name, col_config in collections.items():
        owner = col_config.get("owner_repo", "?")
        by_repo[owner].append((col_name, col_config))

    # Track which repos READ from collections they don't own
    reads_from = defaultdict(list)
    for col_name, col_config in collections.items():
        owner = col_config.get("owner_repo")
        for reader in col_config.get("allowed_readers", []):
            if reader != owner and reader != "all":
                reads_from[reader].append(col_name)

    total_points = 0
    total_collections = 0

    # Sort repos by total points (biggest first)
    repo_order = sorted(by_repo.keys(), key=lambda r: -sum(
        live.get((c[1].get("port", 6333), c[0]), {}).get("points", 0) for c in by_repo[r]
    ))

    print(f"\n{C['bold']}  Database Status{C['reset']}")
    print(f"  {'─'*65}\n")

    for repo_name in repo_order:
        if args.repo and repo_name != args.repo:
            continue

        repo_cols = by_repo[repo_name]
        repo_info = repos.get(repo_name, {})
        category = repo_info.get("category", "?")

        # Sum points for this repo
        repo_total = sum(
            live.get((c[1].get("port", 6333), c[0]), {}).get("points", 0)
            for c in repo_cols
        )

        col_color = size_color(repo_total)
        print(f"  {C['bold']}{repo_name}{C['reset']}  {C['dim']}[{category}]{C['reset']}  {col_color}{fmt(repo_total)} vectors{C['reset']}")

        if repo_name in reads_from:
            print(f"  {C['dim']}reads: {', '.join(reads_from[repo_name])}{C['reset']}")

        for col_name, col_config in repo_cols:
            port = col_config.get("port", 6333)
            if args.port and port != args.port:
                continue

            live_info = live.get((port, col_name), {})
            actual = live_info.get("points", None)
            status = live_info.get("status", "unknown")
            model = col_config.get("embedding_model", "?")
            # Use LIVE state for vector type and quantization, not registry
            vtype = live_info.get("vector_type", col_config.get("vector_type", "?"))
            quant = live_info.get("quantization", col_config.get("quantization", "?"))
            desc = col_config.get("description", "")
            migration = col_config.get("migration_note", "")

            icon = status_icon(status)

            if actual is not None:
                total_points += actual
                total_collections += 1
                pts_color = size_color(actual)
                pts_str = f"{pts_color}{fmt(actual):>12}{C['reset']}"
            else:
                pts_str = f"{C['red']}{'NOT FOUND':>12}{C['reset']}"
                total_collections += 1

            # Type badge
            if vtype == "hybrid":
                type_badge = f"{C['green']}hybrid{C['reset']}"
            else:
                type_badge = f"{C['dim']}flat{C['reset']}"

            quant_badge = f"{C['cyan']}{quant}{C['reset']}" if quant != "none" else f"{C['dim']}none{C['reset']}"

            print(f"    {icon} {C['bold']}{col_name}{C['reset']}  :{port}  {pts_str}  {type_badge}  {quant_badge}  {C['dim']}{model}{C['reset']}")

            # Chunking + coverage info
            chunk_parts = []
            if col_config.get("chunk_max_chars"):
                chunk_parts.append(f"{col_config['chunk_max_chars']}ch")
            if col_config.get("chunk_turns"):
                chunk_parts.append(f"{col_config['chunk_turns']}turns")
            if col_config.get("chunk_msgs"):
                chunk_parts.append(f"{col_config['chunk_msgs']}msgs")
            if col_config.get("chunk_overlap_chars"):
                chunk_parts.append(f"+{col_config['chunk_overlap_chars']}ov")
            if col_config.get("chunk_overlap_turns"):
                chunk_parts.append(f"+{col_config['chunk_overlap_turns']}ov")
            if col_config.get("chunk_overlap_msgs"):
                chunk_parts.append(f"+{col_config['chunk_overlap_msgs']}ov")
            src_convos = col_config.get("source_conversations")
            if src_convos:
                chunk_parts.append(f"from {fmt(src_convos)} convos")
            src_lines = col_config.get("source_lines")
            if src_lines:
                chunk_parts.append(f"{fmt(src_lines)} source lines")
            coverage = col_config.get("coverage_pct")
            if coverage is not None:
                cov_color = C["green"] if coverage >= 80 else C["yellow"] if coverage >= 50 else C["red"]
                chunk_parts.append(f"{cov_color}{coverage}% coverage{C['reset']}")

            if chunk_parts:
                print(f"      {C['dim']}chunk: {' '.join(chunk_parts)}{C['reset']}")

            if migration:
                print(f"      {C['yellow']}{migration}{C['reset']}")

            note = col_config.get("note", "")
            if note:
                print(f"      {C['yellow']}{note}{C['reset']}")
            elif desc:
                print(f"      {C['dim']}{desc}{C['reset']}")

            # Data sources (compact)
            sources = col_config.get("data_sources", [])
            if sources:
                src_names = [s["name"] for s in sources]
                print(f"      {C['dim']}sources: {', '.join(src_names)}{C['reset']}")

        print()

    # Unregistered collections
    registered_keys = {(c.get("port", 6333), n) for n, c in collections.items()}
    unregistered = [(port, name, info) for (port, name), info in live.items()
                    if (port, name) not in registered_keys]

    if unregistered:
        print(f"  {C['yellow']}{C['bold']}Unregistered{C['reset']}")
        for port, name, info in sorted(unregistered):
            pts = info.get("points", 0)
            total_points += pts
            total_collections += 1
            print(f"    {C['yellow']}?{C['reset']} {name:<25} :{port}  {C['yellow']}{fmt(pts):>12}{C['reset']}  {C['dim']}not in registry{C['reset']}")
        print()

    # Summary
    ports = len(set(p for p, _ in live))
    print(f"  {'─'*65}")
    print(f"  {C['bold']}{fmt(total_points)}{C['reset']} vectors  "
          f"{C['dim']}across{C['reset']} {total_collections} collections  "
          f"{C['dim']}on{C['reset']} {ports} ports\n")


if __name__ == "__main__":
    main()
