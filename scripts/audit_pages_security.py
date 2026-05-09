#!/usr/bin/env python3
"""Audit GitHub Pages for encryption and security policy compliance.

Checks all rules in policies/hard/pages-encryption.yaml against
the deployed pages in jthorvaldur.github.io.
"""

import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

HUB = Path.home() / "GitHub" / "jthorvaldur.github.io"
R_DIR = HUB / "r"

# ANSI
C = {
    "reset": "\033[0m", "bold": "\033[1m", "dim": "\033[90m",
    "green": "\033[32m", "yellow": "\033[33m", "red": "\033[31m",
    "cyan": "\033[36m",
}

# Patterns that indicate ACTUAL sensitive data (not just the word in educational context)
# These are regex patterns that match real PII, not discussions about PII
SENSITIVE_DATA_PATTERNS = [
    (r"\b\d{3}-\d{2}-\d{4}\b", "SSN pattern"),                  # actual SSN format
    (r"\b\d{9,12}\b(?=.*rout)", "routing number"),               # actual routing number
    (r"(?i)account\s*#?\s*\d{6,}", "account number"),            # actual account number
    (r"(?i)(?:password|passwd)\s*[:=]\s*['\"][^'\"]{8,}['\"]", "hardcoded password"),
]

# Name patterns that should NEVER appear in unencrypted pages
SENSITIVE_NAME_PATTERNS = [
    "case_ref", "party_a", "party_b", "atty_c", "atty_t", "atagan",
]

# Pages that are intentionally public and unencrypted
PUBLIC_PAGES = {
    "r/index.html",
    "r/legal-concepts.html",
    "r/legal-history.html",
    "r/control-plane.html",
    "r/site-dimensions.html",
    "r/sovereign/jurisdiction.html",
    "r/rights/natural.html",
    "r/influence/layers.html",
}

errors = 0
warnings = 0
checks = []


def record(level, rule, msg):
    global errors, warnings
    if level == "ERROR":
        errors += 1
    elif level == "WARN":
        warnings += 1
    checks.append({"level": level, "rule": rule, "message": msg})


def check_plaintext_sensitive():
    """R1: No actual PII in unencrypted pages."""
    for f in R_DIR.rglob("*.html"):
        if "_originals" in str(f):
            continue
        rel = str(f.relative_to(HUB))

        content = f.read_text(errors="ignore")
        content_lower = content.lower()

        # Skip encrypted pages
        if "const salt" in content_lower and "const ct" in content_lower:
            continue

        # Check for actual PII patterns (regex-based, not word matching)
        for pattern, label in SENSITIVE_DATA_PATTERNS:
            if re.search(pattern, content):
                record("ERROR", "R1", f"{rel} — contains {label}")

        # Check for redacted name patterns (these should never appear even in public pages)
        for name in SENSITIVE_NAME_PATTERNS:
            if name in content_lower:
                record("ERROR", "R1", f"{rel} — contains redacted identifier '{name}'")


def check_unencrypted_non_public():
    """R1b: Non-public pages must be encrypted."""
    for f in R_DIR.rglob("*.html"):
        if "_originals" in str(f):
            continue
        rel = str(f.relative_to(HUB))

        # Skip known public pages
        if rel in PUBLIC_PAGES:
            continue

        content = f.read_text(errors="ignore").lower()
        is_encrypted = "const salt" in content and "const ct" in content

        if not is_encrypted:
            # Check if it's in a section that should be encrypted
            parts = rel.split("/")
            if len(parts) >= 3:  # r/<section>/file.html
                section = parts[1]
                encrypted_sections = {"contacts", "concepts", "d72", "food-trust",
                                      "energy", "reports", "case", "dimensions"}
                if section in encrypted_sections:
                    record("ERROR", "R1b", f"{rel} — in encrypted section but not encrypted")


def check_hash_passwords():
    """R2: No URL hash password support."""
    for f in R_DIR.rglob("*.html"):
        if "_originals" in str(f):
            continue
        content = f.read_text(errors="ignore")
        if "location.hash.length" in content:
            rel = str(f.relative_to(HUB))
            record("ERROR", "R2", f"{rel} — has location.hash password support")


