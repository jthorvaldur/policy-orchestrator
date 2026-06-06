"""devctl diagram — generate Mermaid architecture diagrams for a repo.

Called by `devctl diagram`. Reads .control/repo.yaml, scans the repo,
calls Claude API, writes docs/architecture.md.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

import yaml


# ── repo scanning ──────────────────────────────────────────────────────────────

def _read_file_safe(path: Path, max_chars: int = 2000) -> str:
    try:
        text = path.read_text(errors="replace")
        if len(text) > max_chars:
            text = text[:max_chars] + "\n... (truncated)"
        return text
    except Exception:
        return ""


def _scan_repo(repo_path: Path) -> dict:
    """Collect key facts about a repo for the diagram prompt.

    Returns a dict with keys: name, control_yaml, intent_md, readme_md,
    top_dirs, py_files, js_files, pyproject, package_json.
    Total size is capped so the combined prompt stays under 8000 chars.
    """
    info: dict = {}

    # .control/repo.yaml
    control_yaml_path = repo_path / ".control" / "repo.yaml"
    info["control_yaml"] = _read_file_safe(control_yaml_path, 1500) if control_yaml_path.exists() else ""

    # INTENT.md
    intent_path = repo_path / "INTENT.md"
    info["intent_md"] = _read_file_safe(intent_path, 2000) if intent_path.exists() else ""

    # README.md
    readme_path = repo_path / "README.md"
    info["readme_md"] = _read_file_safe(readme_path, 2000) if readme_path.exists() else ""

    # pyproject.toml or package.json (project manifest)
    manifest = ""
    for manifest_name in ["pyproject.toml", "package.json", "setup.cfg", "Cargo.toml"]:
        mpath = repo_path / manifest_name
        if mpath.exists():
            manifest = _read_file_safe(mpath, 1000)
            break
    info["manifest"] = manifest

    # Top-level directory structure (depth 2, excluding common noise)
    SKIP = {
        ".git", "__pycache__", "node_modules", ".venv", "venv", ".mypy_cache",
        ".ruff_cache", ".pytest_cache", "dist", "build", ".tox", "*.egg-info",
    }
    top_entries = []
    try:
        for entry in sorted(repo_path.iterdir()):
            if entry.name.startswith(".") and entry.name not in {".control", ".env.example"}:
                continue
            if entry.name in SKIP or entry.name.endswith(".egg-info"):
                continue
            if entry.is_dir():
                sub = [s.name for s in sorted(entry.iterdir())
                       if not s.name.startswith(".") and s.name not in SKIP][:8]
                top_entries.append(f"{entry.name}/  [{', '.join(sub)}]" if sub else f"{entry.name}/")
            else:
                top_entries.append(entry.name)
    except Exception:
        pass
    info["tree"] = "\n".join(top_entries[:40])

    # Python source files (names only, for the module graph)
    py_files = sorted(repo_path.rglob("*.py"))
    py_files = [p for p in py_files
                if not any(part in {".venv", "venv", "__pycache__", "node_modules", ".git", "dist", "build"}
                           for part in p.parts)]
    info["py_files"] = "\n".join(str(p.relative_to(repo_path)) for p in py_files[:60])

    # JS/TS source files
    js_files = []
    for pattern in ["*.js", "*.ts", "*.jsx", "*.tsx"]:
        js_files.extend(repo_path.rglob(pattern))
    js_files = [p for p in js_files
                if not any(part in {"node_modules", ".git", "dist", "build"}
                           for part in p.parts)]
    info["js_files"] = "\n".join(str(p.relative_to(repo_path)) for p in sorted(js_files)[:40])

    # Repo name from .control/repo.yaml or directory name
    info["name"] = repo_path.name
    if info["control_yaml"]:
        try:
            ctrl = yaml.safe_load(info["control_yaml"])
            info["name"] = ctrl.get("name", repo_path.name)
            info["language"] = ctrl.get("language", {}).get("primary", "unknown")
            info["category"] = ctrl.get("category", "unknown")
        except Exception:
            info["language"] = "unknown"
            info["category"] = "unknown"
    else:
        info["language"] = "unknown"
        info["category"] = "unknown"

    return info


def _build_prompt(info: dict) -> str:
    """Build a Claude prompt from repo scan data, staying under 8000 chars."""
    sections = [
        f"# Repo: {info['name']}\nLanguage: {info['language']}  Category: {info['category']}\n",
    ]
    if info["control_yaml"]:
        sections.append(f"## .control/repo.yaml\n```yaml\n{info['control_yaml']}\n```\n")
    if info["intent_md"]:
        sections.append(f"## INTENT.md\n{info['intent_md']}\n")
    if info["readme_md"]:
        sections.append(f"## README.md\n{info['readme_md']}\n")
    if info["manifest"]:
        sections.append(f"## Project manifest\n```\n{info['manifest']}\n```\n")
    if info["tree"]:
        sections.append(f"## Directory tree\n```\n{info['tree']}\n```\n")
    if info["py_files"]:
        sections.append(f"## Python source files\n```\n{info['py_files']}\n```\n")
    if info["js_files"]:
        sections.append(f"## JS/TS source files\n```\n{info['js_files']}\n```\n")

    combined = "\n".join(sections)

    instruction = (
        "You are an architecture documentation assistant. "
        "Based on the repo information below, generate a markdown file with Mermaid diagrams. "
        "Include ONLY diagrams that are accurate and supported by the evidence above — "
        "do NOT invent components or flows that are not present. "
        "Structure the output as follows:\n\n"
        "1. A brief one-paragraph summary (2-3 sentences).\n"
        "2. A `flowchart TD` system overview diagram showing the main components.\n"
        "3. A data flow diagram (`flowchart LR`) if there is meaningful data movement.\n"
        "4. A CLI command tree diagram (`flowchart TD`) if there are CLI commands.\n"
        "5. A module dependency graph (`flowchart TD`) if there are multiple source modules.\n\n"
        "Skip any diagram section that would be empty or made up. "
        "Use Mermaid syntax inside ```mermaid fences. "
        "Keep node labels short (under 30 chars). "
        "Output raw markdown only — no preamble, no explanation outside the document.\n\n"
        "---\n\n"
        "Repo information:\n\n"
    )
    # Hard cap: total prompt must stay under 8000 chars
    _trunc_suffix = "\n... (truncated)\n"
    max_content = 8000 - len(instruction) - len(_trunc_suffix)
    if len(combined) > max_content:
        combined = combined[:max_content] + _trunc_suffix

    return instruction + combined


# ── Claude API call ────────────────────────────────────────────────────────────

def _call_claude(prompt: str, model: str, api_key: str) -> str:
    """Call Anthropic Messages API via urllib. Returns the text content."""
    payload = json.dumps({
        "model": model,
        "max_tokens": 4096,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        raise RuntimeError(f"Anthropic API error {e.code}: {body}") from e

    # Extract text from response
    content = data.get("content", [])
    texts = [block["text"] for block in content if block.get("type") == "text"]
    if not texts:
        raise RuntimeError(f"No text in API response: {data}")
    return "\n".join(texts)


# ── writing + committing ───────────────────────────────────────────────────────

HEADER = """\
<!-- AUTO-GENERATED by `devctl diagram` — do not edit by hand.
     Re-generate: devctl diagram --repo . --commit
     Model: {model}
     Generated: {date}
