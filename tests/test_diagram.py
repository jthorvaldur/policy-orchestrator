"""Tests for devctl diagram command.

Run with: uv run pytest tests/test_diagram.py -v
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Make scripts/ importable
REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import diagram as diagram_mod


# ── helpers ────────────────────────────────────────────────────────────────────

FAKE_MERMAID_RESPONSE = """\
## Summary

policy-orchestrator is a Python control plane CLI that manages multiple repos
via a `devctl` command with subcommands for auditing, searching, and deploying.

## System Overview

```mermaid
flowchart TD
    CLI[devctl CLI] --> Repos[Repo Management]
    CLI --> Data[Data / Vector DB]
    CLI --> Pages[GitHub Pages]
    CLI --> Facts[Fact Registry]
    Repos --> Registry[(repos.yaml)]
    Data --> Qdrant[(Qdrant :6333)]
    Facts --> Qdrant
```

## Data Flow

```mermaid
flowchart LR
    Source[Source Repos] -->|embed| Qdrant[(Qdrant)]
    Qdrant -->|search| CLI[devctl search]
    CLI -->|results| User
```

## CLI Command Tree

```mermaid
flowchart TD
    devctl --> status
    devctl --> list
    devctl --> search
    devctl --> diagram
    devctl --> health
    devctl --> embed
```

## Module Dependencies

```mermaid
flowchart TD
    cli[cli.py] --> diagram_script[scripts/diagram.py]
    cli --> search_unified[scripts/search_unified.py]
    cli --> repo_status[scripts/repo_status.py]
```
"""


def _make_mock_urlopen(response_body: str):
    """Return a context-manager mock that mimics urllib.request.urlopen."""
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps({
        "content": [{"type": "text", "text": response_body}],
        "model": "claude-haiku-4-5",
        "stop_reason": "end_turn",
    }).encode()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


# ── tests ──────────────────────────────────────────────────────────────────────

class TestScanRepo:
    """_scan_repo should collect metadata from an existing repo."""

    def test_scans_policy_orchestrator(self):
        info = diagram_mod._scan_repo(REPO_ROOT)
        assert info["name"]  # has a name
        assert "python" in info["language"].lower()
        assert info["tree"]  # has directory tree
        assert info["py_files"]  # has Python files

    def test_scans_control_yaml(self):
        info = diagram_mod._scan_repo(REPO_ROOT)
        assert "policy-orchestrator" in info["control_yaml"]

    def test_handles_missing_optional_files(self, tmp_path):
        """Should not raise if INTENT.md / README.md / manifest are absent."""
        # tmp_path is a bare directory — no .control, no README, no manifest
        info = diagram_mod._scan_repo(tmp_path)
        assert info["control_yaml"] == ""
        assert info["intent_md"] == ""
        assert info["readme_md"] == ""


class TestBuildPrompt:
    """_build_prompt should produce a prompt that's within the size cap."""

    def test_prompt_under_8000_chars(self):
        info = diagram_mod._scan_repo(REPO_ROOT)
        prompt = diagram_mod._build_prompt(info)
        assert len(prompt) <= 8000, f"Prompt too large: {len(prompt)} chars"

    def test_prompt_contains_repo_name(self):
        info = diagram_mod._scan_repo(REPO_ROOT)
        prompt = diagram_mod._build_prompt(info)
        assert "policy-orchestrator" in prompt

    def test_prompt_contains_mermaid_instruction(self):
        info = diagram_mod._scan_repo(REPO_ROOT)
        prompt = diagram_mod._build_prompt(info)
        assert "Mermaid" in prompt or "mermaid" in prompt


