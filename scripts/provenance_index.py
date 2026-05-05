#!/usr/bin/env python3
"""Provenance index — SQLite index built from per-repo JSONL provenance files.

Usage:
    python scripts/provenance_index.py rebuild     # sync all JSONL → SQLite
    python scripts/provenance_index.py show PATH   # show provenance for a file
    python scripts/provenance_index.py stale        # find outputs with changed inputs
    python scripts/provenance_index.py list [--repo=X]  # list all tracked outputs
"""

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import yaml

REGISTRIES = Path(__file__).parent.parent / "registries"
DB_DIR = Path.home() / ".local" / "share" / "devctl"
DB_PATH = DB_DIR / "provenance.db"

C = {
    "reset": "\033[0m", "bold": "\033[1m", "dim": "\033[90m",
    "green": "\033[32m", "yellow": "\033[33m", "red": "\033[31m",
    "cyan": "\033[36m",
}


def get_db():
    """Get or create the SQLite provenance database."""
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS builds (
            id TEXT PRIMARY KEY,
            repo TEXT NOT NULL,
            generator TEXT NOT NULL,
            outputs TEXT NOT NULL,
            output_hashes TEXT,
            inputs TEXT,
            input_hashes TEXT,
            parameters TEXT,
            timestamp TEXT NOT NULL,
            duration_ms INTEGER,
            recreate_cmd TEXT,
            items INTEGER DEFAULT 0
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_builds_repo ON builds(repo)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_builds_ts ON builds(timestamp)")
    conn.commit()
    return conn


def rebuild_index():
    """Scan all repos for .provenance/build.jsonl and load into SQLite."""
    with open(REGISTRIES / "repos.yaml") as f:
        repos = yaml.safe_load(f).get("repos", [])

    conn = get_db()
    conn.execute("DELETE FROM builds")

    total = 0
    for repo in repos:
        path = Path(repo.get("path", "")).expanduser()
        jsonl = path / ".provenance" / "build.jsonl"
        if not jsonl.exists():
            continue

        count = 0
        with open(jsonl) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                conn.execute(
                    """INSERT OR REPLACE INTO builds
                       (id, repo, generator, outputs, output_hashes, inputs,
                        input_hashes, parameters, timestamp, duration_ms,
                        recreate_cmd, items)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        rec.get("id", ""),
                        rec.get("repo", repo["name"]),
                        rec.get("generator", ""),
                        json.dumps(rec.get("outputs", [])),
                        json.dumps(rec.get("output_hashes", {})),
                        json.dumps(rec.get("inputs", [])),
                        json.dumps(rec.get("input_hashes", {})),
                        json.dumps(rec.get("parameters", {})),
                        rec.get("timestamp", ""),
                        rec.get("duration_ms", 0),
                        rec.get("recreate_cmd", ""),
                        rec.get("items", 0),
                    ),
                )
                count += 1
        total += count
        print(f"  {repo['name']}: {count} records")

    conn.commit()
    conn.close()
    print(f"\nIndexed {total} records into {DB_PATH}")


def show_provenance(output_path: str):
    """Show the most recent provenance record for a file."""
    conn = get_db()
    # Search for output_path in the outputs JSON array
    rows = conn.execute(
        "SELECT * FROM builds WHERE outputs LIKE ? ORDER BY timestamp DESC LIMIT 1",
        (f"%{output_path}%",),
    ).fetchall()

    if not rows:
        print(f"  {C['yellow']}No provenance found for: {output_path}{C['reset']}")
        return

    row = dict(rows[0])
    print(f"\n  {C['bold']}Provenance: {output_path}{C['reset']}\n")
    print(f"  {'Generator:':<16} {row['generator']}")
    print(f"  {'Repo:':<16} {row['repo']}")
    print(f"  {'Timestamp:':<16} {row['timestamp']}")
    print(f"  {'Duration:':<16} {row['duration_ms']}ms")
    print(f"  {'Items:':<16} {row['items']}")
    print(f"  {'Inputs:':<16} {row['inputs']}")
    print(f"  {'Recreate:':<16} {row['recreate_cmd']}")
    print()


def find_stale():
    """Find outputs whose input file hashes have changed since last build."""
    sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
    from provenance import _hash_file

    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM builds ORDER BY timestamp DESC"
    ).fetchall()

    # Deduplicate by output (keep latest)
    seen_outputs = set()
    stale = []
    current = []

    for row in rows:
        outputs = json.loads(row["outputs"])
        key = tuple(sorted(outputs))
        if key in seen_outputs:
            continue
        seen_outputs.add(key)

        input_hashes = json.loads(row["input_hashes"] or "{}")
        is_stale = False

        for inp, old_hash in input_hashes.items():
            if not old_hash:
                continue
            p = Path(inp)
            if p.exists():
                current_hash = _hash_file(p)
                if current_hash != old_hash:
                    is_stale = True
                    break

        if is_stale:
            stale.append(dict(row))
        else:
            current.append(dict(row))

    print(f"\n  {C['bold']}Provenance Staleness Check{C['reset']}\n")

    if stale:
        print(f"  {C['red']}{len(stale)} stale outputs (inputs changed):{C['reset']}")
        for s in stale:
            outputs = json.loads(s["outputs"])
            print(f"    {C['yellow']}{', '.join(outputs)}{C['reset']}")
            print(f"      {C['dim']}recreate: {s['recreate_cmd']}{C['reset']}")
    else:
        print(f"  {C['green']}All tracked outputs are current.{C['reset']}")

    print(f"\n  {len(current)} current, {len(stale)} stale, {len(seen_outputs)} total tracked\n")


def list_builds(repo_filter=None):
    """List all tracked outputs."""
    conn = get_db()
    query = "SELECT * FROM builds ORDER BY timestamp DESC"
    params = ()
    if repo_filter:
        query = "SELECT * FROM builds WHERE repo = ? ORDER BY timestamp DESC"
        params = (repo_filter,)

    rows = conn.execute(query, params).fetchall()

    print(f"\n  {C['bold']}Tracked Outputs{C['reset']}")
    print(f"  {'─'*70}\n")
    print(f"  {'Repo':<20} {'Generator':<30} {'Items':>6} {'Time':>8} {'When'}")
    print(f"  {'─'*70}")

    for row in rows:
        outputs = json.loads(row["outputs"])
        ts = row["timestamp"][:10] if row["timestamp"] else "?"
        dur = f"{row['duration_ms']}ms" if row["duration_ms"] else "?"
        gen = row["generator"].split(":")[-1][:28] if row["generator"] else "?"
        print(f"  {row['repo']:<20} {gen:<30} {row['items']:>6} {dur:>8} {ts}")

    print(f"\n  {len(rows)} records\n")


def main():
    args = sys.argv[1:]
    cmd = args[0] if args else "list"

    if cmd == "rebuild":
        rebuild_index()
    elif cmd == "show" and len(args) > 1:
        show_provenance(args[1])
    elif cmd == "stale":
        find_stale()
    elif cmd == "list":
        repo = None
        for a in args:
            if a.startswith("--repo="):
                repo = a.split("=", 1)[1]
        list_builds(repo)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
