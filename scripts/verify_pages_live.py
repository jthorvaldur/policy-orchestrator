#!/usr/bin/env python3
"""Verify deployed GitHub Pages decrypt correctly via live HTTPS fetch.

Fetches each encrypted page from jthorvaldur.github.io, extracts the
AES-256-GCM parameters, decrypts with the correct password, and validates
the plaintext contains valid HTML.

Public (unencrypted) pages are verified for HTTP 200 only.
Sections with redacted paths (CASE_REF) are skipped.

Usage:
    python scripts/verify_pages_live.py              # test all sections
    python scripts/verify_pages_live.py --section=energy_texas
    python scripts/verify_pages_live.py --quick      # one page per section
"""

import base64
import hashlib
import os
import re
import sys
import time
from pathlib import Path

import httpx
import yaml

REGISTRY = Path(__file__).parent.parent / "registries" / "pages.yaml"
BASE_URL = "https://jthorvaldur.github.io"

# ANSI colors — shared scheme with other devctl scripts
C = {
    "reset": "\033[0m", "bold": "\033[1m", "dim": "\033[90m",
    "green": "\033[32m", "yellow": "\033[33m", "red": "\033[31m",
    "cyan": "\033[36m",
}

# Sections whose pages are intentionally public (educational, no PII).
# These may have encryption: aes-256-gcm in pages.yaml (for future use)
# but their current HTML files are deployed unencrypted on purpose.
PUBLIC_SECTIONS = {"sovereign", "rights", "influence"}

# Pages known to be public within otherwise-encrypted sections
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


def load_registry():
    with open(REGISTRY) as f:
        return yaml.safe_load(f)


def decrypt_page(html: str, password: str) -> tuple[bool, str]:
    """Extract SALT/IV/CT from HTML, decrypt, return (ok, reason)."""
    try:
        salt_m = re.search(r'const SALT = "([^"]+)"', html)
        iv_m = re.search(r'const IV = "([^"]+)"', html)
        ct_m = re.search(r'const CT = "([^"]+)"', html)

        if not all([salt_m, iv_m, ct_m]):
            return False, "no crypto markers"

        salt = base64.b64decode(salt_m.group(1))
        iv = base64.b64decode(iv_m.group(1))
        ct = base64.b64decode(ct_m.group(1))

        key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000, dklen=32)

        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        plaintext = AESGCM(key).decrypt(iv, ct, None)

        if b"<" not in plaintext[:100]:
            return False, "decrypted but no HTML found"

        # Check for double encryption (decrypted content is another login page)
        text = plaintext.decode("utf-8", errors="ignore")
        if "const SALT" in text and "const CT" in text:
            return False, "DOUBLE ENCRYPTED — decrypted content is another login page"

        return True, "ok"

    except Exception as e:
        return False, str(e)


def check_login_title(html: str) -> str:
    """Extract the login page title."""
    m = re.search(r"<h1>([^<]+)</h1>", html)
    return m.group(1) if m else "?"


def check_session_key(html: str) -> str:
    """Extract the sessionStorage key."""
    m = re.search(r'sessionStorage\.setItem\("([^"]+)"', html)
    return m.group(1) if m else "?"


def check_hash_vuln(html: str) -> bool:
    """Check if URL hash password code is present."""
    return "location.hash.length" in html


def is_page_public(section_name: str, section_encryption: str, target_dir: str, page_filename: str) -> bool:
    """Check if a page is intentionally public (unencrypted)."""
    # Sections with no encryption are fully public
    if section_encryption == "none":
        return True
    # Known educational sections deployed without encryption
    if section_name in PUBLIC_SECTIONS:
        return True
    # Check against the explicit public pages list
    rel_path = f"{target_dir}{page_filename}".lstrip("/")
    return rel_path in PUBLIC_PAGES


