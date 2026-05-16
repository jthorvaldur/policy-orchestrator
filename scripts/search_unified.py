#!/usr/bin/env python3
"""Unified search across all vector collections via docvec.

Two-stage retrieval: hybrid prefetch (dense + sparse RRF) → cross-encoder rerank.
Reranking is on by default — use --no-rerank to skip.
"""

import sys
from pathlib import Path

import yaml


REGISTRIES = Path(__file__).parent.parent / "registries"

# How deep to prefetch from each vector space before fusion/rerank.
# Deeper = better recall at the cost of speed.  50 per space is enough
# for the reranker to see ~100 candidates per collection.
PREFETCH_DEPTH = 50


def load_registry():
    with open(REGISTRIES / "vector-collections.yaml") as f:
        return yaml.safe_load(f).get("collections", {})


def _text_for_result(payload: dict) -> str:
    """Extract the best text preview from a result payload."""
    # Try fields in order of preference — longer is better for reranking
    for key in ("text", "content", "body", "content_preview", "fact", "learned_rule"):
        v = payload.get(key)
        if v and isinstance(v, str) and len(v.strip()) > 20:
            return v.strip()
    return str(payload)


def search(query, limit=20, collection=None, collections=None, rerank=True):
    """Search across collections using docvec federated search."""
    from docvec.config import EmbedConfig
    from docvec.embedder import embed_hybrid, embed_text
    from qdrant_client import QdrantClient
    from qdrant_client.models import Prefetch, FusionQuery, Fusion, SparseVector

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

    # When reranking, fetch more candidates per collection so the reranker
    # has a wide pool to choose from.
    fetch_per_collection = limit * 5 if rerank else limit

    print(
        f"Searching {len(targets)} collection(s) with {model_used}"
        f"{' + rerank' if rerank else ''}...",
        file=sys.stderr,
    )

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
                results = client.query_points(
                    collection_name=name,
                    prefetch=[
                        Prefetch(
                            query=query_dense,
                            using="dense",
                            limit=PREFETCH_DEPTH,
                        ),
                        Prefetch(
                            query=SparseVector(
                                indices=query_sparse.indices,
                                values=query_sparse.values,
                            ),
                            using="sparse",
                            limit=PREFETCH_DEPTH,
                        ),
                    ],
                    query=FusionQuery(fusion=Fusion.RRF),
                    limit=fetch_per_collection,
                    with_payload=True,
                )
            elif is_hybrid:
                results = client.query_points(
                    collection_name=name,
                    query=query_dense,
                    using="dense",
                    limit=fetch_per_collection,
                    with_payload=True,
                )
            else:
                results = client.query_points(
                    collection_name=name,
                    query=query_dense,
                    limit=fetch_per_collection,
                    with_payload=True,
                )

            for pt in results.points:
                payload = pt.payload or {}
                text = _text_for_result(payload)
                all_results.append({
                    "collection": name,
                    "port": port,
                    "retrieval_score": pt.score,
                    "score": pt.score,
                    "payload": payload,
                    "content_preview": text[:1500],  # cross-encoder can use more context
                    "doc_id": payload.get("doc_id", ""),
                })
        except Exception as e:
            print(f"  {name} (:{port}): {e}", file=sys.stderr)

    if not all_results:
        print("No results found.", file=sys.stderr)
        return

    # Deduplicate by doc_id — keep highest scoring chunk per document
    if any(r["doc_id"] for r in all_results):
        seen_docs: dict[str, dict] = {}
        deduped = []
        for r in sorted(all_results, key=lambda x: x["score"], reverse=True):
            did = r["doc_id"]
            if not did or did not in seen_docs:
                deduped.append(r)
                if did:
                    seen_docs[did] = r
        all_results = deduped

    # Sort by retrieval score
    all_results.sort(key=lambda r: r["score"], reverse=True)

    # Apply cross-encoder reranking
    if rerank:
        try:
            from docvec.embedder import rerank as docvec_rerank

            # Rerank the top candidates — give the reranker a generous pool
            rerank_pool = all_results[:limit * 10]
            reranked = docvec_rerank(
                query=query,
                results=rerank_pool,
                text_key="content_preview",
                limit=limit,
            )
            # Use rerank_score as the display score
            for r in reranked:
                r["score"] = r["rerank_score"]
            all_results = reranked
            score_label = "rerank"
        except Exception as e:
            print(f"  Rerank failed, using retrieval scores: {e}", file=sys.stderr)
            all_results = all_results[:limit]
            score_label = "rrf"
    else:
        all_results = all_results[:limit]
        score_label = "rrf"

    # Display
    total_candidates = sum(1 for _ in all_results)
    print(f"\n{'=' * 70}")
    print(f"  \"{query}\"  ({score_label} scores)")
    print(f"{'=' * 70}\n")

    for i, r in enumerate(all_results):
        p = r["payload"]
        text = r.get("content_preview", "")[:200]

        source = p.get("source_type") or p.get("role") or p.get("repo") or ""
        date = p.get("date") or p.get("source_date") or p.get("timestamp", "")[:10] or ""
        title = p.get("title", "")
        if title and len(title) > 60:
            title = title[:57] + "..."

        print(f"  [{i+1}] {r['score']:.3f}  {r['collection']}  {source}  {date}")
        if title:
            print(f"      {title}")
        print(f"      {text}")
        print()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Unified cross-repo vector search")
    parser.add_argument("query", help="Search query")
    parser.add_argument("--limit", "-n", type=int, default=20)
    parser.add_argument("--collection", "-c", default=None, help="Search specific collection")
    parser.add_argument("--collections", default=None, help="Comma-separated collection names")
    parser.add_argument("--rerank", action="store_true", default=True, help="Apply cross-encoder reranking (default)")
    parser.add_argument("--no-rerank", dest="rerank", action="store_false", help="Skip reranking, use retrieval scores only")

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
