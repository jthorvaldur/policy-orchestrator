#!/usr/bin/env python3
"""Unified search across all vector collections via docvec.

Three-stage retrieval:
  1. Hybrid prefetch (dense + sparse RRF) per collection.
  2. Cross-encoder semantic rerank.
  3. Optional recency kernel that interpolates semantic and recency scores.

Reranking is on by default — use --no-rerank to skip.
Recency boost defaults to a mild bias; use --recent for "what's the latest" queries
or --no-recency to disable.
"""

import math
import sys
from datetime import date, datetime
from pathlib import Path

import yaml


REGISTRIES = Path(__file__).parent.parent / "registries"

# How deep to prefetch from each vector space before fusion/rerank.
# Deeper = better recall at the cost of speed.  50 per space is enough
# for the reranker to see ~100 candidates per collection.
PREFETCH_DEPTH = 50

# Recency defaults — mild boost that doesn't displace strong semantic matches
# but breaks ties toward recent docs and pulls today's content into the top-K.
DEFAULT_RECENCY_TAU = 180.0    # half-life ~125 days; 1y old ≈ 0.13 weight
DEFAULT_RECENCY_WEIGHT = 0.25  # 25% recency, 75% semantic in final score
RECENT_FLAG_TAU = 14.0         # --recent: aggressive, 14-day decay
RECENT_FLAG_WEIGHT = 0.6       # --recent: 60% recency


def _parse_payload_date(payload: dict) -> date | None:
    """Extract an ISO date from common payload fields. Returns None on miss."""
    for key in ("date", "source_date", "timestamp", "extracted_at"):
        raw = payload.get(key)
        if not raw:
            continue
        s = str(raw).strip()
        if not s or s.lower() == "unknown":
            continue
        # Accept YYYY-MM-DD, full ISO datetime, or YYYY-MM
        try:
            if len(s) >= 10 and s[4] == "-" and s[7] == "-":
                return date.fromisoformat(s[:10])
            if len(s) == 7 and s[4] == "-":  # YYYY-MM
                return date.fromisoformat(s + "-01")
        except ValueError:
            continue
    return None


def _recency_weight(d: date | None, today: date, tau_days: float) -> float:
    """Exp-decay weight in [0,1]. Future dates clamp to 1.0; missing → 0.0."""
    if d is None:
        return 0.0
    age = (today - d).days
    if age <= 0:
        return 1.0
    return math.exp(-age / tau_days)


def _apply_recency_kernel(
    results: list[dict],
    today: date,
    tau_days: float,
    recency_weight: float,
) -> list[dict]:
    """Interpolate semantic and recency scores. Mutates and re-sorts results.

    final = (1 - λ) * normalized_semantic + λ * recency_weight

    Semantic scores are min-max normalized to [0,1] across the current result
    set so the interpolation lives on a comparable scale. The original score
    is preserved as `score_semantic_raw` for display/debugging.
    """
    if not results or recency_weight <= 0.0:
        return results

    raw_scores = [r["score"] for r in results]
    s_min = min(raw_scores)
    s_max = max(raw_scores)
    s_range = max(s_max - s_min, 1e-9)

    for r in results:
        r["score_semantic_raw"] = r["score"]
        r["score_semantic"] = (r["score"] - s_min) / s_range
        d = _parse_payload_date(r.get("payload", {}))
        r["score_recency"] = _recency_weight(d, today, tau_days)
        r["score"] = (1.0 - recency_weight) * r["score_semantic"] + recency_weight * r["score_recency"]

    return sorted(results, key=lambda r: r["score"], reverse=True)


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


