"""Substitution-based scrubber for contaminated algorithm source files.

Reads a source .md (which may contain personal markers), writes a CLEAN copy
to caseledger/docs/clean/<concept_id>.md with:
  - frontmatter preserved/added (concept_id, doc_type, case_id=universal, factor_*)
  - body content with personal markers replaced by generic terms
  - inline parenthetical removals for case captions and signatures

Substitutions are intentionally conservative — readability trumps cleverness.
After scrubbing, re-ingest the clean copy through update_concept.py with the
ORIGINAL concept_id so the algorithm record in legal_concepts gets replaced.

The original source files (in div_legal/, Volkmar_Hertz/, title_IV_D/, etc.)
are NOT modified — they remain as case-coupled history.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import frontmatter

from .patterns import SUBS, scrub_text  # re-exported for back-compat

CLEAN_DIR = Path.home() / "GitHub" / "caseledger" / "docs" / "clean"

# Legacy duplicate kept temporarily for any old callers; SUBS comes from patterns
_LEGACY_SUBS: list[tuple[re.Pattern, str]] = [
    # Case caption / number
    (re.compile(r"\b2024\s?[Dd]\s?00?6724\b"), "[Case No.]"),
    (re.compile(r"\bIRMO\s+Thorarinson\s*[/v.]\s*Atagan[;,]?\s*"), ""),
    (re.compile(r"\bIn re Marriage of[^.\n]{0,80}\bAtagan\b[^.\n]{0,40}", re.IGNORECASE), "In re the matter"),
    # County / venue
    (re.compile(r"Cook County Domestic Relations Division", re.IGNORECASE), "the trial court"),
    (re.compile(r"Cook County Circuit Court", re.IGNORECASE), "the trial court"),
    (re.compile(r"\bCook County\b", re.IGNORECASE), "the trial court"),
    # Judge / judicial actor names (must precede generic role replacement)
    (re.compile(r"\bJudge\s+Matthew\s+William\s+Jannusch\b", re.IGNORECASE), "the trial judge"),
    (re.compile(r"\bJudge\s+Jannusch\b", re.IGNORECASE), "the trial judge"),
    (re.compile(r"\bJannusch\b", re.IGNORECASE), "the trial judge"),
    # Opposing counsel firm names
    (re.compile(r"\bFitzpatrick\s+Tarara\s+Family\s+Law(\s*,?\s*LLC)?\b", re.IGNORECASE), "opposing counsel's firm"),
    (re.compile(r"\bAnnemarie\s+Tarara\b", re.IGNORECASE), "opposing lead counsel"),
    (re.compile(r"\bAnne\s+Marie\s+Tarara\b", re.IGNORECASE), "opposing lead counsel"),
    (re.compile(r"\bTarara\b"), "opposing lead counsel"),
    (re.compile(r"\bCora\s+Leeuwenburg\b", re.IGNORECASE), "opposing associate counsel"),
    (re.compile(r"\bLynnea\s+Ellis\b", re.IGNORECASE), "opposing paralegal"),
    (re.compile(r"\bLinda\s+Ellis\b", re.IGNORECASE), "opposing paralegal"),
    (re.compile(r"\bJohn\s+A\.?\s+Conniff\b", re.IGNORECASE), "prior counsel"),
    (re.compile(r"\bConniff\b"), "prior counsel"),
    # Employer
    (re.compile(r"\bEisler\s+Capital(\s+\(US\)\s+LP)?\b", re.IGNORECASE), "the prior employer"),
    (re.compile(r"\bEisler\b"), "the prior employer"),
    # Personal: party names. Order: full → first
    (re.compile(r"\bJoel\s+Thorarinson\b"), "the petitioner"),
    (re.compile(r"\bHeather\s+Kim\s+Atagan\b", re.IGNORECASE), "the respondent"),
    (re.compile(r"\bHeather\s+Atagan\b", re.IGNORECASE), "the respondent"),
    (re.compile(r"\bHEATHER\b"), "the respondent"),
    (re.compile(r"\bJOEL\b"), "the petitioner"),
    (re.compile(r"\bHeather\b", re.IGNORECASE), "the respondent"),
    (re.compile(r"\bJoel\b"), "the petitioner"),
    (re.compile(r"\bAtagan\b", re.IGNORECASE), "the respondent"),
    (re.compile(r"\bThorarinson\b", re.IGNORECASE), "the petitioner"),
    # Hertz-specific (consumer collection defense pattern)
    (re.compile(r"\bHertz\s+Corporation\b"), "the rental car carrier"),
    (re.compile(r"\bHertz\s+v\.\s+Uhlig\b"), "the rental car suit"),
    (re.compile(r"\bv\.\s+Hertz\b"), "v. the rental car carrier"),
    (re.compile(r"\bHertz\b"), "the rental car carrier"),
    (re.compile(r"\bUhlig\b"), "the defendant"),
    # Dollar amounts with cents → placeholder (preserves order-of-magnitude in text)
    (re.compile(r"\$([\d,]+)\.\d{2}"), r"$\1.XX"),
    # eFileIL envelope ids → placeholder
    (re.compile(r"\bEnvelope\s+\d{6,9}\b", re.IGNORECASE), "Envelope [#]"),
    # Specific dates clearly tied to facts of the case can stay; the wording
    # around them is what carries the personal markers.
]

# Phrases that indicate the file is essentially a case-strategy doc — flag
# these for manual review rather than automatic abstraction.
HEAVY_FLAGS: list[re.Pattern] = [
    re.compile(r"VERIFIED PETITION", re.IGNORECASE),
    re.compile(r"PETITIONER/COUNTER-RESPONDENT", re.IGNORECASE),
    re.compile(r"RESPONDENT/COUNTER-PETITIONER", re.IGNORECASE),
    re.compile(r"hereby certifies", re.IGNORECASE),
]


def scrub_file(path: Path, *, concept_id: str | None = None, force: bool = False) -> Path | None:
    """Scrub a single .md and write the clean copy. Returns the output path."""
    if not path.exists():
        print(f"  skip (missing): {path}")
        return None

    post = frontmatter.load(str(path))
    meta = dict(post.metadata or {})
    cid = concept_id or meta.get("concept_id") or path.stem

    # Detect heavy case-strategy docs that should be manually reviewed
    text = post.content
    heavy_hits = [pat.pattern for pat in HEAVY_FLAGS if pat.search(text)]
    if heavy_hits and not force:
        print(f"  HEAVY (skip without --force): {cid}")
        print(f"    flags: {heavy_hits}")
        return None

    scrubbed, n = scrub_text(text)
    if n == 0:
        print(f"  no changes: {cid}")
        # Still write the clean copy with proper frontmatter so re-ingest is consistent
    else:
        print(f"  scrubbed {cid}: {n} substitutions")

    # Build clean frontmatter (force case_id=universal, abstraction_level=fully-abstract)
    meta["concept_id"] = cid
    meta["doc_type"] = meta.get("doc_type", "algorithm")
    meta["case_id"] = "universal"
    meta["applicable_cases"] = meta.get("applicable_cases", ["universal"])
    meta["abstraction_level"] = "fully-abstract"

    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    out_path = CLEAN_DIR / f"{cid}.md"
    post.content = scrubbed
    post.metadata = meta
    out_path.write_text(frontmatter.dumps(post), encoding="utf-8")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+", help="(concept_id=source_path) pairs OR plain source paths")
    parser.add_argument("--force", action="store_true", help="Scrub heavy case-strategy docs anyway")
    args = parser.parse_args()

    outputs = []
    for arg in args.inputs:
        if "=" in arg:
            cid, src = arg.split("=", 1)
        else:
            cid, src = None, arg
        path = Path(src).expanduser()
        if cid is None:
            cid = path.stem
        out = scrub_file(path, concept_id=cid, force=args.force)
        if out:
            outputs.append(out)

    print(f"\nWrote {len(outputs)} clean file(s) to {CLEAN_DIR}/")
    if outputs:
        print("Re-ingest:")
        print("  uv run python scripts/update_concept.py \\")
        for o in outputs:
            print(f"    {o}{' \\' if o != outputs[-1] else ''}")


if __name__ == "__main__":
    main()