class TestDiagramDryRun:
    """Integration: run diagram on policy-orchestrator itself without --commit."""

    def test_diagram_dry_run(self, tmp_path):
        """Diagram the policy-orchestrator repo, write to a temp docs/ dir, no commit.

        Mocks the Anthropic API call so the test is hermetic and free.
        The output file must:
          - exist at docs/architecture.md under the repo
          - contain ```mermaid fences
          - contain 'flowchart' or 'graph' (valid Mermaid diagram types)
        """
        # We write to tmp_path, not the real repo, to keep tests clean
        # Copy the .control/repo.yaml and INTENT.md into tmp_path so scanning works
        import shutil

        for src_name in [".control", "INTENT.md", "README.md", "pyproject.toml"]:
            src = REPO_ROOT / src_name
            if src.exists():
                dst = tmp_path / src_name
                if src.is_dir():
                    shutil.copytree(src, dst)
                else:
                    shutil.copy2(src, dst)

        # Copy a few source files so the tree and py_files are populated
        src_dir = REPO_ROOT / "src"
        if src_dir.exists():
            shutil.copytree(src_dir, tmp_path / "src")

        mock_resp = _make_mock_urlopen(FAKE_MERMAID_RESPONSE)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            out_path = diagram_mod.diagram_repo(
                repo_path=tmp_path,
                model="claude-haiku-4-5",
                commit=False,
                api_key="sk-fake-key-for-test",
                verbose=False,
            )

        assert out_path.exists(), f"Output file not created: {out_path}"
        content = out_path.read_text()

        # Must have Mermaid fences
        assert "```mermaid" in content, "Output missing ```mermaid fences"

        # Must have at least one valid Mermaid diagram type
        has_flowchart = "flowchart" in content
        has_graph = content.count("\ngraph ") > 0 or content.count("graph TD") > 0 or content.count("graph LR") > 0
        assert has_flowchart or has_graph, (
            "Output does not contain 'flowchart' or 'graph' Mermaid syntax"
        )

        # Must have the auto-generated header
        assert "AUTO-GENERATED by `devctl diagram`" in content

    def test_diagram_dry_run_real_api(self, tmp_path):
        """Same as above but uses the live Anthropic API (skipped if key absent)."""
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            pytest.skip("ANTHROPIC_API_KEY not set — skipping live API test")

        import shutil

        for src_name in [".control", "INTENT.md", "README.md", "pyproject.toml"]:
            src = REPO_ROOT / src_name
            if src.exists():
                dst = tmp_path / src_name
                if src.is_dir():
                    shutil.copytree(src, dst)
                else:
                    shutil.copy2(src, dst)

        src_dir = REPO_ROOT / "src"
        if src_dir.exists():
            shutil.copytree(src_dir, tmp_path / "src")

        out_path = diagram_mod.diagram_repo(
            repo_path=tmp_path,
            model="claude-haiku-4-5",
            commit=False,
            api_key=api_key,
            verbose=True,
        )

        assert out_path.exists()
        content = out_path.read_text()
        assert "```mermaid" in content
        assert "flowchart" in content or "graph" in content


class TestWriteDiagram:
    """_write_diagram should create docs/architecture.md with the header."""

    def test_creates_docs_dir(self, tmp_path):
        path = diagram_mod._write_diagram(tmp_path, "some content", "myrepo", "claude-haiku-4-5")
        assert path == tmp_path / "docs" / "architecture.md"
        assert path.exists()

    def test_header_present(self, tmp_path):
        path = diagram_mod._write_diagram(tmp_path, "body text", "myrepo", "claude-haiku-4-5")
        content = path.read_text()
        assert "AUTO-GENERATED by `devctl diagram`" in content
        assert "myrepo" in content
        assert "body text" in content

    def test_overwrites_existing(self, tmp_path):
        (tmp_path / "docs").mkdir()
        existing = tmp_path / "docs" / "architecture.md"
        existing.write_text("old content")
        diagram_mod._write_diagram(tmp_path, "new content", "myrepo", "claude-haiku-4-5")
        assert "new content" in existing.read_text()
        assert "old content" not in existing.read_text()


class TestCallClaude:
    """_call_claude should parse the Anthropic response format correctly."""

    def test_returns_text_content(self):
        mock_resp = _make_mock_urlopen("Hello, world!")
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = diagram_mod._call_claude("test prompt", "claude-haiku-4-5", "sk-fake")
        assert result == "Hello, world!"

    def test_raises_on_http_error(self):
        with patch("urllib.request.urlopen",
                   side_effect=urllib.error.HTTPError(
                       url="", code=401, msg="Unauthorized",
                       hdrs=None, fp=None,
                   )):
            # Patch the read() on HTTPError since we constructed it without fp
            with pytest.raises(RuntimeError, match="401"):
                diagram_mod._call_claude("test", "claude-haiku-4-5", "bad-key")
