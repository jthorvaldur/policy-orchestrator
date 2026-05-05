"""profiler — operation timing and throughput tracking.

Copy or symlink into any repo. Records how fast each operation runs,
enables synthetic benchmarks, and projects costs at scale.

Usage:
    from profiler import timed_op, get_timings, compare_timings

    # Decorator
    @timed_op(category="embed", units="vectors")
    def embed_batch(texts: list[str]) -> list[list[float]]:
        ...  # profiler records duration + items/sec

    # Context manager
    with timed_op("vast_up", category="infra") as t:
        subprocess.run(["./scripts/vast_up.sh"])
        t.items = 1  # optional: set item count for throughput

    # Query timings
    timings = get_timings(category="embed")
"""

from __future__ import annotations

import functools
import json
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


def _write_timing(record: dict[str, Any]) -> None:
    """Append a timing record to .profiling/timings.jsonl."""
    prof_dir = Path.cwd() / ".profiling"
    prof_dir.mkdir(exist_ok=True)
    log_file = prof_dir / "timings.jsonl"
    with open(log_file, "a") as f:
        f.write(json.dumps(record, default=str) + "\n")


class timed_op:
    """Decorator and context manager for timing operations.

    As decorator:
        @timed_op(category="embed", units="vectors")
        def embed_batch(texts): ...

    As context manager:
        with timed_op("vast_up", category="infra") as t:
            do_work()
            t.items = 1
    """

    def __init__(
        self,
        name_or_func: str | Callable | None = None,
        category: str = "general",
        units: str = "items",
        context: dict | None = None,
    ):
        self.category = category
        self.units = units
        self.extra_context = context or {}
        self.items: int = 0
        self._start: float = 0.0
        self._name: str = ""

        # If used as @timed_op (no args), name_or_func is the function
        if callable(name_or_func):
            self._func = name_or_func
            self._name = name_or_func.__qualname__
        elif isinstance(name_or_func, str):
            self._func = None
            self._name = name_or_func
        else:
            self._func = None

    def __call__(self, *args, **kwargs):
        # If wrapping a function directly: @timed_op
        if self._func is not None:
            return self._run_decorated(self._func, *args, **kwargs)

        # If used as @timed_op(category="embed") — returns decorator
        func = args[0] if args and callable(args[0]) else None
        if func:
            self._name = self._name or func.__qualname__

            @functools.wraps(func)
            def wrapper(*a, **kw):
                return self._run_decorated(func, *a, **kw)
            return wrapper

        raise TypeError("timed_op must be used as @decorator or context manager")

    def _run_decorated(self, func, *args, **kwargs):
        """Run a decorated function with timing."""
        start = time.monotonic()
        result = func(*args, **kwargs)
        duration_ms = int((time.monotonic() - start) * 1000)

        # Infer items from result
        items = self.items
        if not items:
            if isinstance(result, (list, tuple)):
                items = len(result)
            elif isinstance(result, dict) and "total" in result:
                items = result["total"]
            elif isinstance(result, int):
                items = result

        throughput = (items / (duration_ms / 1000)) if duration_ms > 0 and items > 0 else 0

        record = {
            "operation": self._name or func.__qualname__,
            "category": self.category,
            "repo": _detect_repo(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "duration_ms": duration_ms,
            "items": items,
            "throughput": round(throughput, 1),
            "units": f"{self.units}/sec",
            "context": self.extra_context,
        }
        _write_timing(record)
        return result

    def __enter__(self):
        self._start = time.monotonic()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration_ms = int((time.monotonic() - self._start) * 1000)
        throughput = (self.items / (duration_ms / 1000)) if duration_ms > 0 and self.items > 0 else 0

        record = {
            "operation": self._name or "unnamed",
            "category": self.category,
            "repo": _detect_repo(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "duration_ms": duration_ms,
            "items": self.items,
            "throughput": round(throughput, 1),
            "units": f"{self.units}/sec",
            "context": self.extra_context,
        }
        _write_timing(record)
        return False


def get_timings(
    repo_path: str | Path | None = None,
    category: str | None = None,
    operation: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """Read timing records, optionally filtered."""
    if repo_path is None:
        repo_path = Path.cwd()
    log_file = Path(repo_path) / ".profiling" / "timings.jsonl"
    if not log_file.exists():
        return []

    records = []
    with open(log_file) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if category and rec.get("category") != category:
                continue
            if operation and rec.get("operation") != operation:
                continue
            records.append(rec)

    return records[-limit:]


def compare_timings(
    operation: str,
    repo_path: str | Path | None = None,
) -> dict:
    """Get stats for an operation: min, max, avg, count, trend."""
    records = get_timings(repo_path, operation=operation, limit=1000)
    if not records:
        return {"operation": operation, "count": 0}

    durations = [r["duration_ms"] for r in records]
    throughputs = [r["throughput"] for r in records if r.get("throughput")]

    stats = {
        "operation": operation,
        "count": len(records),
        "duration_min_ms": min(durations),
        "duration_max_ms": max(durations),
        "duration_avg_ms": int(sum(durations) / len(durations)),
        "last_run": records[-1].get("timestamp", ""),
    }

    if throughputs:
        stats["throughput_avg"] = round(sum(throughputs) / len(throughputs), 1)
        stats["throughput_max"] = round(max(throughputs), 1)
        stats["units"] = records[-1].get("units", "items/sec")

    # Trend: compare last 5 vs first 5
    if len(durations) >= 10:
        first5 = sum(durations[:5]) / 5
        last5 = sum(durations[-5:]) / 5
        if first5 > 0:
            change_pct = ((last5 - first5) / first5) * 100
            stats["trend_pct"] = round(change_pct, 1)
            stats["trend"] = "faster" if change_pct < -5 else "slower" if change_pct > 5 else "stable"

    return stats


def project_scale(
    operation: str,
    target_items: int,
    repo_path: str | Path | None = None,
) -> dict:
    """Project how long an operation would take at target scale."""
    stats = compare_timings(operation, repo_path)
    if not stats.get("throughput_avg"):
        return {"operation": operation, "error": "no throughput data"}

    throughput = stats["throughput_avg"]
    projected_sec = target_items / throughput if throughput > 0 else float("inf")

    return {
        "operation": operation,
        "target_items": target_items,
        "throughput_avg": throughput,
        "units": stats.get("units", "items/sec"),
        "projected_seconds": round(projected_sec, 1),
        "projected_human": _human_time(projected_sec),
    }


def _human_time(seconds: float) -> str:
    """Format seconds into human-readable time."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    if seconds < 3600:
        return f"{seconds / 60:.0f}min"
    return f"{seconds / 3600:.1f}hr"
