"""Deploy gate-orchestrator for the public algorithm catalog.

Pipeline:
  1. audit       (gate — abort on any contamination)
  2. build       (regenerate, filter to algorithm doc_type / case_id=universal)
  3. encrypt     (optional, off by default — audit gate already guarantees clean content)
  4. stage       (copy files to jthorvaldur.github.io/r/algos/)
  5. preview     (show git diff; do NOT commit/push without --confirm)
  6. push        (only with --confirm: git add, commit, push)

The deploy is intended to be shareable — the audit gate enforces that no chunk
contains personal markers (party names, case numbers, judge names, employer
names, dollar-cents amounts, case-specific emails). Encryption is therefore
opt-in (--encrypt) and only useful for backwards-compat with the older
filing_key convention used by case-coupled pages in /r/reports/.

Usage:
  # Dry run — preview without writing
  uv run python -m scripts.concepts.deploy --dry-run

  # Build + stage + preview (no commit)
  uv run python -m scripts.concepts.deploy

  # Build + commit + push (PUBLIC, plain HTML)
  uv run python -m scripts.concepts.deploy --confirm

  # Build + encrypt + push (legacy case-coupled mode)
  uv run python -m scripts.concepts.deploy --confirm --encrypt
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import audit as audit_module
from . import build_public

ROOT_POL = Path(__file__).resolve().parents[2]
GH_REPO = Path.home() / "GitHub" / "jthorvaldur.github.io"
TARGET_DIR = GH_REPO / "r" / "algos"
BUILD_DIR = ROOT_POL / "build" / "concepts_public"
PASSWORD_ENV = "JTHORVALDUR_LEGAL_PAGE_PASSWORD"

# Encrypt module sits in contacts repo per CLAUDE.md convention
ENCRYPT_TOOLS = Path.home() / "GitHub" / "contacts" / "tools"


def stage_audit() -> None:
    print("\n[1/6] AUDIT")
    report = audit_module.audit(include_findings=False)
    if "error" in report:
        print(f"  audit failed: {report['error']}", file=sys.stderr)
        sys.exit(2)
    if report["dirty"]:
        print(f"  ✗ {report['dirty_count']} contaminated. Aborting deploy.", file=sys.stderr)
        for d in report["dirty"][:10]:
            print(f"    {d['concept_id']}: {d['total_marker_hits']} markers", file=sys.stderr)
        sys.exit(1)
    print(f"  ✓ {report['clean_count']} algorithms clean.")


def stage_build() -> None:
    print("\n[2/6] BUILD")
    build_public.regenerate_in_place()
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    for name in ("algos_tool.html", "knowledge_map.html", "network_map.html"):
        src = Path.home() / "GitHub" / "div_legal" / "reports" / name
        dst = BUILD_DIR / name
        build_public.filter_html(src, dst)
        print(f"  built {dst.name}")
    (BUILD_DIR / "index.html").write_text(build_public._landing_html(), encoding="utf-8")
    print(f"  built index.html")


def stage_encrypt(do_encrypt: bool) -> list[Path]:
    """Return list of source paths to stage. Encrypted if do_encrypt; else plain."""
    if not do_encrypt:
        print("\n[3/6] ENCRYPT (skipped — public deploy)")
        names = ("algos_tool.html", "knowledge_map.html", "network_map.html", "index.html")
        return [BUILD_DIR / n for n in names]

    print("\n[3/6] ENCRYPT")
    sys.path.insert(0, str(ENCRYPT_TOOLS))
    from encrypt_page import encrypt_html  # type: ignore

    password = os.environ.get(PASSWORD_ENV)
    if not password:
        print(f"  ✗ ${PASSWORD_ENV} not set. Source ~/.oh-my-zsh/custom/keys.zsh first.", file=sys.stderr)
        sys.exit(3)

    encrypted_dir = BUILD_DIR / "encrypted"
    encrypted_dir.mkdir(parents=True, exist_ok=True)
    out = []
    for name in ("algos_tool.html", "knowledge_map.html", "network_map.html", "index.html"):
        src = BUILD_DIR / name
        if not src.exists():
            print(f"  ✗ missing build artifact: {src}", file=sys.stderr)
            sys.exit(4)
        plain = src.read_text(encoding="utf-8")
        enc = encrypt_html(plain, password, title=f"algos:{name}")
        enc = enc.replace('"_cp"', '"filing_key"')
        dst = encrypted_dir / name
        dst.write_text(enc, encoding="utf-8")
        print(f"  encrypted {name}: {len(plain)//1024} KB → {len(enc)//1024} KB")
        out.append(dst)
    return out


def stage_stage(files: list[Path], dry_run: bool) -> None:
    print("\n[4/6] STAGE")
    if dry_run:
        print(f"  (dry-run) would copy {len(files)} files to {TARGET_DIR}/")
        for f in files:
            print(f"    → {TARGET_DIR}/{f.name}")
        return
    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    for f in files:
        shutil.copy2(f, TARGET_DIR / f.name)
        print(f"  staged {TARGET_DIR}/{f.name}")


def stage_preview(dry_run: bool) -> None:
    print("\n[5/6] PREVIEW")
    if dry_run:
        print("  (dry-run) skipping git preview")
        return
    r = subprocess.run(["git", "-C", str(GH_REPO), "status", "--short"],
                       capture_output=True, text=True, check=True)
    if not r.stdout.strip():
        print("  (no changes — already deployed)")
        return
    print(r.stdout)
    r = subprocess.run(["git", "-C", str(GH_REPO), "diff", "--stat", "--", "r/algos/"],
                       capture_output=True, text=True, check=True)
    if r.stdout.strip():
        print(r.stdout)


def stage_push(confirm: bool, dry_run: bool, encrypted: bool) -> None:
    print("\n[6/6] PUSH")
    if dry_run:
        print("  (dry-run) skipping")
        return
    if not confirm:
        print("  (no --confirm flag) staged but NOT committed. Review then re-run with --confirm.")
        return
    subprocess.run(["git", "-C", str(GH_REPO), "add", "r/algos/"], check=True)
    suffix = " (encrypted)" if encrypted else " (public, audit-gated)"
    msg = f"Deploy algorithm catalog{suffix}"
    subprocess.run(["git", "-C", str(GH_REPO), "commit", "-m", msg], check=True)
    subprocess.run(["git", "-C", str(GH_REPO), "push"], check=True)
    print(f"  ✓ pushed to jthorvaldur.github.io{suffix}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Build locally; no staging or push")
    parser.add_argument("--confirm", action="store_true", help="Actually commit + push")
    parser.add_argument("--encrypt", action="store_true",
                        help="Encrypt with JTHORVALDUR_LEGAL_PAGE_PASSWORD (legacy, opt-in). "
                             "Default: public/plain, audit-gated.")
    args = parser.parse_args()

    stage_audit()
    stage_build()
    artifacts = stage_encrypt(do_encrypt=args.encrypt)
    stage_stage(artifacts, dry_run=args.dry_run)
    stage_preview(dry_run=args.dry_run)
    stage_push(confirm=args.confirm, dry_run=args.dry_run, encrypted=args.encrypt)


if __name__ == "__main__":
    main()