def test_section(name, section, password, quick=False):
    """Test one section. Returns (passed, warned, failed, skipped, details).

    details is a list of (icon, line) tuples for display.
    """
    target_dir = section.get("target_dir", "")
    pages = section.get("pages", [])
    encryption = section.get("encryption", "none")
    details = []

    if not pages:
        # Auto-discover from local source dir
        source_repo = section.get("source_repo", "")
        source_dir = section.get("source_dir", "")
        local_dir = Path.home() / "GitHub" / source_repo / source_dir
        if local_dir.exists():
            pages = sorted(f.name for f in local_dir.glob("*.html"))
        if not pages:
            details.append(("skip", f"{C['dim']}no pages found{C['reset']}"))
            return 0, 0, 0, 1, details

    if quick:
        pages = pages[:1]

    passed = warned = failed = 0
    for entry in pages:
        if " -> " in str(entry):
            _, tgt = entry.split(" -> ", 1)
        else:
            tgt = entry
        tgt = tgt.strip()

        page_public = is_page_public(name, encryption, target_dir, tgt)
        url = f"{BASE_URL}/{target_dir}{tgt}"

        try:
            r = httpx.get(url, timeout=15.0, follow_redirects=True)
            if r.status_code != 200:
                details.append(("fail", f"{C['red']}✗{C['reset']} {tgt}  {C['dim']}HTTP {r.status_code}{C['reset']}"))
                failed += 1
                continue

            html = r.text

            # Public page — just verify it loaded
            if page_public:
                details.append(("pass", f"{C['green']}✓{C['reset']} {tgt}  {C['dim']}public (ok){C['reset']}"))
                passed += 1
                continue

            # Encrypted page — full crypto verification
            title = check_login_title(html)
            skey = check_session_key(html)
            has_hash = check_hash_vuln(html)

            ok, reason = decrypt_page(html, password)

            issues = []
            if title != "Private Page":
                issues.append(f"title=\"{title}\"")
            if has_hash:
                issues.append("HAS URL HASH VULN")

            issue_str = ""
            if issues:
                issue_str = f"  {C['yellow']}{', '.join(issues)}{C['reset']}"

            if ok:
                details.append(("pass", f"{C['green']}✓{C['reset']} {tgt}  {C['dim']}key={skey}{C['reset']}{issue_str}"))
                if issues:
                    warned += 1
                else:
                    passed += 1
            else:
                details.append(("fail", f"{C['red']}✗{C['reset']} {tgt}  {C['red']}{reason}{C['reset']}{issue_str}"))
                failed += 1

        except Exception as e:
            details.append(("fail", f"{C['red']}✗{C['reset']} {tgt}  {C['red']}{e}{C['reset']}"))
            failed += 1

        # Rate limit to not hammer GitHub Pages
        time.sleep(0.3)

    return passed, warned, failed, 0, details


def main():
    data = load_registry()
    sections = data.get("sections", {})
    pending = data.get("pending", {})
    all_sections = {**sections, **pending}

    # Parse args
    filter_section = None
    quick = False
    for arg in sys.argv[1:]:
        if arg.startswith("--section="):
            filter_section = arg.split("=", 1)[1]
        elif arg == "--quick":
            quick = True

    # Collect results for summary
    section_results = []  # (name, status, passed, warned, failed, skipped, details)

    section_count = 0
    for name in all_sections:
        if filter_section and name != filter_section:
            continue
        section_count += 1

    print(f"\n{C['bold']}  devctl verify-pages{C['reset']}  {C['dim']}{section_count} sections{C['reset']}\n")

    total_passed = total_warned = total_failed = total_skipped = 0
    section_pass = section_warn = section_fail = section_skip = 0

    for name, section in all_sections.items():
        if filter_section and name != filter_section:
            continue

        encryption = section.get("encryption", "none")
        target_dir = section.get("target_dir", "?")
        is_public_section = encryption == "none" or name in PUBLIC_SECTIONS

        # Skip sections with CASE_REF in the path (redacted references)
        if "CASE_REF" in target_dir:
            print(f"  {C['yellow']}●{C['reset']} {C['bold']}{name}{C['reset']}  {C['dim']}{target_dir}{C['reset']}")
            print(f"    {C['dim']}–{C['reset']} {C['dim']}skipped — redacted path (CASE_REF){C['reset']}")
            print()
            total_skipped += 1
            section_skip += 1
            continue

        # For non-public encrypted sections, check password
        if not is_public_section:
            pw_env = section.get("password_env", "")
            password = os.environ.get(pw_env, "")
            if not password:
                print(f"  {C['yellow']}●{C['reset']} {C['bold']}{name}{C['reset']}  {C['dim']}{target_dir}{C['reset']}")
                print(f"    {C['dim']}–{C['reset']} {C['dim']}skipped — {pw_env} not set{C['reset']}")
                print()
                total_skipped += 1
                section_skip += 1
                continue
        else:
            password = ""
            # Public sections with encryption key set — still try to get it
            pw_env = section.get("password_env", "")
            if pw_env:
                password = os.environ.get(pw_env, "")

        p, w, f, s, details = test_section(name, section, password, quick=quick)
        total_passed += p
        total_warned += w
        total_failed += f
        total_skipped += s

        # Section-level status
        if s > 0 and p == 0 and f == 0:
            icon = f"{C['yellow']}●{C['reset']}"
            section_skip += 1
        elif f > 0:
            icon = f"{C['red']}●{C['reset']}"
            section_fail += 1
        elif w > 0:
            icon = f"{C['yellow']}●{C['reset']}"
            section_warn += 1
        else:
            icon = f"{C['green']}●{C['reset']}"
            section_pass += 1

        print(f"  {icon} {C['bold']}{name}{C['reset']}  {C['dim']}{target_dir}{C['reset']}")
        for _, line in details:
            print(f"    {line}")
        print()

    # Summary
    print(f"  {'─' * 50}")
    parts = []
    if section_pass > 0:
        parts.append(f"{C['green']}● {section_pass} passed{C['reset']}")
    if section_warn > 0:
        parts.append(f"{C['yellow']}● {section_warn} warnings{C['reset']}")
    if section_fail > 0:
        parts.append(f"{C['red']}● {section_fail} failed{C['reset']}")
    if section_skip > 0:
        parts.append(f"{C['dim']}● {section_skip} skipped{C['reset']}")
    print(f"  {C['bold']}{section_count} sections{C['reset']}  {'  '.join(parts)}")
    print()

    if total_failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
