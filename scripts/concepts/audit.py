"""Audit gate — scans legal_concepts for personal markers in algorithm chunks.

Exit codes:
    0 — clean, safe to deploy
    1 — contamination found in algorithm doc_type (deploy blocked)
    2 — Qdrant unreachable / other error

Used as the gate by deploy_concepts.py. Can also be run standalone:

    uv run python -m scripts.concepts.audit                    # report + gate
    uv run python -m scripts.concepts.audit --json             # machine-readable
    uv run python -m scripts.concepts.audit --include-findings # also audit findings (for review)
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Iterable

import httpx
import yaml

from .patterns import PERSONAL_PATTERNS

QDRANT_URL = "http://localhost:6333"
COLLECTION = "legal_concepts"
CATALOG_YAML = Path.home() / "GitHub" / "div_legal" / "data" / "algo_factors.yaml"
YAML_AUDITED_FIELDS = ("explanation", "inverse_strategy", "precondition", "anti_pattern")


def scroll_all() -> Iterable[dict]:
    offset = None
    while True:
        body = {"limit": 256, "with_payload": True, "with_vector": False}
        if offset is not None:
            body["offset"] = offset
        r = httpx.post(f"{QDRANT_URL}/collections/{COLLECTION}/points/scroll", json=body, timeout=30)
        r.raise_for_status()
        d = r.json()["result"]
        for p in d["points"]:
            yield p
        offset = d.get("next_page_offset")
        if offset is None:
            break


def audit(include_findings: bool = False) -> dict:
    """Returns audit report. Always succeeds (doesn't exit).

    Scans BOTH content_preview AND concept_id for personal markers. A concept
    whose slug embeds a personal name (e.g., judge_profile_jannusch) leaks
    that name into URLs, search results, and card titles even if the body
    is fully abstracted — so the slug must also pass.
    """
    try:
        points = list(scroll_all())
    except httpx.HTTPError as e:
        return {"error": str(e), "exit_code": 2}

    by_concept: dict[str, dict] = defaultdict(lambda: {
        "doc_type": "",
        "case_id": "",
        "source_file": "",
        "chunks": 0,
        "markers": defaultdict(int),
        "slug_markers": defaultdict(int),
        "first_offending_chunk": None,
    })

    # First pass: scan concept_id slugs (each slug audited only once).
    # Word-boundary regex doesn't fire around underscores (since `_` is \w),
    # so we normalize slugs by replacing `_` and `-` with spaces before matching.
    seen_slugs: set[str] = set()
    for p in points:
        pl = p["payload"]
        cid = pl.get("concept_id", "")
        if not cid or cid in seen_slugs:
            continue
        seen_slugs.add(cid)
        normalized = cid.replace("_", " ").replace("-", " ")
        rec = by_concept[cid]
        for name, pat in PERSONAL_PATTERNS.items():
            hits = pat.findall(normalized)
            if hits:
                rec["slug_markers"][name] += len(hits)
                rec["markers"][name] += len(hits)

    # Second pass: scan content_preview chunks
    for p in points:
        pl = p["payload"]
        cid = pl.get("concept_id", "")
        rec = by_concept[cid]
        rec["doc_type"] = pl.get("doc_type", "")
        rec["case_id"] = pl.get("case_id", "")
        if not rec["source_file"]:
            rec["source_file"] = pl.get("source_file", "")
        rec["chunks"] += 1
        text = pl.get("content_preview", "")
        for name, pat in PERSONAL_PATTERNS.items():
            hits = pat.findall(text)
            if hits:
                rec["markers"][name] += len(hits)
                if rec["first_offending_chunk"] is None:
                    rec["first_offending_chunk"] = pl.get("chunk_index", 0)

    # Third pass: scan YAML catalog text fields (explanation/inverse_strategy/precondition/anti_pattern).
    # These ship straight into the public HTML without going through Qdrant.
    if CATALOG_YAML.exists():
        try:
            catalog = yaml.safe_load(CATALOG_YAML.read_text()) or {}
        except Exception:
            catalog = {}
        for entry in catalog.get("algos") or []:
            cid = entry.get("doc_id", "")
            if not cid:
                continue
            rec = by_concept[cid]
            if not rec["doc_type"]:
                rec["doc_type"] = "algorithm"  # YAML catalog only tracks algorithms
            for field in YAML_AUDITED_FIELDS:
                val = entry.get(field, "") or ""
                if not isinstance(val, str):
                    continue
                for name, pat in PERSONAL_PATTERNS.items():
                    hits = pat.findall(val)
                    if hits:
                        rec["markers"][name] += len(hits)
                        rec.setdefault("yaml_markers", defaultdict(int))[f"{field}/{name}"] += len(hits)

    # Categorize
    auditable: list[tuple[str, dict]] = []
    skipped_findings: list[tuple[str, dict]] = []
    for cid, info in sorted(by_concept.items()):
        if info["doc_type"] == "algorithm":
            auditable.append((cid, info))
        elif info["doc_type"] in ("finding", "evidence"):
            if include_findings:
                auditable.append((cid, info))
            else:
                skipped_findings.append((cid, info))

    dirty = [(cid, info) for cid, info in auditable if info["markers"]]
    clean = [(cid, info) for cid, info in auditable if not info["markers"]]

    return {
        "total_concepts": len(by_concept),
        "auditable_count": len(auditable),
        "clean_count": len(clean),
        "dirty_count": len(dirty),
        "skipped_findings_count": len(skipped_findings),
        "dirty": [
            {
                "concept_id": cid,
                "doc_type": info["doc_type"],
                "case_id": info["case_id"],
                "source_file": info["source_file"],
                "chunks": info["chunks"],
                "markers": dict(info["markers"]),
                "slug_markers": dict(info.get("slug_markers", {})),
                "total_marker_hits": sum(info["markers"].values()),
            }
            for cid, info in dirty
        ],
        "clean": [cid for cid, _ in clean],
        "skipped_findings": [
            {"concept_id": cid, "doc_type": info["doc_type"], "case_id": info["case_id"]}
            for cid, info in skipped_findings
        ],
        "exit_code": 1 if dirty else 0,
    }


def print_report(report: dict) -> None:
    if "error" in report:
        print(f"AUDIT FAILED: {report['error']}", file=sys.stderr)
        return
    print(f"\nAudit summary")
    print(f"=" * 60)
    print(f"  Total concepts in legal_concepts: {report['total_concepts']}")
    print(f"  Auditable (doc_type=algorithm): {report['auditable_count']}")
    print(f"    ✓ clean:                      {report['clean_count']}")
    print(f"    ✗ contaminated:               {report['dirty_count']}")
    print(f"  Skipped (findings/evidence): {report['skipped_findings_count']}")
    print()
    if report["dirty"]:
        print(f"BLOCKED — {report['dirty_count']} algorithms contain personal markers:")
        for d in report["dirty"]:
            top = ", ".join(f"{k}={v}" for k, v in sorted(d["markers"].items(), key=lambda x: -x[1])[:5])
            slug_tag = ""
            if d.get("slug_markers"):
                slug_tag = f"  [SLUG leak: {', '.join(d['slug_markers'].keys())}]"
            print(f"  ✗ {d['concept_id']:50s}  {d['total_marker_hits']:3d} hits  ({top}){slug_tag}")
            print(f"      → {d['source_file']}")
        print()
        print(f"Run bulk_scrub.py against the source files, then re-ingest, then re-audit.")
    else:
        print(f"✓ CLEAN — all {report['auditable_count']} algorithms pass. Safe to deploy.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of human report")
    parser.add_argument("--include-findings", action="store_true",
                        help="Also audit doc_type=finding/evidence (will always be dirty by design)")
    args = parser.parse_args()

    report = audit(include_findings=args.include_findings)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print_report(report)
    sys.exit(report.get("exit_code", 2))


if __name__ == "__main__":
    main()