def check_unique_crypto():
    """R3: Unique salt and IV per page."""
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
            record("ERROR", "R3", f"duplicate salt+IV: {', '.join(files)}")

    return len(seen_salts)


def check_session_storage():
    """R4: sessionStorage only, no localStorage."""
    for f in R_DIR.rglob("*.html"):
        if "_originals" in str(f):
            continue
        content = f.read_text(errors="ignore")
        if "localStorage.setItem" in content or "localStorage.getItem" in content:
            rel = str(f.relative_to(HUB))
            record("ERROR", "R4", f"{rel} — uses localStorage")


def check_originals_in_git():
    """R5: _originals never committed."""
    result = subprocess.run(
        ["git", "ls-files"], cwd=HUB, capture_output=True, text=True, timeout=10
    )
    originals = [f for f in result.stdout.strip().split("\n") if "_originals" in f]
    if originals:
        for f in originals:
            record("ERROR", "R5", f"_originals committed: {f}")


def check_pbkdf2():
    """R8: PBKDF2 minimum 100K iterations."""
    for f in R_DIR.rglob("*.html"):
        if "_originals" in str(f):
            continue
        content = f.read_text(errors="ignore")
        iter_match = re.search(r"iterations:\s*(\d+)", content)
        if iter_match:
            iters = int(iter_match.group(1))
            if iters < 100000:
                rel = str(f.relative_to(HUB))
                record("ERROR", "R8", f"{rel} — PBKDF2 iterations={iters} (min 100K)")


def main():
    if not R_DIR.exists():
        print(f"\n  {C['red']}●{C['reset']} Pages directory not found: {R_DIR}")
        sys.exit(1)

    # Count pages
    all_html = [f for f in R_DIR.rglob("*.html") if "_originals" not in str(f)]
    encrypted = 0
    public = 0
    for f in all_html:
        content = f.read_text(errors="ignore").lower()
        if "const salt" in content and "const ct" in content:
            encrypted += 1
        else:
            public += 1

    # Run checks
    check_plaintext_sensitive()
    check_unencrypted_non_public()
    check_hash_passwords()
    encrypted_count = check_unique_crypto()
    check_session_storage()
    check_originals_in_git()
    check_pbkdf2()

    # Output
    print(f"\n{C['bold']}  devctl audit-pages{C['reset']}  {C['dim']}{len(all_html)} pages ({encrypted} encrypted, {public} public){C['reset']}\n")

    # Group by rule
    rules = {
        "R1": "Plaintext PII",
        "R1b": "Unencrypted sections",
        "R2": "Hash passwords",
        "R3": "Unique salt/IV",
        "R4": "Session storage",
        "R5": "Git originals",
        "R8": "PBKDF2 iterations",
    }

    error_checks = [c for c in checks if c["level"] == "ERROR"]
    warn_checks = [c for c in checks if c["level"] == "WARN"]

    if error_checks:
        for c in error_checks:
            print(f"  {C['red']}✗{C['reset']} {C['dim']}[{c['rule']}]{C['reset']} {c['message']}")

    if warn_checks:
        for c in warn_checks:
            print(f"  {C['yellow']}!{C['reset']} {C['dim']}[{c['rule']}]{C['reset']} {c['message']}")

    # Passing rules
    triggered_rules = {c["rule"] for c in checks}
    passing = [r for r in rules if r not in triggered_rules]
    if passing:
        pass_str = "  ".join(f"{C['dim']}{r}{C['reset']}" for r in passing)
        print(f"\n  {C['green']}●{C['reset']} passing: {pass_str}")

    # Summary
    print(f"\n  {'─' * 50}")
    parts = []
    if passing:
        parts.append(f"{C['green']}● {len(passing)} rules pass{C['reset']}")
    if warnings > 0:
        parts.append(f"{C['yellow']}● {warnings} warnings{C['reset']}")
    if errors > 0:
        parts.append(f"{C['red']}● {errors} errors{C['reset']}")
    else:
        parts.append(f"{C['green']}● 0 errors{C['reset']}")
    print(f"  {C['bold']}{encrypted_count} encrypted pages{C['reset']}  {'  '.join(parts)}")
    print()

    if errors > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
