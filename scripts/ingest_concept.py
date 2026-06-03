#!/usr/bin/env python3
"""Unified ingester for the `legal_concepts` Qdrant collection.

Accepts markdown files with YAML frontmatter declaring concept metadata, OR
explicit CLI flags. Chunks header-aware, embeds dense+sparse via docvec,
upserts with idempotent replace-by-concept-id.

Frontmatter schema (preferred):
---
concept_id: snake_case_unique_id
doc_type: algorithm | finding | evidence | factor_index
case_id: universal | 2024D006724 | hertz_uhlig_d1gn24c1023
applicable_cases: [universal]                 # for algorithms
parent_concept_id: parent_slug                # findings → algos; evidence → finding
factor_layer: meta | L1_demand | L2_refuse | L3_expose | vocab | phil
factor_leverage: 1-5
factor_target: [counterparty, judge, ...]
factor_venue: [filing, deposition, ...]
factor_tempo: preemptive | reactive | parallel | endgame
factor_jurisdiction: [universal, IL, ...]
finding_type: contradiction | admission | assertion | pattern   # findings only
finding_summary: "one-line synthesis"                           # findings only
source_doc_id: 8charhash                                        # evidence only
source_paragraph: "P13"                                         # evidence only
date: 2026-06-02                                                # findings/evidence
abstraction_level: fully-abstract | partially-abstracted | case-specific
---

# Title
content...

Usage:
  uv run python scripts/ingest_concept.py <file.md> [<file2.md> ...]
  uv run python scripts/ingest_concept.py --doc-type algorithm --case-id universal file.md
  uv run python scripts/ingest_concept.py --no-replace file.md
"""
from __future__ import annotations

import argparse
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import frontmatter
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

COLLECTION = "legal_concepts"
PORT = 6333
MAX_CHUNK_CHARS = 2200
CHUNK_OVERLAP_CHARS = 200


def chunk_markdown(text: str) -> list[str]:
    parts = re.split(r"\n(?=#{1,3}\s)", text)
    chunks: list[str] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if len(part) <= MAX_CHUNK_CHARS:
            chunks.append(part)
            continue
        i = 0
        while i < len(part):
            chunks.append(part[i : i + MAX_CHUNK_CHARS])
            i += MAX_CHUNK_CHARS - CHUNK_OVERLAP_CHARS
    return chunks


def _list_or_none(v):
    if v is None:
        return None
    if isinstance(v, list):
        return v
    return [v]


def build_payload(meta: dict, source_file: str, chunk_idx: int, chunk_text: str) -> dict:
    payload = {
        "concept_id": meta["concept_id"],
        "doc_type": meta.get("doc_type", "algorithm"),
        "case_id": meta.get("case_id", "universal"),
        "source_file": source_file,
        "chunk_index": chunk_idx,
        "content_preview": chunk_text,
        "added_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    optional = {
        "applicable_cases": _list_or_none(meta.get("applicable_cases")),
        "parent_concept_id": meta.get("parent_concept_id"),
        "factor_layer": meta.get("factor_layer"),
        "factor_leverage": meta.get("factor_leverage"),
        "factor_target": _list_or_none(meta.get("factor_target")),
        "factor_venue": _list_or_none(meta.get("factor_venue")),
        "factor_tempo": meta.get("factor_tempo"),
        "factor_jurisdiction": _list_or_none(meta.get("factor_jurisdiction")),
        "finding_type": meta.get("finding_type"),
        "finding_summary": meta.get("finding_summary"),
        "source_doc_id": meta.get("source_doc_id"),
        "source_paragraph": meta.get("source_paragraph"),
        "date": meta.get("date"),
        "abstraction_level": meta.get("abstraction_level"),
    }
    for k, v in optional.items():
        if v is not None:
            payload[k] = v
    return payload


def delete_concept(client: QdrantClient, concept_id: str) -> int:
    pre = client.count(
        collection_name=COLLECTION,
        count_filter=Filter(must=[FieldCondition(key="concept_id", match=MatchValue(value=concept_id))]),
        exact=True,
    ).count
    if pre > 0:
        client.delete(
            collection_name=COLLECTION,
            points_selector=FilterSelector(
                filter=Filter(must=[FieldCondition(key="concept_id", match=MatchValue(value=concept_id))]),
            ),
        )
    return pre


def ingest_file(
    client: QdrantClient, config: EmbedConfig, path: Path,
    overrides: dict | None = None, replace: bool = True,
) -> int:
    post = frontmatter.load(str(path))
    meta = dict(post.metadata or {})
    if overrides:
        for k, v in overrides.items():
            if v is not None:
                meta[k] = v
    if not meta.get("concept_id"):
        meta["concept_id"] = path.stem
    if not meta.get("doc_type"):
        meta["doc_type"] = "algorithm"

    chunks = chunk_markdown(post.content)
    if not chunks:
        print(f"  skip (empty): {path.name}")
        return 0

    if replace:
        deleted = delete_concept(client, meta["concept_id"])
        if deleted:
            print(f"  - removed {deleted} stale chunks for {meta['concept_id']}")

    points: list[PointStruct] = []
    for idx, chunk in enumerate(chunks):
        hybrid = embed_hybrid(chunk, config=config)
        payload = build_payload(meta, str(path), idx, chunk)
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
                payload=payload,
            )
        )

    client.upsert(collection_name=COLLECTION, points=points)
    print(f"  ✓ {meta['concept_id']} ({meta['doc_type']}/{meta['case_id']}): {len(chunks)} chunks")
    return len(chunks)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest concept markdown into legal_concepts")
    parser.add_argument("files", nargs="+", help="Markdown files to ingest")
    parser.add_argument("--doc-type", default=None, choices=["algorithm", "finding", "evidence", "factor_index"])
    parser.add_argument("--case-id", default=None)
    parser.add_argument("--parent-concept-id", default=None)
    parser.add_argument("--no-replace", dest="replace", action="store_false")
    parser.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args()

    config = EmbedConfig(embed_backend="st", dense_model="BAAI/bge-base-en-v1.5")
    client = QdrantClient(host="localhost", port=args.port, timeout=60)
    existing = {c.name for c in client.get_collections().collections}
    if COLLECTION not in existing:
        print(f"ERROR: collection '{COLLECTION}' does not exist. Run legal_concepts_setup.py first.", file=sys.stderr)
        sys.exit(1)

    overrides = {
        "doc_type": args.doc_type,
        "case_id": args.case_id,
        "parent_concept_id": args.parent_concept_id,
    }

    total = 0
    for f in args.files:
        path = Path(f).expanduser().resolve()
        if not path.exists():
            print(f"  skip (missing): {f}", file=sys.stderr)
            continue
        total += ingest_file(client, config, path, overrides=overrides, replace=args.replace)

    print(f"\nIngested {total} chunks into '{COLLECTION}' on :{args.port}.")


if __name__ == "__main__":
    main()
