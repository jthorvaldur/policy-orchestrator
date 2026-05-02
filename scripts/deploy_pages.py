#!/usr/bin/env python3
"""Deploy encrypted HTML pages from source repos to jthorvaldur.github.io.

Reads registries/pages.yaml for section definitions. Encrypts source HTML
with AES-256-GCM and writes to the Pages hub repo.

Usage:
    python scripts/deploy_pages.py                      # deploy all sections
    python scripts/deploy_pages.py --section=energy_texas  # deploy one section
    python scripts/deploy_pages.py --pending             # deploy pending sections too
    python scripts/deploy_pages.py --dry-run             # show what would happen
    python scripts/deploy_pages.py --push                # commit + push the hub repo
    python scripts/deploy_pages.py --verify              # verify encrypted pages decrypt ok
    python scripts/deploy_pages.py --auto                # auto-detect section from cwd
"""

import os
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent
REGISTRIES = ROOT / "registries"
ENCRYPT_TOOL = Path.home() / "GitHub" / "contacts" / "tools" / "encrypt_page.py"
HUB_REPO = Path.home() / "GitHub" / "jthorvaldur.github.io"


def load_registry():
    with open(REGISTRIES / "pages.yaml") as f:
        return yaml.safe_load(f)


def get_encrypt_fn():
    """Import the encrypt_html function from contacts/tools/encrypt_page.py."""
    if not ENCRYPT_TOOL.exists():
        print(f"  ERROR: encrypt tool not found at {ENCRYPT_TOOL}")
        sys.exit(1)
    # Add to path and import
    sys.path.insert(0, str(ENCRYPT_TOOL.parent))
    from encrypt_page import encrypt_html
    return encrypt_html


def resolve_source_dir(section):
    """Get the absolute path to the source directory."""
    repo_name = section.get("source_repo", "")
    source_dir = section.get("source_dir", "")
    repo_path = Path.home() / "GitHub" / repo_name
    return repo_path / source_dir


def resolve_target_dir(section):
    """Get the absolute path to the target directory in the hub repo."""
    target_dir = section.get("target_dir", "")
    return HUB_REPO / target_dir


def parse_page_mapping(page_entry):
    """Parse 'source.html -> target.html' or plain 'file.html'."""
    if isinstance(page_entry, str) and " -> " in page_entry:
        src, tgt = page_entry.split(" -> ", 1)
        return src.strip(), tgt.strip()
    return page_entry.strip(), page_entry.strip()


def deploy_section(name, section, encrypt_fn, dry_run=False, verify=False):
    """Deploy one section. Returns count of pages deployed."""
    encryption = section.get("encryption", "none")
    password_env = section.get("password_env", "")
    session_key = section.get("session_key", "_cp")

    source_dir = resolve_source_dir(section)
    target_dir = resolve_target_dir(section)

    if not source_dir.exists():
        print(f"    SKIP — source dir not found: {source_dir}")
        return 0

    # Get password
    password = ""
    if encryption != "none" and password_env:
        password = os.environ.get(password_env, "")
        if not password:
            print(f"    ERROR — {password_env} not set")
            return 0

    # Get page list
    pages = section.get("pages", [])
    if not pages:
        # Auto-discover HTML files
        pages = [f.name for f in sorted(source_dir.glob("*.html"))]

    # Copy supporting assets (CSS, JS, images) — unencrypted
    asset_exts = {".css", ".js", ".png", ".jpg", ".jpeg", ".svg", ".gif", ".ico", ".woff", ".woff2"}
    for asset in source_dir.iterdir():
        if asset.suffix.lower() in asset_exts and asset.is_file():
            tgt_asset = target_dir / asset.name
            if dry_run:
                print(f"    ASSET {asset.name} -> {tgt_asset.relative_to(HUB_REPO)}")
            else:
                tgt_asset.parent.mkdir(parents=True, exist_ok=True)
                import shutil
                shutil.copy2(asset, tgt_asset)
                print(f"    ASSET {asset.name} -> {tgt_asset.relative_to(HUB_REPO)}")

    deployed = 0
    for entry in pages:
        src_name, tgt_name = parse_page_mapping(entry)
        src_path = source_dir / src_name
        tgt_path = target_dir / tgt_name

        if not src_path.exists():
            print(f"    MISS  {src_name} — not found")
            continue

        if dry_run:
            print(f"    WOULD {src_name} -> {tgt_path.relative_to(HUB_REPO)}")
            deployed += 1
            continue

        html = src_path.read_text(encoding="utf-8")

        if encryption != "none" and password:
            # Encrypt with the session key and section title baked in
            title = section.get("title", "Private Page")
            encrypted = encrypt_with_session_key(encrypt_fn, html, password, session_key, title)
            tgt_path.parent.mkdir(parents=True, exist_ok=True)
            tgt_path.write_text(encrypted, encoding="utf-8")

            if verify:
                # Verify by decrypting
                ok = verify_decryption(tgt_path, password)
                status = "OK" if ok else "VERIFY FAILED"
                print(f"    {status}  {src_name} -> {tgt_path.relative_to(HUB_REPO)}")
            else:
                print(f"    DONE  {src_name} -> {tgt_path.relative_to(HUB_REPO)}")
        else:
            # No encryption — copy as-is
            tgt_path.parent.mkdir(parents=True, exist_ok=True)
            tgt_path.write_text(html, encoding="utf-8")
            print(f"    COPY  {src_name} -> {tgt_path.relative_to(HUB_REPO)}")

        deployed += 1

    return deployed


