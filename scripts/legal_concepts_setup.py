#!/usr/bin/env python3
"""Create / verify the `legal_concepts` Qdrant collection.

Unified collection that integrates:
  - algorithm     : abstract reusable procedural strategy
  - finding       : case-specific empirical finding (e.g., 18 incompetence admissions)
  - evidence      : verbatim quote + paragraph cite (e.g., Paragraph 13 self-cancel)
  - factor_index  : factor-catalog metadata for the algo

Case-portable. Every concept tagged with case_id ('universal' or case number) and
applicable_cases (list of cases the concept can be deployed in).

Hybrid vectors (dense BGE-base-en-v1.5 + sparse SPLADE++) for fast semantic search.
"""
from __future__ import annotations

import sys

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    HnswConfigDiff,
    Modifier,
    OptimizersConfigDiff,
    PayloadSchemaType,
    SparseIndexParams,
    SparseVectorParams,
    VectorParams,
)

COLLECTION = "legal_concepts"
DENSE_DIM = 768
PORT = 6333


def main(port: int = PORT) -> None:
    client = QdrantClient(host="localhost", port=port, timeout=60)

    existing = {c.name for c in client.get_collections().collections}
    if COLLECTION in existing:
        info = client.get_collection(COLLECTION)
        print(f"'{COLLECTION}' already exists. Points: {info.points_count}")
        if "--recreate" in sys.argv:
            print("--recreate flag set; deleting and recreating...")
            client.delete_collection(COLLECTION)
        else:
            print("Use --recreate to delete and rebuild. Skipping.")
            return

    print(f"Creating '{COLLECTION}' on :{port}...")
    client.create_collection(
        collection_name=COLLECTION,
        vectors_config={
            "dense": VectorParams(size=DENSE_DIM, distance=Distance.COSINE),
        },
        sparse_vectors_config={
            "sparse": SparseVectorParams(
                index=SparseIndexParams(on_disk=False),
                modifier=Modifier.IDF,
            ),
        },
        hnsw_config=HnswConfigDiff(m=16, ef_construct=100),
        optimizers_config=OptimizersConfigDiff(indexing_threshold=10_000),
    )

    # Indexes on commonly filtered payload fields
    for field, schema in [
        ("concept_id", PayloadSchemaType.KEYWORD),
        ("doc_type", PayloadSchemaType.KEYWORD),
        ("case_id", PayloadSchemaType.KEYWORD),
        ("parent_concept_id", PayloadSchemaType.KEYWORD),
        ("factor_layer", PayloadSchemaType.KEYWORD),
        ("factor_leverage", PayloadSchemaType.INTEGER),
        ("applicable_cases", PayloadSchemaType.KEYWORD),
        ("date", PayloadSchemaType.KEYWORD),
    ]:
        try:
            client.create_payload_index(
                collection_name=COLLECTION,
                field_name=field,
                field_schema=schema,
            )
            print(f"  indexed: {field}")
        except Exception as e:
            print(f"  index {field} skipped: {e}")

    print(f"\nCreated '{COLLECTION}' on :{port}.")
    print("Payload schema:")
    print("""
  concept_id        — snake_case slug (unique within doc_type)
  doc_type          — algorithm | finding | evidence | factor_index
  case_id           — 'universal' (algos) or case identifier (findings/evidence)
  applicable_cases  — list of case ids this concept can be deployed in
  parent_concept_id — link: finding → algorithm; evidence → finding
  source_file       — path to .md source
  chunk_index       — within source doc
  content_preview   — full chunk text
  factor_layer      — meta | L1_demand | L2_refuse | L3_expose | vocab | phil
  factor_leverage   — 1-5
  factor_target     — list of targets
  factor_venue      — list of venues
  factor_tempo      — preemptive | reactive | parallel | endgame
  factor_jurisdiction — list of jurisdictions
  finding_type      — contradiction | admission | assertion | pattern (findings only)
  finding_summary   — one-line synthesis (findings only)
  source_doc_id     — 8-char hash of source filing (evidence only)
  source_paragraph  — paragraph cite in source (evidence only)
  date              — ISO date of evidence/finding
  abstraction_level — case-specific | partially-abstracted | fully-abstract
  added_at          — ISO timestamp of ingest
""")


if __name__ == "__main__":
    main()
