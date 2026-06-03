#!/usr/bin/env python3
"""Migrate the 26 algos from `algorithms` collection → `legal_concepts`.

For each algo in data/algo_factors.yaml:
  - Look up the source_file path (read from algorithms collection payload)
  - Re-ingest the .md with full factor metadata as frontmatter overrides
  - case_id='universal', doc_type='algorithm', applicable_cases=['universal']

Does NOT delete the source `algorithms` collection — kept as legacy.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
import yaml
from docvec.config import EmbedConfig
from qdrant_client import QdrantClient

# Reuse the ingest function
sys.path.insert(0, str(Path(__file__).parent))
from ingest_concept import ingest_file  # noqa: E402

ALGOS_QDRANT = "http://localhost:6333"
ALGO_FACTORS = Path("/Users/jthor/GitHub/div_legal/data/algo_factors.yaml")


SEARCH_BASES = [
    Path.home() / "GitHub" / "div_legal",
    Path.home() / "GitHub",  # for caseledger/docs/*
    Path("/"),
]


def resolve_path(sf: str) -> Path | None:
    p = Path(sf).expanduser()
    if p.is_absolute() and p.exists():
        return p
    for base in SEARCH_BASES:
        cand = base / sf
        if cand.exists():
            return cand
    return None


def lookup_source_files() -> dict[str, str]:
    """concept_id → source_file from `algorithms` collection."""
    out: dict[str, str] = {}
    offset = None
    while True:
        body = {"limit": 256, "with_payload": True, "with_vector": False}
        if offset is not None:
            body["offset"] = offset
        r = httpx.post(f"{ALGOS_QDRANT}/collections/algorithms/points/scroll", json=body, timeout=30)
        r.raise_for_status()
        data = r.json()["result"]
        for p in data["points"]:
            pl = p["payload"]
            did = pl.get("doc_id", "")
            sf = pl.get("source_file", "")
            if did and sf and did not in out and pl.get("doc_type") not in ("word", "words", ""):
                out[did] = sf
        offset = data.get("next_page_offset")
        if offset is None:
            break
    return out


def main() -> None:
    catalog = yaml.safe_load(ALGO_FACTORS.read_text())["algos"]
    sources = lookup_source_files()
    print(f"Catalog: {len(catalog)} algos. Sources found: {len(sources)}.")

    config = EmbedConfig(embed_backend="st", dense_model="BAAI/bge-base-en-v1.5")
    client = QdrantClient(host="localhost", port=6333, timeout=60)

    total = 0
    for entry in catalog:
        cid = entry["doc_id"]
        sf = sources.get(cid)
        if not sf:
            print(f"  - SKIP {cid}: no source_file in algorithms collection")
            continue
        resolved = resolve_path(sf)
        if resolved is None:
            print(f"  - SKIP {cid}: source file not found ({sf})")
            continue
        sf_path = resolved
        # Build overrides from factor catalog
        overrides = {
            "concept_id": cid,
            "doc_type": "algorithm",
            "case_id": "universal",
            "applicable_cases": ["universal"],
            "factor_layer": entry.get("layer"),
            "factor_leverage": entry.get("leverage"),
            "factor_target": entry.get("target"),
            "factor_venue": entry.get("venue"),
            "factor_tempo": entry.get("tempo"),
            "factor_jurisdiction": entry.get("jurisdiction"),
            "abstraction_level": "fully-abstract",
        }
        total += ingest_file(client, config, sf_path, overrides=overrides, replace=True)

    print(f"\nMigrated {total} chunks across {len(catalog)} algos into legal_concepts.")


if __name__ == "__main__":
    main()