def encrypt_with_session_key(encrypt_fn, html, password, session_key, title="Protected Page"):
    """Encrypt HTML and patch the session key and title in the output."""
    encrypted = encrypt_fn(html, password, title=title)
    # Replace the hardcoded session key '_cp' with the section's session key
    if session_key != "_cp":
        encrypted = encrypted.replace(
            'sessionStorage.setItem("_cp"',
            f'sessionStorage.setItem("{session_key}"',
        )
        encrypted = encrypted.replace(
            'sessionStorage.getItem("_cp")',
            f'sessionStorage.getItem("{session_key}")',
        )
        encrypted = encrypted.replace(
            'sessionStorage.removeItem("_cp")',
            f'sessionStorage.removeItem("{session_key}")',
        )
    return encrypted


def verify_decryption(encrypted_path, password):
    """Verify an encrypted page can be decrypted."""
    import base64
    import hashlib
    import re

    html = encrypted_path.read_text(encoding="utf-8")
    try:
        salt_b64 = re.search(r'const SALT = "([^"]+)"', html).group(1)
        iv_b64 = re.search(r'const IV = "([^"]+)"', html).group(1)
        ct_b64 = re.search(r'const CT = "([^"]+)"', html).group(1)
    except AttributeError:
        return False

    salt = base64.b64decode(salt_b64)
    iv = base64.b64decode(iv_b64)
    ct = base64.b64decode(ct_b64)
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000, dklen=32)

    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        aesgcm = AESGCM(key)
        plaintext = aesgcm.decrypt(iv, ct, None)
        return b"<!DOCTYPE" in plaintext or b"<html" in plaintext
    except Exception:
        return False


def detect_section_from_cwd(sections):
    """Find the section matching the current working directory."""
    cwd = Path.cwd()
    repo_name = cwd.name

    # Also check if we're inside a repo (e.g. in a subdirectory)
    for parent in [cwd] + list(cwd.parents):
        if (parent / ".git").exists():
            repo_name = parent.name
            break

    for name, section in sections.items():
        if section.get("source_repo") == repo_name:
            return name
    return None


def main():
    data = load_registry()
    sections = data.get("sections", {})
    pending = data.get("pending", {})

    # Parse args
    filter_section = None
    dry_run = False
    push = False
    include_pending = False
    verify = False
    auto = False
    for arg in sys.argv[1:]:
        if arg.startswith("--section="):
            filter_section = arg.split("=", 1)[1]
        elif arg == "--dry-run":
            dry_run = True
        elif arg == "--push":
            push = True
        elif arg == "--pending":
            include_pending = True
        elif arg == "--verify":
            verify = True
        elif arg == "--auto":
            auto = True

    # Auto-detect section from cwd
    if auto and not filter_section:
        all_for_detect = {**sections, **pending}
        detected = detect_section_from_cwd(all_for_detect)
        if detected:
            filter_section = detected
            # Auto-include pending if the detected section is in pending
            if detected in pending:
                include_pending = True
            print(f"  Auto-detected: {detected}")
        else:
            cwd_name = Path.cwd().name
            print(f"  No section found for repo '{cwd_name}' in pages.yaml")
            sys.exit(1)

    # Merge pending if requested
    all_sections = dict(sections)
    if include_pending or auto:
        all_sections.update(pending)

    # Load encrypt function
    encrypt_fn = get_encrypt_fn()

    total = 0
    for name, section in all_sections.items():
        if filter_section and name != filter_section:
            continue

        # Skip non-encryptable sections (e.g. bulldogs uses GitHub Actions)
        deploy_script = section.get("deploy_script", "")
        if ".github/workflows" in deploy_script:
            continue

        print(f"\n  {name} ({section.get('source_repo', '?')} -> {section.get('target_dir', '?')})")
        count = deploy_section(name, section, encrypt_fn, dry_run=dry_run, verify=verify)
        total += count

    action = "Would deploy" if dry_run else "Deployed"
    print(f"\n  {action}: {total} pages")

    if push and not dry_run and total > 0:
        import subprocess
        print(f"\n  Committing + pushing {HUB_REPO.name}...")
        subprocess.run(["git", "add", "-A", "."], cwd=HUB_REPO)
        subprocess.run(
            ["git", "commit", "-m", f"Deploy {total} pages (verified)"],
            cwd=HUB_REPO,
        )
        subprocess.run(["git", "push"], cwd=HUB_REPO)
        print("  Pushed.")


if __name__ == "__main__":
    main()
