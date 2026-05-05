"""provenance — build lineage tracking for generated outputs.

Copy or symlink into any repo. Records what generated each output,
from what inputs, with what parameters, and how to recreate it.

Usage:
    from provenance import tracked_output, provenance_context

    # Decorator — auto-tracks function outputs
    @tracked_output(inputs=["sdata/index.json"], recreate_cmd="uv run generate")
    def generate_timelines(year: int) -> list[str]:
        ...
        return ["reports/timeline_2024.html"]

    # Context manager — for imperative scripts
    with provenance_context("out/dashboard.html", inputs=["data/merged.jsonl"]):
        build_dashboard(data, output)

Records are appended to {cwd}/.provenance/build.jsonl.
"""

from __future__ import annotations

import functools
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


def _detect_repo() -> str:
    """Detect repo name from cwd or git."""
    cwd = Path.cwd()
    for parent in [cwd] + list(cwd.parents):
        if (parent / ".git").exists():
            return parent.name
    return cwd.name


def _hash_file(path: str | Path) -> str:
    """SHA-256 hash of a file. Returns empty string if file doesn't exist."""
    p = Path(path)
    if not p.exists():
        return ""
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()[:16]}"


def _hash_inputs(inputs: list[str | Path]) -> dict[str, str]:
    """Hash all input files."""
    result = {}
    for inp in inputs:
        p = Path(inp)
        if p.exists():
            result[str(p)] = _hash_file(p)
        elif p.is_dir() if p.exists() else False:
            # Directory — hash file count + total size as proxy
            files = list(p.rglob("*"))
            total = sum(f.stat().st_size for f in files if f.is_file())
            result[str(p)] = f"dir:{len(files)}files:{total}bytes"
    return result


def _write_record(record: dict[str, Any]) -> Path:
    """Append a provenance record to .provenance/build.jsonl."""
    prov_dir = Path.cwd() / ".provenance"
    prov_dir.mkdir(exist_ok=True)
    log_file = prov_dir / "build.jsonl"
    with open(log_file, "a") as f:
        f.write(json.dumps(record, default=str) + "\n")
    return log_file


def _inject_html_provenance(output_path: Path, record: dict) -> None:
    """Inject provenance comment into HTML files."""
    if not output_path.suffix == ".html":
        return
    if not output_path.exists():
        return

    compact = {
        "generator": record.get("generator", ""),
        "repo": record.get("repo", ""),
        "timestamp": record.get("timestamp", ""),
        "inputs": record.get("inputs", []),
        "recreate": record.get("recreate_cmd", ""),
    }
    comment = f"\n<!-- provenance: {json.dumps(compact)} -->\n"

    content = output_path.read_text(encoding="utf-8")
    if "<!-- provenance:" in content:
        # Replace existing provenance comment
        import re
        content = re.sub(r"\n<!-- provenance: .+? -->\n", comment, content)
    elif "</body>" in content:
        content = content.replace("</body>", f"{comment}</body>")
    elif "</html>" in content:
        content = content.replace("</html>", f"{comment}</html>")
    else:
        content += comment

    output_path.write_text(content, encoding="utf-8")


def tracked_output(
    inputs: list[str] | None = None,
    recreate_cmd: str = "",
    inject_html: bool = True,
):
    """Decorator that tracks build provenance for a generator function.

    The decorated function should return a list of output file paths (str or Path),
    or a single path, or None (in which case outputs aren't hashed).

    Args:
        inputs: List of input file/directory paths to hash before execution.
        recreate_cmd: Shell command to recreate the outputs.
        inject_html: If True, inject provenance comment into HTML outputs.
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            repo = _detect_repo()
            input_list = inputs or []
            input_hashes = _hash_inputs(input_list)

            start = time.monotonic()
            result = func(*args, **kwargs)
            duration_ms = int((time.monotonic() - start) * 1000)

            # Normalize outputs
            outputs = []
            if isinstance(result, (str, Path)):
                outputs = [str(result)]
            elif isinstance(result, (list, tuple)):
                outputs = [str(p) for p in result]

            # Hash outputs
            output_hashes = {}
            for out in outputs:
                h = _hash_file(out)
                if h:
                    output_hashes[out] = h

            # Build record
            record = {
                "id": hashlib.md5(
                    f"{repo}:{func.__module__}:{func.__qualname__}:{datetime.now(timezone.utc).isoformat()}".encode()
                ).hexdigest()[:12],
                "repo": repo,
                "generator": f"{func.__module__}:{func.__qualname__}",
                "outputs": outputs,
                "output_hashes": output_hashes,
                "inputs": input_list,
                "input_hashes": input_hashes,
                "parameters": {k: str(v) for k, v in kwargs.items()},
                "args": [str(a) for a in args] if args else [],
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "duration_ms": duration_ms,
                "recreate_cmd": recreate_cmd,
                "items": len(outputs),
            }

            log_file = _write_record(record)

            # Inject provenance into HTML outputs
            if inject_html:
                for out in outputs:
                    _inject_html_provenance(Path(out), record)

            return result
        return wrapper
    return decorator


class provenance_context:
    """Context manager for tracking provenance of imperative generation scripts.

    Usage:
        with provenance_context("out/dashboard.html", inputs=["data/merged.jsonl"]):
            build_dashboard(data, output)
    """

    def __init__(
        self,
        output: str | Path | list[str | Path],
        inputs: list[str] | None = None,
        generator: str = "",
        recreate_cmd: str = "",
        inject_html: bool = True,
    ):
        self.outputs = [str(output)] if isinstance(output, (str, Path)) else [str(o) for o in output]
        self.inputs = inputs or []
        self.generator = generator
        self.recreate_cmd = recreate_cmd
        self.inject_html = inject_html
        self._start = 0.0

    def __enter__(self):
        self._start = time.monotonic()
        self._input_hashes = _hash_inputs(self.inputs)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            return False  # don't suppress exceptions

        duration_ms = int((time.monotonic() - self._start) * 1000)
        repo = _detect_repo()

        # Determine generator name from caller
        import inspect
        frame = inspect.stack()[1]
        generator = self.generator or f"{frame.filename}:{frame.function}"

        output_hashes = {}
        for out in self.outputs:
            h = _hash_file(out)
            if h:
                output_hashes[out] = h

        record = {
            "id": hashlib.md5(
                f"{repo}:{generator}:{datetime.now(timezone.utc).isoformat()}".encode()
            ).hexdigest()[:12],
            "repo": repo,
            "generator": generator,
            "outputs": self.outputs,
            "output_hashes": output_hashes,
            "inputs": self.inputs,
            "input_hashes": self._input_hashes,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "duration_ms": duration_ms,
            "recreate_cmd": self.recreate_cmd,
            "items": len(self.outputs),
        }

        _write_record(record)

        if self.inject_html:
            for out in self.outputs:
                _inject_html_provenance(Path(out), record)

        return False


def read_provenance(repo_path: str | Path | None = None) -> list[dict]:
    """Read all provenance records from a repo's .provenance/build.jsonl."""
    if repo_path is None:
        repo_path = Path.cwd()
    log_file = Path(repo_path) / ".provenance" / "build.jsonl"
    if not log_file.exists():
        return []
    records = []
    with open(log_file) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def find_provenance(output_path: str, repo_path: str | Path | None = None) -> dict | None:
    """Find the most recent provenance record for a given output path."""
    records = read_provenance(repo_path)
    for rec in reversed(records):
        if output_path in rec.get("outputs", []):
            return rec
    return None
