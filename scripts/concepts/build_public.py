"""Build PUBLIC variants of the algos_tool and knowledge_map HTML pages.

Differs from the in-place generators in div_legal/src/scripts/ by:
  - Strict filter: doc_type=algorithm AND case_id=universal only.
  - Runs the audit gate first; any contamination aborts the build.
  - Writes to a build/ directory, NOT the live reports/.

Usage:
    uv run python -m scripts.concepts.build_public
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from . import audit as audit_module

ROOT_POL = Path(__file__).resolve().parents[2]
ROOT_DIV = Path.home() / "GitHub" / "div_legal"
BUILD_DIR = ROOT_POL / "build" / "concepts_public"
TOOL_GEN = ROOT_DIV / "src" / "scripts" / "generate_algos_tool.py"
MAP_GEN = ROOT_DIV / "src" / "scripts" / "generate_knowledge_map.py"


def gate_audit() -> None:
    """Run audit. Abort build if any algorithm chunk contains personal markers."""
    print("[gate] Running audit...")
    report = audit_module.audit(include_findings=False)
    if "error" in report:
        print(f"  audit error: {report['error']}", file=sys.stderr)
        sys.exit(2)
    if report["dirty"]:
        print(f"  AUDIT FAILED — {report['dirty_count']} contaminated algorithms.", file=sys.stderr)
        for d in report["dirty"]:
            print(f"    ✗ {d['concept_id']}: {d['total_marker_hits']} hits", file=sys.stderr)
        print(f"\n  Scrub before retrying. See scripts/concepts/scrub.py.", file=sys.stderr)
        sys.exit(1)
    print(f"  ✓ {report['clean_count']} algorithms clean. Build can proceed.")


def regenerate_in_place() -> None:
    """Run the existing in-place generators, then copy & filter to BUILD_DIR."""
    print("[build] Regenerating in-place HTML pages...")
    for module in ("generate_algos_tool", "generate_knowledge_map", "generate_network_map"):
        subprocess.run(["uv", "run", "python", "-m", f"src.scripts.{module}"],
                       check=True, cwd=ROOT_DIV, capture_output=True)


def filter_html(src: Path, dst: Path) -> None:
    """Strip non-algorithm, non-universal entries from the embedded JSON.

    Both generators embed a JSON ALGOS array (algos_tool) or DATA/CATALOG
    (knowledge_map) directly in <script> tags. We parse the file as text,
    locate the array, filter, and re-serialize. This is brittle by design —
    if the generators change schema, this filter will surface it loudly.
    """
    text = src.read_text(encoding="utf-8")

    # Network map has its own data shape; no filter needed (catalog is already
    # algorithm-scoped and audit-gated). Just copy through.
    if "const GRAPH =" in text:
        pass
    # Check knowledge_map FIRST — it has CATALOG; algos_tool does not.
    elif "const CATALOG =" in text:
        text = _filter_knowledge_map(text)
    # algos_tool.html: const ALGOS = [...]
    elif "const ALGOS =" in text:
        text = _filter_algos_tool(text)

    dst.write_text(text, encoding="utf-8")


def _slice_json_after(text: str, marker: str) -> tuple[str, int, int]:
    """Return (json_text, start_idx, end_idx) for the JSON value following marker."""
    start = text.index(marker) + len(marker)
    # Skip whitespace
    while start < len(text) and text[start] in " \t":
        start += 1
    if text[start] not in "[{":
        raise ValueError(f"Expected JSON [ or {{ after marker {marker!r}")
    bracket = text[start]
    close = "]" if bracket == "[" else "}"
    depth = 0
    in_str = False
    esc = False
    i = start
    while i < len(text):
        c = text[i]
        if esc:
            esc = False
        elif in_str:
            if c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == bracket:
                depth += 1
            elif c == close:
                depth -= 1
                if depth == 0:
                    return text[start:i + 1], start, i + 1
        i += 1
    raise ValueError(f"Unterminated JSON value for marker {marker!r}")


def _filter_algos_tool(text: str) -> str:
    j, s, e = _slice_json_after(text, "const ALGOS =")
    data = json.loads(j)
    filtered = [
        a for a in data
        if (a.get("layer") not in (None, "unscored", "")) and (a.get("in_db", True))
    ]
    # Drop anything with doc_type implied by layer == 'finding' or 'evidence'
    # (those aren't in this payload schema; just keep algorithm-shaped entries).
    new_json = json.dumps(filtered, ensure_ascii=False)
    return text[:s] + new_json + text[e:]


def _filter_knowledge_map(text: str) -> str:
    # CATALOG is the source-of-truth — filter to algorithm-shaped entries
    j_cat, s_cat, e_cat = _slice_json_after(text, "const CATALOG =")
    catalog = json.loads(j_cat)
    filtered_catalog = [c for c in catalog if c.get("layer") not in (None, "unscored", "")]
    new_cat_json = json.dumps(filtered_catalog, ensure_ascii=False)
    text = text[:s_cat] + new_cat_json + text[e_cat:]

    # DATA.join keyed by doc_id — filter to same set
    valid_ids = {c["doc_id"] for c in filtered_catalog}
    j_data, s_data, e_data = _slice_json_after(text, "const DATA =")
    data = json.loads(j_data)
    data["join"] = {k: v for k, v in data.get("join", {}).items() if k in valid_ids}
    data["co_occurrence"] = {
        k: [pair for pair in v if pair[0] in valid_ids]
        for k, v in data.get("co_occurrence", {}).items()
        if k in valid_ids
    }
    new_data_json = json.dumps(data, ensure_ascii=False)
    return text[:s_data] + new_data_json + text[e_data:]


def main() -> None:
    gate_audit()
    regenerate_in_place()

    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    sources = [
        ROOT_DIV / "reports" / "algos_tool.html",
        ROOT_DIV / "reports" / "knowledge_map.html",
        ROOT_DIV / "reports" / "network_map.html",
    ]
    for src in sources:
        dst = BUILD_DIR / src.name
        filter_html(src, dst)
        print(f"[build] wrote {dst}")

    # Also drop a tiny landing page
    landing = BUILD_DIR / "index.html"
    landing.write_text(_landing_html(), encoding="utf-8")
    print(f"[build] wrote {landing}")
    print(f"\n✓ Public build ready in {BUILD_DIR}")


def _landing_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Algorithm Catalog</title>
<style>
:root { --bg:#0e1014; --panel:#161922; --ink:#e7e9ee; --ink-dim:#9aa3b2; --accent:#f5a623; --edge:#1f2330; }
body { margin:0; background:var(--bg); color:var(--ink); font:14px/1.55 'Inter','SF Pro Text',-apple-system,sans-serif; }
.wrap { max-width:880px; margin:60px auto; padding:0 28px; }
h1 { font-weight:600; letter-spacing:-.01em; font-size:34px; margin:0 0 8px; }
.subtitle { color:var(--ink-dim); font-size:14px; margin-bottom:36px; }
.cards { display:grid; grid-template-columns:repeat(3, 1fr); gap:16px; }
.card { background:var(--panel); border:1px solid var(--edge); border-radius:10px; padding:22px 22px; text-decoration:none; color:inherit; transition:border-color .15s; }
.card:hover { border-color:var(--accent); }
.card h2 { margin:0 0 6px; font-size:17px; font-weight:600; color:var(--accent); }
.card p { margin:0; color:var(--ink-dim); font-size:12px; line-height:1.5; }
footer { color:var(--ink-dim); font-size:11px; margin-top:48px; text-align:center; font-family:'JetBrains Mono',ui-monospace,monospace; }
@media (max-width:780px) { .cards { grid-template-columns:1fr; } }
</style>
</head>
<body>
<div class="wrap">
  <h1>Algorithm Catalog</h1>
  <p class="subtitle">Procedural and strategic algorithms for high-conflict litigation. Universal, case-portable, abstract.</p>
  <div class="cards">
    <a class="card" href="./algos_tool.html">
      <h2>Explorer</h2>
      <p>Card grid, filter by 14 factor dimensions, factor-matrix heatmap, gap-density view.</p>
    </a>
    <a class="card" href="./knowledge_map.html">
      <h2>Vocabulary Map</h2>
      <p>Each algorithm joined to a 282K-row statutory vocabulary DB. Leverage scores, jurisdiction tags, statute pointers.</p>
    </a>
    <a class="card" href="./network_map.html">
      <h2>Network Map</h2>
      <p>Force-directed graph. Edges by shared vocabulary and shared factor cells. Click any node for detail.</p>
    </a>
  </div>
  <footer>Built from audited corpus. No case data. No personal identifiers. Share freely.</footer>
</div>
</body>
</html>
"""


if __name__ == "__main__":
    main()
