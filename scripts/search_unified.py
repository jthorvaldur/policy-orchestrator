#!/usr/bin/env python3
"""Unified search across all vector collections via docvec."""

import sys
from pathlib import Path

import yaml


REGISTRIES = Path(__file__).parent.parent / "registries"


def load_registry():
    with open(REGISTRIES / "vector-collections.yaml") as f:
        return yaml.safe_load(f).get("collections", {})


def search(query, limit=10, collection=None, collections=None, rerank=False):
    """Search across collections using docvec federated search."""
    from docvec.config import EmbedConfig
    from docvec.embedder import embed_text
    from qdrant_client import QdrantClient
    from qdrant_client.models import ScoredPoint

    registry = load_registry()

    # Determine which collections to search
    if collection:
        if collection not in registry:
            print(f"Collection '{collection}' not in registry", file=sys.stderr)
            return
        targets = {collection: registry[collection]}
    elif collections:
        names = [c.strip() for c in collections.split(",")]
        targets = {n: registry[n] for n in names if n in registry}
    else:
        # Search all readable collections (skip tiny ones like feedback/facts)
        targets = {
            n: c for n, c in registry.items()
            if c.get("points_expected", 0) > 50
        }

    if not targets:
        print("No collections to search.", file=sys.stderr)
        return

    # Embed query — use BGE if available, fall back to nomic
    try:
        config = EmbedConfig(embed_backend="st", dense_model="BAAI/bge-base-en-v1.5")
        query_vector = embed_text(query, config=config)
        model_used = "BGE"
    except Exception:
        # Fall back to ollama/nomic
        import httpx
        resp = httpx.post(
            "http://localhost:11434/api/embeddings",
            json={"model": "nomic-embed-text", "prompt": query},
            timeout=30,
        )
        query_vector = resp.json()["embedding"]
        model_used = "nomic"

    print(f"Searching {len(targets)} collection(s) with {model_used}...", file=sys.stderr)

    # Search each collection
    all_results = []
    for name, config in targets.items():
        port = config.get("port", 6333)
        try:
            client = QdrantClient(host="localhost", port=port, timeout=10)

            # Check if collection uses named vectors
            info = client.get_collection(name)
            vec_config = info.config.params.vectors

            if isinstance(vec_config, dict) and "dense" in vec_config:
                # Hybrid collection — search dense vector
                results = client.query_points(
                    collection_name=name,
                    query=query_vector,
                    using="dense",
                    limit=limit,
                    with_payload=True,
                )
            else:
                # Flat collection
                results = client.query_points(
                    collection_name=name,
                    query=query_vector,
                    limit=limit,
                    with_payload=True,
                )

            for pt in results.points:
                all_results.append({
                    "collection": name,
                    "port": port,
                    "score": pt.score,
                    "payload": pt.payload,
                })
        except Exception as e:
            print(f"  {name} (:{port}): {e}", file=sys.stderr)

    # Sort by score descending, take top N
    all_results.sort(key=lambda r: r["score"], reverse=True)
    top = all_results[:limit]

    if not top:
        print("No results found.", file=sys.stderr)
        return

    print(f"\n{'=' * 70}")
    print(f"  Search: \"{query}\"")
    print(f"  {len(all_results)} results across {len(targets)} collections")
    print(f"{'=' * 70}\n")

    for i, r in enumerate(top):
        p = r["payload"]
        # Try to extract text preview from various payload schemas
        text = (p.get("text") or p.get("content_preview") or
                p.get("content") or p.get("fact") or
                p.get("learned_rule") or str(p))[:200]

        source = p.get("source_type") or p.get("role") or p.get("repo") or ""
        date = p.get("date") or p.get("source_date") or p.get("timestamp", "")[:10] or ""

        print(f"  [{i+1}] {r['score']:.3f}  {r['collection']}  {source}  {date}")
        print(f"      {text}")
        print()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Unified cross-repo vector search")
    parser.add_argument("query", help="Search query")
    parser.add_argument("--limit", "-n", type=int, default=10)
    parser.add_argument("--collection", "-c", default=None, help="Search specific collection")
    parser.add_argument("--collections", default=None, help="Comma-separated collection names")
    parser.add_argument("--rerank", action="store_true", help="Apply cross-encoder reranking")

    args = parser.parse_args()
    search(
        query=args.query,
        limit=args.limit,
        collection=args.collection,
        collections=args.collections,
        rerank=args.rerank,
    )


if __name__ == "__main__":
    main()