-->

# Architecture: {name}

"""


def _write_diagram(repo_path: Path, content: str, name: str, model: str) -> Path:
    """Write docs/architecture.md and return the file path."""
    from datetime import date

    docs_dir = repo_path / "docs"
    docs_dir.mkdir(exist_ok=True)
    out_path = docs_dir / "architecture.md"

    header = HEADER.format(
        model=model,
        date=date.today().isoformat(),
        name=name,
    )
    out_path.write_text(header + content)
    return out_path


def _git_commit(repo_path: Path) -> tuple[bool, str]:
    """Stage and commit docs/architecture.md. Returns (success, message)."""
    rel = "docs/architecture.md"
    try:
        add = subprocess.run(
            ["git", "-C", str(repo_path), "add", rel],
            capture_output=True, text=True, timeout=10,
        )
        if add.returncode != 0:
            return False, f"git add failed: {add.stderr.strip()}"

        # Check if there's actually a change to commit
        diff = subprocess.run(
            ["git", "-C", str(repo_path), "diff", "--cached", "--name-only"],
            capture_output=True, text=True, timeout=10,
        )
        if not diff.stdout.strip():
            return True, "nothing to commit (docs/architecture.md unchanged)"

        commit = subprocess.run(
            ["git", "-C", str(repo_path), "commit", "-m",
             "docs: add mermaid architecture diagrams [devctl diagram]"],
            capture_output=True, text=True, timeout=15,
        )
        if commit.returncode != 0:
            return False, f"git commit failed: {commit.stderr.strip()}"
        return True, commit.stdout.strip()
    except Exception as e:
        return False, str(e)


# ── main entry point ───────────────────────────────────────────────────────────

def diagram_repo(
    repo_path: Path,
    model: str,
    commit: bool,
    api_key: str,
    verbose: bool = True,
) -> Path:
    """Generate architecture diagram for a single repo. Returns the output path."""
    C = {
        "reset": "\033[0m", "bold": "\033[1m", "dim": "\033[90m",
        "green": "\033[32m", "yellow": "\033[33m", "cyan": "\033[36m",
        "red": "\033[31m",
    }

    if not repo_path.exists():
        raise ValueError(f"Repo path does not exist: {repo_path}")

    if verbose:
        print(f"  {C['cyan']}scanning{C['reset']} {repo_path} ...")

    info = _scan_repo(repo_path)
    prompt = _build_prompt(info)

    if verbose:
        print(f"  {C['cyan']}calling{C['reset']} Claude ({model}) — prompt {len(prompt)} chars ...")

    content = _call_claude(prompt, model, api_key)
    out_path = _write_diagram(repo_path, content, info["name"], model)

    if verbose:
        print(f"  {C['green']}wrote{C['reset']} {out_path}  ({len(content)} chars)")

    if commit:
        ok, msg = _git_commit(repo_path)
        status = C["green"] if ok else C["red"]
        if verbose:
            print(f"  {status}commit{C['reset']}  {msg}")

    return out_path


# ── CLI entry (called by scripts/diagram.py or tests directly) ────────────────

def run(
    repo: Optional[str],
    all_repos: bool,
    model: str,
    commit: bool,
) -> None:
    """Top-level runner called from cli.py."""
    C = {
        "reset": "\033[0m", "bold": "\033[1m", "dim": "\033[90m",
        "green": "\033[32m", "yellow": "\033[33m", "cyan": "\033[36m",
        "red": "\033[31m",
    }

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print(f"  {C['red']}ANTHROPIC_API_KEY not set. Run: source ~/.oh-my-zsh/custom/keys.zsh{C['reset']}")
        sys.exit(1)

    repos_to_process: list[Path] = []

    if repo:
        repos_to_process.append(Path(repo).expanduser().resolve())
    elif all_repos:
        # Load from registries/repos.yaml
        registries_dir = Path(__file__).parent.parent / "registries"
        registry_path = registries_dir / "repos.yaml"
        if not registry_path.exists():
            print(f"  {C['red']}Registry not found: {registry_path}{C['reset']}")
            sys.exit(1)
        with open(registry_path) as f:
            registry = yaml.safe_load(f)
        github_dir = Path.home() / "GitHub"
        seen = set()
        for r in registry.get("repos", []):
            name = r.get("name", "")
            if name and name not in seen:
                seen.add(name)
                p = github_dir / name
                if p.exists():
                    repos_to_process.append(p)
    else:
        # Default: current working directory
        repos_to_process.append(Path.cwd())

    if not repos_to_process:
        print(f"  {C['yellow']}no repos to process{C['reset']}")
        return

    print(f"\n{C['bold']}  devctl diagram{C['reset']}  {C['dim']}{len(repos_to_process)} repo(s)  model={model}{C['reset']}\n")

    errors = []
    for rp in repos_to_process:
        try:
            diagram_repo(rp, model=model, commit=commit, api_key=api_key)
        except Exception as e:
            print(f"  {C['red']}error{C['reset']} {rp.name}: {e}")
            errors.append((rp.name, str(e)))

    print()
    if errors:
        print(f"  {C['red']}{len(errors)} error(s){C['reset']}")
        for name, msg in errors:
            print(f"    {name}: {msg}")
        sys.exit(1)
    else:
        print(f"  {C['green']}done{C['reset']}")