def search(
    query,
    limit=20,
    collection=None,
    collections=None,
    rerank=True,
    tau_days: float = DEFAULT_RECENCY_TAU,
    recency_weight: float = DEFAULT_RECENCY_WEIGHT,
    today: date | None = None,
):
    """Search across collections using docvec federated search.

    Args:
        tau_days: Exponential decay constant for recency in days. Smaller = steeper.
        recency_weight: λ in [0,1]. 0 disables recency boost; 1 sorts purely by date.
        today: Override for "now" — useful for testing.
    """
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
            # Skip the version-compat check for known version-skewed servers
            # (e.g. :8333 runs server 1.14 vs a 1.17+ client) so we don't emit
            # a cosmetic UserWarning on every connection.
            client_kwargs = {}
            if port in (8333,):
                client_kwargs["check_compatibility"] = False
            client = QdrantClient(host="localhost", port=port, timeout=10, **client_kwargs)

            # Check if collection uses named vectors (hybrid)
            info = client.get_collection(name)
            vec_config = info.config.params.vectors
            is_hybrid = isinstance(vec_config, dict) and "dense" in vec_config

            # Guard against dimension mismatch. The query is embedded once with a
            # single model (768-dim BGE-base by default); collections built with a
            # different model (e.g. knowledge_v2 @ 1024-dim, koplik_library @ 4096)
            # would otherwise return HTTP 400 "Vector dimension error". Skip those
            # rather than fail the whole search.
            if is_hybrid:
                col_dim = vec_config["dense"].size
            elif hasattr(vec_config, "size"):
                col_dim = vec_config.size
            else:
                col_dim = None
            q_dim = len(query_dense)
            if col_dim is not None and col_dim != q_dim:
                print(
                    f"  {name} (:{port}): skipped — collection dense dim {col_dim} "
                    f"!= query dim {q_dim} (built with a different embedding model)",
                    file=sys.stderr,
                )
                continue

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

    # --- Two-tier dedup (runs before reranker to maximize diversity) ---
    from docvec.ids import content_fingerprint

    # Tier 1: Content fingerprint — catches cross-source and re-ingestion dupes
    seen_fp: dict[str, dict] = {}
    deduped = []
    for r in sorted(all_results, key=lambda x: x["score"], reverse=True):
        fp = content_fingerprint(r["content_preview"])
        if fp in seen_fp:
            seen_fp[fp].setdefault("similar_count", 0)
            seen_fp[fp]["similar_count"] += 1
            continue
        seen_fp[fp] = r
        r["similar_count"] = 0
        deduped.append(r)

    # Tier 2: doc_id dedup — keep highest-scoring chunk per document
    seen_docs: dict[str, dict] = {}
    final = []
    for r in deduped:
        did = r["doc_id"]
        if not did or did not in seen_docs:
            final.append(r)
            if did:
                seen_docs[did] = r
        else:
            seen_docs[did].setdefault("similar_count", 0)
            seen_docs[did]["similar_count"] += 1

    all_results = final

    # Sort by retrieval score
    all_results.sort(key=lambda r: r["score"], reverse=True)

    # Apply cross-encoder reranking
    if rerank:
        try:
            from docvec.embedder import rerank as docvec_rerank

            # Rerank a generous pool. When recency boost is active we need a
            # wider pool so recent-but-semantically-decent docs survive into
            # the final cut.
            pool_multiplier = 20 if recency_weight > 0.0 else 10
            rerank_pool = all_results[:limit * pool_multiplier]
            reranked = docvec_rerank(
                query=query,
                results=rerank_pool,
                text_key="content_preview",
                limit=len(rerank_pool),  # keep all so kernel can re-sort
            )
            # Use rerank_score as the display score
            for r in reranked:
                r["score"] = r["rerank_score"]
            all_results = reranked
            score_label = "rerank"
        except Exception as e:
            print(f"  Rerank failed, using retrieval scores: {e}", file=sys.stderr)
            score_label = "rrf"
    else:
        score_label = "rrf"

    # Apply recency kernel (no-op if recency_weight == 0)
    if recency_weight > 0.0:
        today = today or datetime.utcnow().date()
        all_results = _apply_recency_kernel(
            all_results,
            today=today,
            tau_days=tau_days,
            recency_weight=recency_weight,
        )
        score_label = f"{score_label}+recency(τ={tau_days:.0f}d,λ={recency_weight:.2f})"

    all_results = all_results[:limit]

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

        similar = r.get("similar_count", 0)
        similar_tag = f"  [+{similar} similar]" if similar else ""
        recency_tag = ""
        if "score_recency" in r:
            recency_tag = f"  ⟨sem={r['score_semantic']:.2f} rec={r['score_recency']:.2f}⟩"
        print(f"  [{i+1}] {r['score']:.3f}  {r['collection']}  {source}  {date}{similar_tag}{recency_tag}")
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

    # Recency kernel
    parser.add_argument(
        "--tau", type=float, default=DEFAULT_RECENCY_TAU,
        help=f"Recency exp-decay constant in days (default: {DEFAULT_RECENCY_TAU:g})",
    )
    parser.add_argument(
        "--recency", type=float, default=DEFAULT_RECENCY_WEIGHT,
        help=f"Recency weight λ in [0,1] (default: {DEFAULT_RECENCY_WEIGHT:g}; 0 disables)",
    )
    parser.add_argument(
        "--recent", action="store_true",
        help=f"Aggressive recency preset: τ={RECENT_FLAG_TAU:g}d, λ={RECENT_FLAG_WEIGHT:g}",
    )
    parser.add_argument(
        "--no-recency", dest="recency", action="store_const", const=0.0,
        help="Disable recency kernel entirely",
    )
    parser.add_argument(
        "--today", default=None,
        help="Override 'today' as YYYY-MM-DD (for testing/reproducibility)",
    )

    args = parser.parse_args()

    tau = args.tau
    recency = args.recency
    if args.recent:
        tau = RECENT_FLAG_TAU
        recency = RECENT_FLAG_WEIGHT

    today_override = None
    if args.today:
        today_override = date.fromisoformat(args.today)

    search(
        query=args.query,
        limit=args.limit,
        collection=args.collection,
        collections=args.collections,
        rerank=args.rerank,
        tau_days=tau,
        recency_weight=recency,
        today=today_override,
    )


if __name__ == "__main__":
    main()
