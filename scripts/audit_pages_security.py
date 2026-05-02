#!/usr/bin/env python3
"""Audit GitHub Pages for encryption and security policy compliance.

Checks all rules in policies/hard/pages-encryption.yaml against
the deployed pages in jthorvaldur.github.io.

Usage:
    python scripts/audit_pages_security.py          # full audit
    python scripts/audit_pages_security.py --fix    # show fix commands
"""

import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

HUB = Path.home() / "GitHub" / "jthorvaldur.github.io"
R_DIR = HUB / "r"

# Names that indicate sensitive content
SENSITIVE_PATTERNS = [
    "cook6724", "thorarinson v", "hensgen", "conniff", "tarara",
    "atagan", "plaid_", "ssn", "social security",
    "bank account", "routing number",
]

# Files that are allowed to be unencrypted even with name matches
EXCEPTIONS = {
    "r/index.html", "r/qwl/index.html", "r/qwl/data/basis_map.html",
}

errors = 0
warnings = 0


def error(rule, msg):
    global errors
    errors += 1
    print(f"  [ERROR] {rule}: {msg}")


def warn(rule, msg):
    global warnings
    warnings += 1
    print(f"  [ WARN] {rule}: {msg}")


def info(rule, msg):
    print(f"  [ INFO] {rule}: {msg}")


def check_plaintext_sensitive():
    """R1: No plaintext sensitive content."""
    print("\n  R1: Plaintext sensitive content")
    count = 0
    for f in R_DIR.rglob("*.html"):
        if "_originals" in str(f):
            continue
        rel = str(f.relative_to(HUB))
        if rel in EXCEPTIONS:
            continue

        content = f.read_text(errors="ignore").lower()
        # Skip if encrypted
        if "const salt" in content and "const ct" in content:
            continue

        # Check for sensitive patterns
        matches = []
        for pattern in SENSITIVE_PATTERNS:
            if pattern in content:
                matches.append(pattern)

        if matches:
            error("R1", f"{rel} — unencrypted with sensitive refs: {', '.join(matches)}")
            count += 1

    if count == 0:
        info("R1", "All sensitive content is encrypted")


def check_hash_passwords():
    """R2: No URL hash password support."""
    print("\n  R2: URL hash password code")
    count = 0
    for f in R_DIR.rglob("*.html"):
        if "_originals" in str(f):
            continue
        content = f.read_text(errors="ignore")
        if "location.hash.length" in content:
            rel = str(f.relative_to(HUB))
            error("R2", f"{rel} — has location.hash password support")
            count += 1
    if count == 0:
        info("R2", "No pages have URL hash password code")


def check_unique_crypto():
    """R3: Unique salt and IV per page."""
    print("\n  R3: Unique salt/IV")
    seen_salts = defaultdict(list)
    for f in R_DIR.rglob("*.html"):
        if "_originals" in str(f):
            continue
        content = f.read_text(errors="ignore")
        salt_match = re.search(r'const SALT = "([^"]+)"', content)
        iv_match = re.search(r'const IV = "([^"]+)"', content)
        if salt_match and iv_match:
            key = f"{salt_match.group(1)}:{iv_match.group(1)}"
            seen_salts[key].append(str(f.relative_to(HUB)))

    dupes = {k: v for k, v in seen_salts.items() if len(v) > 1}
    if dupes:
        for key, files in dupes.items():
            error("R3", f"Duplicate salt+IV across: {', '.join(files)}")
    else:
        info("R3", f"All {len(seen_salts)} encrypted pages have unique salt/IV")


def check_session_storage():
    """R4: sessionStorage only, no localStorage."""
    print("\n  R4: Session storage only")
    count = 0
    for f in R_DIR.rglob("*.html"):
        if "_originals" in str(f):
            continue
        content = f.read_text(errors="ignore")
        if "localStorage.setItem" in content or "localStorage.getItem" in content:
            rel = str(f.relative_to(HUB))
            error("R4", f"{rel} — uses localStorage (should be sessionStorage)")
            count += 1
    if count == 0:
        info("R4", "No pages use localStorage")


def check_originals_in_git():
    """R5: _originals never committed."""
    print("\n  R5: _originals not in git")
    result = subprocess.run(
        ["git", "ls-files"], cwd=HUB, capture_output=True, text=True, timeout=10
    )
    originals = [f for f in result.stdout.strip().split("\n") if "_originals" in f]
    if originals:
        for f in originals:
            error("R5", f"_originals committed: {f}")
    else:
        info("R5", "_originals directory is clean (not tracked)")


def check_pbkdf2():
    """R8: PBKDF2 minimum 100K iterations."""
    print("\n  R8: PBKDF2 iterations")
    bad = 0
    for f in R_DIR.rglob("*.html"):
        if "_originals" in str(f):
            continue
        content = f.read_text(errors="ignore")
        iter_match = re.search(r"iterations:\s*(\d+)", content)
        if iter_match:
            iters = int(iter_match.group(1))
            if iters < 100000:
                rel = str(f.relative_to(HUB))
                error("R8", f"{rel} — PBKDF2 iterations={iters} (minimum 100000)")
                bad += 1
    if bad == 0:
        info("R8", "All encrypted pages use >= 100K PBKDF2 iterations")


def main():
    print(f"\n{'='*60}")
    print(f"  Pages Security Audit — {HUB.name}")
    print(f"{'='*60}")

    check_plaintext_sensitive()
    check_hash_passwords()
    check_unique_crypto()
    check_session_storage()
    check_originals_in_git()
    check_pbkdf2()

    print(f"\n{'='*60}")
    print(f"  Results: {errors} errors, {warnings} warnings")
    print(f"{'='*60}\n")

    if errors > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
