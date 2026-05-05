#!/usr/bin/env python3
"""Benchmark all system operations — embed, upsert, query, encrypt, deploy.

Generates synthetic data, times each operation at multiple batch sizes,
stores results, and optionally generates an HTML report.

Usage:
    python scripts/benchmark.py                     # run all categories
    python scripts/benchmark.py --category=embed    # just embedding
    python scripts/benchmark.py --compare           # compare against historical
    python scripts/benchmark.py --project=100000    # project time at scale
    python scripts/benchmark.py --report            # generate HTML dashboard
"""

import json
import os
import random
import string
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROFILING_DIR = Path(__file__).parent.parent / ".profiling"

C = {
    "reset": "\033[0m", "bold": "\033[1m", "dim": "\033[90m",
    "green": "\033[32m", "yellow": "\033[33m", "red": "\033[31m",
    "cyan": "\033[36m",
}


def _write_result(result: dict) -> None:
    PROFILING_DIR.mkdir(exist_ok=True)
    with open(PROFILING_DIR / "benchmarks.jsonl", "a") as f:
        f.write(json.dumps(result, default=str) + "\n")


def _synthetic_texts(n: int, avg_chars: int = 500) -> list[str]:
    """Generate n synthetic text chunks that resemble legal/research content."""
    templates = [
        "On {date}, the respondent filed a motion for {topic} in the {court} court. "
        "The filing referenced exhibits {num1} through {num2}, including bank statements "
        "from {bank} showing transactions totaling ${amount}.",
        "Analysis of {topic} reveals a {adj} pattern across {num1} data points. "
        "The correlation coefficient of {pct}% suggests {conclusion}. "
        "Further investigation of {bank} records from {date} is recommended.",
        "The iron-air battery system operates at ${amount}/kWh with {num1}-hour duration. "
        "ERCOT grid integration requires {topic} compliance by {date}. "
        "Bond financing under the UNA structure provides {pct}% ITC direct pay.",
    ]
    topics = ["custody", "asset disclosure", "contempt", "discovery", "settlement",
              "energy storage", "grid compliance", "bond issuance", "solar partnership"]
    courts = ["Cook County", "Circuit", "Family", "Domestic Relations"]
    banks = ["JPMorgan", "Chase", "Revolut", "Wells Fargo"]
    adjs = ["significant", "recurring", "notable", "concerning", "stable"]

    texts = []
    for _ in range(n):
        tmpl = random.choice(templates)
        text = tmpl.format(
            date=f"2024-{random.randint(1,12):02d}-{random.randint(1,28):02d}",
            topic=random.choice(topics),
            court=random.choice(courts),
            num1=random.randint(1, 50),
            num2=random.randint(51, 200),
            bank=random.choice(banks),
            amount=f"{random.randint(1000, 500000):,}",
            pct=f"{random.uniform(10, 95):.1f}",
            adj=random.choice(adjs),
            conclusion="further analysis is warranted",
        )
        # Pad or trim to target length
        while len(text) < avg_chars:
            text += " " + random.choice(string.ascii_lowercase) * random.randint(5, 20)
        texts.append(text[:avg_chars])
    return texts


