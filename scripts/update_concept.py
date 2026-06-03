#!/usr/bin/env python3
"""Single command: ingest concept .md → legal_concepts → update factor catalog → regenerate pages.

This is the "do not waste concept" pipeline. Use this for every new concept ingest;
it guarantees the .md file, the Qdrant collection, the YAML catalog, and the HTML
pages all stay in sync.

Usage:
    uv run python scripts/update_concept.py path/to/file.md [path/to/file2.md ...]
    uv run python scripts/update_concept.py --no-pages path/to/file.md   # skip page regen
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import frontmatter
import yaml

ROOT_POL = Path(__file__).resolve().parents[1]
ROOT_DIV = Path.home() / "GitHub" / "div_legal"
CATALOG_YAML = ROOT_DIV / "data" / "algo_factors.yaml"
INGEST_SCRIPT = ROOT_POL / "scripts" / "ingest_concept.py"
TOOL_GENERATOR = ROOT_DIV / "src" / "scripts" / "generate_algos_tool.py"
MAP_GENERATOR = ROOT_DIV / "src" / "scripts" / "generate_knowledge_map.py"


def step(label: str, fn) -> bool:
    print(f"\n[{label}]")
    try:
        fn()
        return True
    except subprocess.CalledProcessError as e:
        print(f"  FAILED: {e}")
        return False
    except Exception as e:
        print(f"  FAILED: {e}")
        return False


def ingest(files: list[Path]) -> None:
    cmd = ["uv", "run", "python", str(INGEST_SCRIPT)] + [str(f) for f in files]
    subprocess.run(cmd, check=True, cwd=ROOT_POL)


def update_catalog(files: list[Path]) -> None:
    """For each file with frontmatter factor fields, ensure a YAML entry exists.

    If concept_id already in catalog: update its factor fields from frontmatter.
    If not: append a new entry.
    """
    catalog = yaml.safe_load(CATALOG_YAML.read_text()) if CATALOG_YAML.exists() else {"algos": []}
    by_id = {a["doc_id"]: a for a in catalog["algos"]}

    updated_or_added = []
    for f in files:
        post = frontmatter.load(str(f))
        meta = dict(post.metadata or {})
        cid = meta.get("concept_id") or f.stem
        # Build catalog entry shape (uses 'doc_id' for back-compat with existing yaml)
        entry = {"doc_id": cid}
        for key_in, key_out in [
            ("factor_layer", "layer"),
            ("factor_target", "target"),
            ("factor_venue", "venue"),
            ("factor_tempo", "tempo"),
            ("factor_leverage", "leverage"),
            ("factor_jurisdiction", "jurisdiction"),
        ]:
            if meta.get(key_in) is not None:
                entry[key_out] = meta[key_in]
        # Carry over precondition / anti_pattern / vocabulary if present in body (optional)
        if meta.get("precondition"):
            entry["precondition"] = meta["precondition"]
        if meta.get("anti_pattern"):
            entry["anti_pattern"] = meta["anti_pattern"]
        if meta.get("vocabulary"):
            entry["vocabulary"] = meta["vocabulary"]

        # Skip catalog write for findings/evidence (catalog is algorithm-scoped)
        if meta.get("doc_type") and meta["doc_type"] != "algorithm":
            print(f"  - {cid}: doc_type={meta['doc_type']} not added to algo catalog (catalog tracks algorithms only)")
            continue

        if cid in by_id:
            # Update in place — only fields we have data for
            for k, v in entry.items():
                if k != "doc_id":
                    by_id[cid][k] = v
            updated_or_added.append((cid, "updated"))
        else:
            catalog["algos"].append(entry)
            updated_or_added.append((cid, "added"))

    CATALOG_YAML.write_text(yaml.safe_dump(catalog, sort_keys=False, allow_unicode=True))
    for cid, action in updated_or_added:
        print(f"  - {cid}: {action} in catalog")


def regen_tool() -> None:
    subprocess.run(["uv", "run", "python", "-m", "src.scripts.generate_algos_tool"],
                   check=True, cwd=ROOT_DIV)


def regen_map() -> None:
    subprocess.run(["uv", "run", "python", "-m", "src.scripts.generate_knowledge_map"],
                   check=True, cwd=ROOT_DIV)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="+", help=".md files to ingest + index")
    parser.add_argument("--no-pages", action="store_true", help="Skip HTML regeneration")
    parser.add_argument("--no-catalog", action="store_true", help="Skip catalog YAML update")
    args = parser.parse_args()

    files = []
    for f in args.files:
        p = Path(f).expanduser().resolve()
        if not p.exists():
            print(f"  skip (missing): {f}", file=sys.stderr)
            continue
        files.append(p)

    if not files:
        sys.exit(1)

    print(f"Processing {len(files)} file(s).")

    ok = step("1/4 Ingest .md → legal_concepts", lambda: ingest(files))
    if not ok:
        sys.exit(2)

    if not args.no_catalog:
        ok = step("2/4 Update factor catalog", lambda: update_catalog(files))
        if not ok:
            sys.exit(3)

    if not args.no_pages:
        ok = step("3/4 Regenerate algos_tool.html", regen_tool)
        if not ok:
            sys.exit(4)
        ok = step("4/4 Regenerate knowledge_map.html", regen_map)
        if not ok:
            sys.exit(5)

    print(f"\n✓ Done. {len(files)} concept(s) ingested, catalog updated, pages regenerated.")
    print(f"  • /Users/jthor/GitHub/div_legal/reports/algos_tool.html")
    print(f"  • /Users/jthor/GitHub/div_legal/reports/knowledge_map.html")


if __name__ == "__main__":
    main()
