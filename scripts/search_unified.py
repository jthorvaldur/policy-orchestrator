#!/usr/bin/env python3
"""Unified search across all vector collections via docvec.

Supports hybrid search (dense + sparse RRF fusion) and cross-encoder reranking.
"""

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
    from docvec.embedder import embed_hybrid, embed_text
    from qdrant_client import QdrantClient
    from qdrant_client.models import Prefetch, FusionQuery, Fusion, SparseVector, NamedVector

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

    # Embed query — dense + sparse for hybrid search
    try:
        config = EmbedConfig(embed_backend="st", dense_model="BAAI/bge-base-en-v1.5")
        hybrid = embed_hybrid(query, config=config)
        query_dense = hybrid.dense
        query_sparse = hybrid.sparse
        model_used = "BGE+SPLADE"
    except Exception:
        # Fall back to dense-only via ollama
        try:
            import httpx
            resp = httpx.post(
                "http://localhost:11434/api/embeddings",
                json={"model": "nomic-embed-text", "prompt": query},
                timeout=30,
            )
            query_dense = resp.json()["embedding"]
            query_sparse = None
            model_used = "nomic (dense-only)"
        except Exception:
            query_dense = embed_text(query, config=config)
            query_sparse = None
            model_used = "BGE (dense-only)"

    print(f"Searching {len(targets)} collection(s) with {model_used}...", file=sys.stderr)

    # Search each collection
    all_results = []
    for name, col_config in targets.items():
        port = col_config.get("port", 6333)
        try:
            client = QdrantClient(host="localhost", port=port, timeout=10)

            # Check if collection uses named vectors (hybrid)
            info = client.get_collection(name)
            vec_config = info.config.params.vectors
            is_hybrid = isinstance(vec_config, dict) and "dense" in vec_config

            if is_hybrid and query_sparse is not None:
                # Hybrid search with RRF fusion via Qdrant Query API
                prefetch_dense = Prefetch(
                    query=query_dense,
                    using="dense",
                    limit=limit * 3,
                )
                prefetch_sparse = Prefetch(
                    query=SparseVector(
                        indices=query_sparse.indices,
                        values=query_sparse.values,
                    ),
                    using="sparse",
                    limit=limit * 3,
                )
                results = client.query_points(
                    collection_name=name,
                    prefetch=[prefetch_dense, prefetch_sparse],
                    query=FusionQuery(fusion=Fusion.RRF),
                    limit=limit,
                    with_payload=True,
                )
            elif is_hybrid:
                # Dense-only on a hybrid collection
                results = client.query_points(
                    collection_name=name,
                    query=query_dense,
                    using="dense",
                    limit=limit,
                    with_payload=True,
                )
            else:
                # Flat vector collection
                results = client.query_points(
                    collection_name=name,
                    query=query_dense,
                    limit=limit,
                    with_payload=True,
                )

            for pt in results.points:
                payload = pt.payload or {}
                text = (payload.get("text") or payload.get("content_preview") or
                        payload.get("content") or payload.get("fact") or
                        payload.get("learned_rule") or "")
                all_results.append({
                    "collection": name,
                    "port": port,
                    "score": pt.score,
                    "payload": payload,
                    "content_preview": text[:500],
                })
        except Exception as e:
            print(f"  {name} (:{port}): {e}", file=sys.stderr)

    # Sort by score descending, take top N
    all_results.sort(key=lambda r: r["score"], reverse=True)

    # Apply cross-encoder reranking if requested
    if rerank and all_results:
        try:
            from docvec.embedder import rerank as docvec_rerank
            all_results = docvec_rerank(
                query=query,
                results=all_results,
                text_key="content_preview",
                limit=limit,
            )
            print("  Reranked with cross-encoder", file=sys.stderr)
        except Exception as e:
            print(f"  Rerank failed, using fusion scores: {e}", file=sys.stderr)

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
        text = r.get("content_preview", str(p))[:200]

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
