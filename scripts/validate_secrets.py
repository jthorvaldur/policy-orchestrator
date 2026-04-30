#!/usr/bin/env python3
"""Validate that each registered repo has the API keys its profile requires.

Unlike secrets_check.py (which scans for leaked secrets in committed files),
this script checks the current shell environment against each repo's declared
secret profile in registries/secrets.schema.yaml.

Usage:
    python scripts/validate_secrets.py              # check all repos
    python scripts/validate_secrets.py --repo=d72   # check one repo
    python scripts/validate_secrets.py --live        # also ping endpoints
    python scripts/validate_secrets.py --keys-only   # just show key inventory
"""

import os
import sys
from pathlib import Path

import yaml

REGISTRY_DIR = Path(__file__).parent.parent / "registries"


def load_yaml(name: str) -> dict:
    with open(REGISTRY_DIR / name) as f:
        return yaml.safe_load(f)


def check_key_pattern(key_name: str, value: str, patterns: dict) -> str | None:
    """Return a warning message if the key value doesn't match its expected prefix."""
    expected_prefix = patterns.get(key_name, "")
    if not expected_prefix or not value:
        return None
    if not value.startswith(expected_prefix):
        return (
            f"prefix mismatch: expected '{expected_prefix}...' "
            f"but got '{value[:12]}...'"
        )
    return None


def check_live_ollama(url: str) -> bool:
    """Ping ollama endpoint."""
    try:
        import httpx
        r = httpx.get(f"{url}/api/tags", timeout=3.0)
        return r.status_code == 200
    except Exception:
        return False


def check_live_anthropic(key: str) -> bool:
    """Validate anthropic key with a minimal request."""
    try:
        import httpx
        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5",
                "max_tokens": 1,
                "messages": [{"role": "user", "content": "hi"}],
            },
            timeout=10.0,
        )
        return r.status_code == 200
    except Exception:
        return False


def check_live_openrouter(key: str) -> bool:
    """Validate openrouter key by checking models endpoint."""
    try:
        import httpx
        r = httpx.get(
            "https://openrouter.ai/api/v1/models",
            headers={"Authorization": f"Bearer {key}"},
            timeout=10.0,
        )
        return r.status_code == 200
    except Exception:
        return False


def print_key_inventory(schema: dict) -> None:
    """Print a table of all known keys and their current status."""
    patterns = schema.get("key_patterns", {})
    all_keys: set[str] = set()
    for profile in schema.get("profiles", {}).values():
        all_keys.update(profile.get("required", []))
        all_keys.update(profile.get("optional", []))

    # Add keys from patterns too
    all_keys.update(patterns.keys())

    print("\n  Key Inventory")
    print(f"  {'Key':<30} {'Status':<10} {'Prefix Check':<20} {'Value Preview'}")
    print(f"  {'-'*85}")

    for key in sorted(all_keys):
        value = os.environ.get(key, "")
        status = "SET" if value else "MISSING"
        preview = f"{value[:16]}..." if value else "-"
        pattern_warn = check_key_pattern(key, value, patterns)
        prefix_status = pattern_warn if pattern_warn else ("ok" if value else "-")
        print(f"  {key:<30} {status:<10} {prefix_status:<20} {preview}")


