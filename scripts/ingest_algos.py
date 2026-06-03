#!/usr/bin/env python3
"""Ingest procedural/strategic algorithms into Qdrant `algorithms` collection.

Matches existing payload schema:
    doc_id          — stable slug (filename stem)
    doc_type        — 'algorithm' (or 'philosophy' / 'analysis' / etc.)
    source_file     — path string for traceability
    chunk_index     — sequential within doc
    content_preview — full chunk text

Hybrid: dense (BGE-base-en-v1.5, 768d) + sparse (SPLADE++) via docvec.

Usage:
    uv run python scripts/ingest_algos.py <file1.md> [<file2.md> ...]
    uv run python scripts/ingest_algos.py --type algorithm <file.md>
"""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

from docvec.config import EmbedConfig
from docvec.embedder import embed_hybrid
from qdrant_client import QdrantClient
from qdrant_client.models import (
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PointStruct,
    SparseVector,
)

COLLECTION = "algorithms"
QDRANT_PORT = 6333
CHUNK_TOKENS = 512        # ~512 tokens ≈ ~2000 chars
CHUNK_OVERLAP_CHARS = 200
MAX_CHUNK_CHARS = 2200


def chunk_markdown(text: str) -> list[str]:
    """Header-aware chunking with overlap."""
    if not text.strip():
        return []
    # Split on H1/H2/H3 boundaries when possible
    import re
    parts = re.split(r"\n(?=#{1,3}\s)", text)
    chunks: list[str] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if len(part) <= MAX_CHUNK_CHARS:
            chunks.append(part)
        else:
            # Sliding window
            i = 0
            while i < len(part):
                chunks.append(part[i : i + MAX_CHUNK_CHARS])
                i += MAX_CHUNK_CHARS - CHUNK_OVERLAP_CHARS
    return chunks


def _delete_existing(client: QdrantClient, doc_id: str) -> int:
    """Delete all existing points for a doc_id. Returns count deleted (approx)."""
    pre = client.count(
        collection_name=COLLECTION,
        count_filter=Filter(must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]),
        exact=True,
    ).count
    if pre > 0:
        client.delete(
            collection_name=COLLECTION,
            points_selector=FilterSelector(
                filter=Filter(must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]),
            ),
        )
    return pre


def ingest_file(client: QdrantClient, config: EmbedConfig, path: Path, doc_type: str, replace: bool = True) -> int:
    text = path.read_text(encoding="utf-8")
    doc_id = path.stem  # filename without extension
    chunks = chunk_markdown(text)
    if not chunks:
        print(f"  skip (empty): {path.name}")
        return 0

    if replace:
        deleted = _delete_existing(client, doc_id)
        if deleted:
            print(f"  - removed {deleted} stale chunks for {doc_id}")

    points: list[PointStruct] = []
    for idx, chunk in enumerate(chunks):
        hybrid = embed_hybrid(chunk, config=config)
        points.append(
            PointStruct(
                id=str(uuid.uuid4()),
                vector={
                    "dense": hybrid.dense,
                    "sparse": SparseVector(
                        indices=hybrid.sparse.indices,
                        values=hybrid.sparse.values,
                    ),
                },
                payload={
                    "doc_id": doc_id,
                    "doc_type": doc_type,
                    "source_file": str(path),
                    "chunk_index": idx,
                    "content_preview": chunk,
                },
            )
        )

    client.upsert(collection_name=COLLECTION, points=points)
    print(f"  ✓ {doc_id}: {len(chunks)} chunks")
    return len(chunks)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest algorithm markdown files into Qdrant")
    parser.add_argument("files", nargs="+", help="Algorithm .md files to ingest")
    parser.add_argument(
        "--type", default="algorithm",
        choices=["algorithm", "philosophy", "analysis", "template", "filing"],
        help="doc_type tag (default: algorithm)",
    )
    parser.add_argument("--port", type=int, default=QDRANT_PORT)
    parser.add_argument(
        "--no-replace", dest="replace", action="store_false",
        help="Do NOT delete existing points for the same doc_id (default: replace).",
    )
    args = parser.parse_args()

    config = EmbedConfig(embed_backend="st", dense_model="BAAI/bge-base-en-v1.5")
    client = QdrantClient(host="localhost", port=args.port, timeout=60)

    # Verify collection exists
    existing = {c.name for c in client.get_collections().collections}
    if COLLECTION not in existing:
        print(f"ERROR: collection '{COLLECTION}' does not exist on :{args.port}", file=sys.stderr)
        sys.exit(1)

    total_chunks = 0
    for f in args.files:
        path = Path(f).expanduser().resolve()
        if not path.exists():
            print(f"  skip (missing): {f}", file=sys.stderr)
            continue
        total_chunks += ingest_file(client, config, path, args.type, replace=args.replace)

    print(f"\nIngested {total_chunks} chunks across {len(args.files)} file(s) into '{COLLECTION}' on :{args.port}")


if __name__ == "__main__":
    main()
