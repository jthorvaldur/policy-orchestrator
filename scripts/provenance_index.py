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

    # Original builds table (build artifact provenance)
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

    # File-level provenance (all tracked files)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS files (
            content_hash TEXT PRIMARY KEY,
            file_path TEXT NOT NULL,
            repo TEXT,
            first_seen TEXT DEFAULT (datetime('now')),
            last_modified TEXT,
            file_size INTEGER,
            mime_type TEXT,
            created_by TEXT,
            session_id TEXT,
            git_commit TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_files_repo ON files(repo)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_files_path ON files(file_path)")

    # File lineage (input → output relationships)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS file_lineage (
            output_hash TEXT NOT NULL REFERENCES files(content_hash),
            input_hash TEXT NOT NULL REFERENCES files(content_hash),
            transform TEXT,
            timestamp TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (output_hash, input_hash)
        )
    """)

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


def _hash_file_sha256(path: Path) -> str:
    """SHA-256 hash of file contents."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"


def _guess_mime(path: Path) -> str:
    """Basic MIME type guess from extension."""
    ext_map = {
        ".py": "text/x-python", ".js": "text/javascript", ".ts": "text/typescript",
        ".html": "text/html", ".css": "text/css", ".md": "text/markdown",
        ".json": "application/json", ".yaml": "text/yaml", ".yml": "text/yaml",
        ".csv": "text/csv", ".sql": "text/sql", ".sh": "text/x-shellscript",
        ".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg",
        ".lz4": "application/x-lz4", ".gz": "application/gzip",
        ".zip": "application/zip", ".toml": "text/toml",
    }
    return ext_map.get(path.suffix.lower(), "application/octet-stream")


def scan_repo(repo_name: str):
    """Hash all tracked files in a repo and register in provenance DB."""
    with open(REGISTRIES / "repos.yaml") as f:
        repos = {r["name"]: r for r in yaml.safe_load(f).get("repos", [])}

    if repo_name not in repos:
        print(f"  {C['red']}Repo '{repo_name}' not in registry{C['reset']}")
        return

    repo_path = Path(repos[repo_name]["path"]).expanduser()
    if not repo_path.exists():
        print(f"  {C['red']}Path not found: {repo_path}{C['reset']}")
        return

    # Get git-tracked files (respects .gitignore)
    import subprocess
    result = subprocess.run(
        ["git", "ls-files"], capture_output=True, text=True, cwd=str(repo_path)
    )
    if result.returncode != 0:
        print(f"  {C['red']}Not a git repo: {repo_path}{C['reset']}")
        return

    tracked_files = [repo_path / f for f in result.stdout.strip().split("\n") if f]

    # Get latest git commit
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=str(repo_path)
    ).stdout.strip()[:40]

    conn = get_db()
    new_count = 0
    updated_count = 0
    skipped_count = 0

    for fp in tracked_files:
        if not fp.exists() or fp.is_dir():
            continue

        content_hash = _hash_file_sha256(fp)
        file_size = fp.stat().st_size
        last_modified = str(fp.stat().st_mtime)
        rel_path = str(fp.relative_to(repo_path))

        # Check if already tracked with same hash
        existing = conn.execute(
            "SELECT content_hash, file_path FROM files WHERE file_path = ? AND repo = ?",
            (rel_path, repo_name),
        ).fetchone()

        if existing and existing["content_hash"] == content_hash:
            skipped_count += 1
            continue

        if existing:
            # File changed — update
            conn.execute(
                """UPDATE files SET content_hash=?, last_modified=?, file_size=?,
                   git_commit=? WHERE file_path=? AND repo=?""",
                (content_hash, last_modified, file_size, commit, rel_path, repo_name),
            )
            updated_count += 1
        else:
            # New file
            conn.execute(
                """INSERT OR REPLACE INTO files
                   (content_hash, file_path, repo, last_modified, file_size,
                    mime_type, created_by, git_commit)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (content_hash, rel_path, repo_name, last_modified, file_size,
                 _guess_mime(fp), "git", commit),
            )
            new_count += 1

    conn.commit()
    conn.close()

    total = new_count + updated_count + skipped_count
    print(f"  {C['bold']}{repo_name}{C['reset']}: "
          f"{total} files scanned, "
          f"{C['green']}{new_count} new{C['reset']}, "
          f"{C['yellow']}{updated_count} updated{C['reset']}, "
          f"{C['dim']}{skipped_count} unchanged{C['reset']}")


def trace_file(file_path: str):
    """Show full provenance chain for a file."""
    conn = get_db()
    # Search by path (partial match)
    rows = conn.execute(
        "SELECT * FROM files WHERE file_path LIKE ?",
        (f"%{file_path}%",),
    ).fetchall()

    if not rows:
        print(f"  {C['yellow']}No file found matching: {file_path}{C['reset']}")
        return

    for row in rows:
        row = dict(row)
        print(f"\n  {C['bold']}{row['repo']}/{row['file_path']}{C['reset']}")
        print(f"  {'Hash:':<16} {row['content_hash']}")
        print(f"  {'Size:':<16} {row['file_size']} bytes")
        print(f"  {'Type:':<16} {row['mime_type']}")
        print(f"  {'Created by:':<16} {row['created_by']}")
        print(f"  {'Git commit:':<16} {row['git_commit']}")
        print(f"  {'First seen:':<16} {row['first_seen']}")

        # Check lineage
        inputs = conn.execute(
            "SELECT f.repo, f.file_path, l.transform FROM file_lineage l "
            "JOIN files f ON f.content_hash = l.input_hash "
            "WHERE l.output_hash = ?",
            (row["content_hash"],),
        ).fetchall()
        if inputs:
            print(f"  {'Derived from:':<16}")
            for inp in inputs:
                print(f"    {inp['repo']}/{inp['file_path']} (via {inp['transform']})")

        outputs = conn.execute(
            "SELECT f.repo, f.file_path, l.transform FROM file_lineage l "
            "JOIN files f ON f.content_hash = l.output_hash "
            "WHERE l.input_hash = ?",
            (row["content_hash"],),
        ).fetchall()
        if outputs:
            print(f"  {'Used to create:':<16}")
            for out in outputs:
                print(f"    {out['repo']}/{out['file_path']} (via {out['transform']})")

    print()


def main():
    args = sys.argv[1:]
    cmd = args[0] if args else "list"

    if cmd == "rebuild":
        rebuild_index()
    elif cmd == "show" and len(args) > 1:
        show_provenance(args[1])
    elif cmd == "stale":
        find_stale()
    elif cmd == "scan" and len(args) > 1:
        repo_name = args[1].replace("--repo=", "")
        scan_repo(repo_name)
    elif cmd == "trace" and len(args) > 1:
        trace_file(args[1])
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
