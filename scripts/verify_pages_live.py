#!/usr/bin/env python3
"""Verify deployed GitHub Pages decrypt correctly via live HTTPS fetch.

Fetches each encrypted page from jthorvaldur.github.io, extracts the
AES-256-GCM parameters, decrypts with the correct password, and validates
the plaintext contains valid HTML.

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


def test_section(name, section, password, quick=False):
    """Test one section. Returns (passed, failed, skipped)."""
    target_dir = section.get("target_dir", "")
    pages = section.get("pages", [])

    if not pages:
        # Auto-discover from local source dir
        source_repo = section.get("source_repo", "")
        source_dir = section.get("source_dir", "")
        local_dir = Path.home() / "GitHub" / source_repo / source_dir
        if local_dir.exists():
            pages = sorted(f.name for f in local_dir.glob("*.html"))
        if not pages:
            return 0, 0, 1

    if quick:
        pages = pages[:1]

    passed = failed = 0
    for entry in pages:
        if " -> " in str(entry):
            _, tgt = entry.split(" -> ", 1)
        else:
            tgt = entry
        tgt = tgt.strip()

        url = f"{BASE_URL}/{target_dir}{tgt}"

        try:
            r = httpx.get(url, timeout=15.0, follow_redirects=True)
            if r.status_code != 200:
                print(f"    FAIL  {tgt} — HTTP {r.status_code}")
                failed += 1
                continue

            html = r.text
            title = check_login_title(html)
            skey = check_session_key(html)
            has_hash = check_hash_vuln(html)

            ok, reason = decrypt_page(html, password)

            issues = []
            if title != "Private Page":
                issues.append(f"title=\"{title}\"")
            if has_hash:
                issues.append("HAS URL HASH VULN")

            issue_str = f" [{', '.join(issues)}]" if issues else ""

            if ok:
                print(f"    OK    {tgt} (key={skey}){issue_str}")
                passed += 1
            else:
                print(f"    FAIL  {tgt} — {reason}{issue_str}")
                failed += 1

        except Exception as e:
            print(f"    ERR   {tgt} — {e}")
            failed += 1

        # Rate limit to not hammer GitHub Pages
        time.sleep(0.3)

    return passed, failed, 0


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

    # Map sections to their password env vars
    total_passed = total_failed = total_skipped = 0

    print(f"\n  Live Page Verification — {BASE_URL}")
    print(f"  {'='*60}\n")

    for name, section in all_sections.items():
        if filter_section and name != filter_section:
            continue

        encryption = section.get("encryption", "none")
        if encryption == "none":
            continue

        pw_env = section.get("password_env", "")
        password = os.environ.get(pw_env, "")
        if not password:
            print(f"  {name}: SKIP — {pw_env} not set")
            total_skipped += 1
            continue

        target = section.get("target_dir", "?")
        print(f"  {name} ({target})")

        p, f, s = test_section(name, section, password, quick=quick)
        total_passed += p
        total_failed += f
        total_skipped += s
        print()

    print(f"  {'='*60}")
    print(f"  Results: {total_passed} passed, {total_failed} failed, {total_skipped} skipped")
    print(f"  {'='*60}\n")

    if total_failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
