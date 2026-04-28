#!/usr/bin/env python3
"""Semantic search across Claude Code sessions in Qdrant."""

import sys
import time

import httpx
from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue

# ---------------------------------------------------------------------------
# Config (must match ingest_sessions.py)
# ---------------------------------------------------------------------------

QDRANT_HOST = "localhost"
QDRANT_PORT = 6333
COLLECTION_NAME = "claude_code_sessions"

OLLAMA_BASE_URL = "http://localhost:11434"
EMBEDDING_MODEL = "nomic-embed-text"

# ---------------------------------------------------------------------------
# Embedding (same as ingest)
# ---------------------------------------------------------------------------


def embed_text(text: str, max_chars: int = 8000, max_retries: int = 3) -> list[float]:
    """Get embedding vector via Ollama."""
    if len(text) > max_chars:
        text = text[:max_chars]
    for attempt in range(max_retries):
        try:
            resp = httpx.post(
                f"{OLLAMA_BASE_URL}/api/embeddings",
                json={"model": EMBEDDING_MODEL, "prompt": text},
                timeout=120.0,
            )
            resp.raise_for_status()
            return resp.json()["embedding"]
        except (httpx.HTTPStatusError, httpx.ConnectError, httpx.ReadTimeout):
            if attempt < max_retries - 1:
                time.sleep(1.0 * (attempt + 1))
                continue
            raise


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


def search_sessions(
    query: str,
    repo_filter: str | None = None,
    role_filter: str | None = None,
    limit: int = 10,
    show_full: bool = False,
):
    """Search Qdrant for relevant session chunks."""
    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

    # Check collection exists
    collections = [c.name for c in client.get_collections().collections]
    if COLLECTION_NAME not in collections:
        print(f"Collection '{COLLECTION_NAME}' not found. Run 'devctl ingest-sessions' first.", file=sys.stderr)
        return

    # Embed query
    print(f"Searching for: \"{query}\"", file=sys.stderr)
    query_vector = embed_text(query)

    # Build filter
    conditions = []
    if repo_filter:
        conditions.append(FieldCondition(key="repo", match=MatchValue(value=repo_filter)))
    if role_filter:
        conditions.append(FieldCondition(key="role", match=MatchValue(value=role_filter)))

    query_filter = Filter(must=conditions) if conditions else None

    # Search
    results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        query_filter=query_filter,
        limit=limit,
        with_payload=True,
    )

    if not results.points:
        print("No results found.", file=sys.stderr)
        return

    # Display
    print(f"\n{'=' * 70}")
    print(f"  Results for: \"{query}\"")
    if repo_filter:
        print(f"  Filtered to repo: {repo_filter}")
    print(f"{'=' * 70}\n")

    for i, point in enumerate(results.points):
        payload = point.payload
        score = point.score
        repo = payload.get("repo", "?")
        role = payload.get("role", "?")
        date = payload.get("date", "?")
        session_id = payload.get("session_id", "?")[:12]
        turn = payload.get("turn_index", "?")

        text = payload.get("text", "") if show_full else payload.get("content_preview", "")

        print(f"  [{i+1}] score={score:.3f}  repo={repo}  date={date}  role={role}  turn={turn}")
        print(f"      session={session_id}...")
        print(f"      {text}")
        print()

    info = client.get_collection(COLLECTION_NAME)
    print(f"Searched {info.points_count} points in '{COLLECTION_NAME}'", file=sys.stderr)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Search Claude Code sessions")
    parser.add_argument("query", help="Search query")
    parser.add_argument("--repo", default=None, help="Filter to a specific repo")
    parser.add_argument("--role", default=None, choices=["user", "assistant"], help="Filter by role")
    parser.add_argument("--limit", type=int, default=10, help="Number of results")
    parser.add_argument("--full", action="store_true", help="Show full chunk text instead of preview")

    args = parser.parse_args()
    search_sessions(
        query=args.query,
        repo_filter=args.repo,
        role_filter=args.role,
        limit=args.limit,
        show_full=args.full,
    )


if __name__ == "__main__":
    main()