def validate_repo(
    repo_name: str,
    repo_req: dict,
    profiles: dict,
    patterns: dict,
    live: bool = False,
) -> list[dict]:
    """Validate one repo's secret requirements. Returns list of findings."""
    findings = []
    repo_profiles = repo_req.get("profiles", [])
    cloud_allowed = repo_req.get("cloud_allowed", True)

    if not repo_profiles:
        return findings

    # Collect all required and optional keys from profiles
    required_keys: set[str] = set()
    optional_keys: set[str] = set()

    for profile_name in repo_profiles:
        profile = profiles.get(profile_name)
        if not profile:
            findings.append({
                "level": "ERROR",
                "message": f"unknown profile '{profile_name}' referenced",
            })
            continue
        required_keys.update(profile.get("required", []))
        optional_keys.update(profile.get("optional", []))

    # Remove required from optional (if a key is required by one profile, don't report as optional)
    optional_keys -= required_keys

    # Check required keys
    for key in sorted(required_keys):
        value = os.environ.get(key, "")
        if not value:
            findings.append({
                "level": "ERROR",
                "message": f"required key {key} is not set (profiles: {repo_profiles})",
            })
        else:
            pattern_warn = check_key_pattern(key, value, patterns)
            if pattern_warn:
                findings.append({
                    "level": "WARN",
                    "message": f"{key}: {pattern_warn}",
                })

    # Check optional keys (info only)
    missing_optional = [k for k in sorted(optional_keys) if not os.environ.get(k, "")]
    if missing_optional:
        findings.append({
            "level": "INFO",
            "message": f"optional keys not set: {', '.join(missing_optional)}",
        })

    # Cloud policy check
    if not cloud_allowed:
        cloud_keys = {"ANTHROPIC_API_KEY", "OPENROUTER_API_KEY", "OPENAI_API_KEY", "VAST_API_KEY"}
        set_cloud = [k for k in cloud_keys if os.environ.get(k)]
        if set_cloud:
            findings.append({
                "level": "INFO",
                "message": f"cloud_allowed=false but cloud keys available: {', '.join(set_cloud)} "
                           f"(router will enforce LEGAL_LOCAL_ONLY if set)",
            })

    # Live checks
    if live:
        ollama_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        if "OLLAMA_BASE_URL" in required_keys or "OLLAMA_BASE_URL" in optional_keys:
            if check_live_ollama(ollama_url):
                findings.append({"level": "INFO", "message": f"ollama reachable at {ollama_url}"})
            else:
                findings.append({"level": "WARN", "message": f"ollama NOT reachable at {ollama_url}"})

        if "ANTHROPIC_API_KEY" in required_keys and os.environ.get("ANTHROPIC_API_KEY"):
            if check_live_anthropic(os.environ["ANTHROPIC_API_KEY"]):
                findings.append({"level": "INFO", "message": "anthropic key validated (live)"})
            else:
                findings.append({"level": "ERROR", "message": "anthropic key REJECTED by API"})

        if "OPENROUTER_API_KEY" in required_keys and os.environ.get("OPENROUTER_API_KEY"):
            if check_live_openrouter(os.environ["OPENROUTER_API_KEY"]):
                findings.append({"level": "INFO", "message": "openrouter key validated (live)"})
            else:
                findings.append({"level": "ERROR", "message": "openrouter key REJECTED by API"})

    return findings


def main():
    schema = load_yaml("secrets.schema.yaml")
    profiles = schema.get("profiles", {})
    patterns = schema.get("key_patterns", {})
    repo_requirements = schema.get("repo_requirements", {})

    # Parse CLI args
    filter_repo = None
    live = False
    keys_only = False
    for arg in sys.argv[1:]:
        if arg.startswith("--repo="):
            filter_repo = arg.split("=", 1)[1]
        elif arg == "--live":
            live = True
        elif arg == "--keys-only":
            keys_only = True

    # Always show key inventory first
    print_key_inventory(schema)

    if keys_only:
        return

    print(f"\n  Repo Validation")
    print(f"  {'='*60}")

    error_count = 0
    warn_count = 0
    repos_checked = 0

    for repo_name, repo_req in sorted(repo_requirements.items()):
        if filter_repo and repo_name != filter_repo:
            continue

        findings = validate_repo(repo_name, repo_req, profiles, patterns, live)
        repos_checked += 1

        if not findings and not filter_repo:
            # Skip repos with no profiles and no findings
            if not repo_req.get("profiles"):
                continue

        profiles_str = ", ".join(repo_req.get("profiles", [])) or "none"
        cloud = "cloud=yes" if repo_req.get("cloud_allowed", True) else "cloud=NO"
        print(f"\n  {repo_name}  [{profiles_str}] [{cloud}]")

        if not findings:
            print(f"    all checks passed")
            continue

        print(f"  {'-'*50}")
        for f in findings:
            icon = {"ERROR": "ERROR", "WARN": " WARN", "INFO": " INFO"}[f["level"]]
            print(f"    [{icon}] {f['message']}")
            if f["level"] == "ERROR":
                error_count += 1
            elif f["level"] == "WARN":
                warn_count += 1

    print(f"\n--- Validate Secrets Summary ---")
    print(f"Repos checked: {repos_checked}")
    print(f"Errors: {error_count}  Warnings: {warn_count}")

    if error_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