def bench_embed_ollama(batch_sizes: list[int] = [1, 10, 50]):
    """Benchmark local Ollama embedding."""
    import urllib.request

    url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    model = "nomic-embed-text"

    print(f"\n  {C['bold']}Embed: Ollama ({model}){C['reset']}")

    for n in batch_sizes:
        texts = _synthetic_texts(n, avg_chars=400)
        try:
            payload = json.dumps({"model": model, "input": texts}).encode()
            req = urllib.request.Request(
                f"{url}/api/embed", data=payload,
                headers={"Content-Type": "application/json"},
            )
            start = time.monotonic()
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read())
            duration_ms = int((time.monotonic() - start) * 1000)
            vecs = len(data.get("embeddings", []))
            throughput = vecs / (duration_ms / 1000) if duration_ms > 0 else 0

            result = {
                "operation": "embed_ollama",
                "category": "embed",
                "batch_size": n,
                "duration_ms": duration_ms,
                "items": vecs,
                "throughput": round(throughput, 1),
                "units": "vectors/sec",
                "model": model,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            _write_result(result)
            print(f"    batch={n:>4}  {duration_ms:>6}ms  {throughput:>8.1f} vec/sec")
        except Exception as e:
            print(f"    batch={n:>4}  {C['red']}FAILED: {e}{C['reset']}")


def bench_qdrant_upsert(batch_sizes: list[int] = [10, 100, 500]):
    """Benchmark Qdrant upsert (flat vectors)."""
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, PointStruct, VectorParams

    TEST_COLLECTION = "_benchmark_test"
    client = QdrantClient(host="localhost", port=6333, timeout=10)

    print(f"\n  {C['bold']}DB Upsert: Qdrant{C['reset']}")

    for n in batch_sizes:
        # Create fresh collection
        try:
            client.delete_collection(TEST_COLLECTION)
        except Exception:
            pass
        client.create_collection(
            TEST_COLLECTION,
            vectors_config=VectorParams(size=768, distance=Distance.COSINE),
        )

        # Generate random vectors
        points = [
            PointStruct(
                id=i,
                vector=[random.gauss(0, 1) for _ in range(768)],
                payload={"text": f"test point {i}", "batch": n},
            )
            for i in range(n)
        ]

        start = time.monotonic()
        client.upsert(TEST_COLLECTION, points=points)
        duration_ms = int((time.monotonic() - start) * 1000)
        throughput = n / (duration_ms / 1000) if duration_ms > 0 else 0

        result = {
            "operation": "qdrant_upsert",
            "category": "db_upsert",
            "batch_size": n,
            "duration_ms": duration_ms,
            "items": n,
            "throughput": round(throughput, 1),
            "units": "points/sec",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        _write_result(result)
        print(f"    batch={n:>4}  {duration_ms:>6}ms  {throughput:>8.1f} pts/sec")

        client.delete_collection(TEST_COLLECTION)


def bench_qdrant_search(queries: int = 20):
    """Benchmark Qdrant search on existing collections."""
    from qdrant_client import QdrantClient

    client = QdrantClient(host="localhost", port=6333, timeout=10)

    print(f"\n  {C['bold']}DB Query: Qdrant search{C['reset']}")

    for col_name in ["legal_docs_v2", "claude_code_sessions"]:
        try:
            info = client.get_collection(col_name)
            pts = info.points_count
        except Exception:
            continue

        durations = []
        for _ in range(queries):
            vec = [random.gauss(0, 1) for _ in range(768)]
            start = time.monotonic()
            try:
                client.query_points(col_name, query=vec, limit=10, using="dense")
            except Exception:
                try:
                    client.query_points(col_name, query=vec, limit=10)
                except Exception:
                    continue
            durations.append((time.monotonic() - start) * 1000)

        if durations:
            avg_ms = sum(durations) / len(durations)
            p95 = sorted(durations)[int(len(durations) * 0.95)]
            result = {
                "operation": f"qdrant_search_{col_name}",
                "category": "db_query",
                "items": len(durations),
                "duration_avg_ms": round(avg_ms, 1),
                "duration_p95_ms": round(p95, 1),
                "collection_size": pts,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            _write_result(result)
            print(f"    {col_name} ({pts:,} pts)  avg={avg_ms:.1f}ms  p95={p95:.1f}ms")


def bench_encrypt(counts: list[int] = [10, 100]):
    """Benchmark AES-256-GCM page encryption."""
    sys.path.insert(0, str(Path.home() / "GitHub" / "contacts" / "tools"))

    print(f"\n  {C['bold']}Encrypt: AES-256-GCM{C['reset']}")

    try:
        from encrypt_page import encrypt_html
    except ImportError:
        print(f"    {C['red']}encrypt_page not found{C['reset']}")
        return

    # Generate synthetic HTML
    html = "<html><body>" + "x" * 10000 + "</body></html>"
    password = "benchmark_password_123"

    for n in counts:
        start = time.monotonic()
        for _ in range(n):
            encrypt_html(html, password)
        duration_ms = int((time.monotonic() - start) * 1000)
        throughput = n / (duration_ms / 1000) if duration_ms > 0 else 0

        result = {
            "operation": "encrypt_page",
            "category": "generate",
            "batch_size": n,
            "duration_ms": duration_ms,
            "items": n,
            "throughput": round(throughput, 1),
            "units": "pages/sec",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        _write_result(result)
        print(f"    n={n:>4}  {duration_ms:>6}ms  {throughput:>8.1f} pages/sec")


def show_projections(target: int):
    """Show scale projections based on collected benchmarks."""
    results_file = PROFILING_DIR / "benchmarks.jsonl"
    if not results_file.exists():
        print(f"  {C['yellow']}No benchmark data. Run devctl benchmark first.{C['reset']}")
        return

    records = []
    with open(results_file) as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))

    # Group by operation, take latest throughput
    ops = {}
    for rec in records:
        op = rec.get("operation", "")
        tp = rec.get("throughput", 0)
        if tp > 0:
            ops[op] = rec

    print(f"\n  {C['bold']}Scale Projections — {target:,} items{C['reset']}\n")
    print(f"  {'Operation':<30} {'Throughput':>12} {'Projected':>12}")
    print(f"  {'─'*56}")

    for op, rec in sorted(ops.items()):
        tp = rec["throughput"]
        units = rec.get("units", "items/sec")
        projected_sec = target / tp if tp > 0 else float("inf")

        if projected_sec < 60:
            time_str = f"{projected_sec:.0f}s"
        elif projected_sec < 3600:
            time_str = f"{projected_sec / 60:.0f}min"
        else:
            time_str = f"{projected_sec / 3600:.1f}hr"

        print(f"  {op:<30} {tp:>8.1f} {units:<4} {time_str:>12}")


def show_comparison():
    """Compare latest benchmarks against historical."""
    results_file = PROFILING_DIR / "benchmarks.jsonl"
    if not results_file.exists():
        print(f"  {C['yellow']}No benchmark data.{C['reset']}")
        return

    records = []
    with open(results_file) as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))

    # Group by operation
    by_op = {}
    for rec in records:
        op = rec.get("operation", "")
        by_op.setdefault(op, []).append(rec)

    print(f"\n  {C['bold']}Benchmark Comparison{C['reset']}\n")
    print(f"  {'Operation':<30} {'Runs':>5} {'Avg tp':>10} {'Best':>10} {'Trend'}")
    print(f"  {'─'*65}")

    for op, recs in sorted(by_op.items()):
        throughputs = [r.get("throughput", 0) for r in recs if r.get("throughput")]
        if not throughputs:
            continue
        avg = sum(throughputs) / len(throughputs)
        best = max(throughputs)
        units = recs[-1].get("units", "items/sec")

        trend = ""
        if len(throughputs) >= 4:
            first = sum(throughputs[:2]) / 2
            last = sum(throughputs[-2:]) / 2
            if first > 0:
                pct = ((last - first) / first) * 100
                if pct > 5:
                    trend = f"{C['green']}+{pct:.0f}%{C['reset']}"
                elif pct < -5:
                    trend = f"{C['red']}{pct:.0f}%{C['reset']}"
                else:
                    trend = f"{C['dim']}stable{C['reset']}"

        print(f"  {op:<30} {len(recs):>5} {avg:>8.1f}/s {best:>8.1f}/s {trend}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="System benchmarks")
    parser.add_argument("--category", default=None, help="Only run this category")
    parser.add_argument("--compare", action="store_true", help="Compare against historical")
    parser.add_argument("--project", type=int, default=None, help="Project time at this scale")
    parser.add_argument("--report", action="store_true", help="Generate HTML report")
    args = parser.parse_args()

    if args.compare:
        show_comparison()
        return

    if args.project:
        show_projections(args.project)
        return

    print(f"\n{C['bold']}  System Benchmark{C['reset']}")
    print(f"  {'─'*55}")

    categories = {
        "embed": bench_embed_ollama,
        "db_upsert": bench_qdrant_upsert,
        "db_query": bench_qdrant_search,
        "generate": bench_encrypt,
    }

    for cat, func in categories.items():
        if args.category and cat != args.category:
            continue
        try:
            func()
        except Exception as e:
            print(f"\n  {C['red']}{cat} failed: {e}{C['reset']}")

    print(f"\n  {C['dim']}Results saved to {PROFILING_DIR / 'benchmarks.jsonl'}{C['reset']}\n")

    if args.report:
        print(f"  {C['yellow']}HTML report generation not yet implemented{C['reset']}")


if __name__ == "__main__":
    main()
