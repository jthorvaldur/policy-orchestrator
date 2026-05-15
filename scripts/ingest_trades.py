#!/usr/bin/env python3
"""Ingest trade data (Binance CSV / Hyperliquid NDJSON) into TimescaleDB.

Usage:
    # Ingest Hyperliquid fills from local sample
    python ingest_trades.py --source ./hl_fills/ --exchange hyperliquid

    # Ingest Binance trades for specific symbol
    python ingest_trades.py --source ./bn_trades/ --exchange binance --symbol BTCUSDT

    # Ingest everything in a directory
    python ingest_trades.py --source ./bn_trades/ --exchange binance --workers 4

    # Dry run — count files and estimate rows without inserting
    python ingest_trades.py --source ./hl_fills/ --exchange hyperliquid --dry-run
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

TSDB_HOST = "localhost"
TSDB_PORT = 5434
TSDB_DB = "orchestrator"
TSDB_USER = "orchestrator"
TSDB_PASS = "orchestrator_dev"

BATCH_SIZE = 10_000  # rows per INSERT batch
COMMIT_EVERY = 100_000  # rows between commits


def human(n: int | float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}PB"


def get_conn():
    return psycopg2.connect(
        host=TSDB_HOST, port=TSDB_PORT,
        dbname=TSDB_DB, user=TSDB_USER, password=TSDB_PASS,
    )


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def parse_binance_csv(path: Path) -> list[tuple]:
    """Parse Binance trade CSV into rows for the trades table."""
    rows = []
    with open(path, "r") as f:
        reader = csv.reader(f)
        for line in reader:
            if len(line) < 6:
                continue
            try:
                trade_id = int(line[0])
                price = float(line[1])
                qty = float(line[2])
                quote_qty = float(line[3])
                # Binance timestamps are microseconds
                ts = int(line[4])
                if ts > 1e15:  # microseconds
                    dt = datetime.fromtimestamp(ts / 1_000_000, tz=timezone.utc)
                elif ts > 1e12:  # milliseconds
                    dt = datetime.fromtimestamp(ts / 1_000, tz=timezone.utc)
                else:
                    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                is_buyer_maker = line[5].strip().lower() == "true"
                side = "A" if is_buyer_maker else "B"  # maker sell = taker buy
                rows.append((
                    dt, "binance", None, price, qty, quote_qty,
                    side, is_buyer_maker, trade_id,
                    None, None, None, None,  # HL-specific fields
                    str(path),
                ))
            except (ValueError, IndexError):
                continue
    return rows


def parse_hl_lz4(path: Path) -> list[tuple]:
    """Parse Hyperliquid LZ4-compressed NDJSON into rows."""
    import lz4.frame
    rows = []
    with open(path, "rb") as f:
        data = lz4.frame.decompress(f.read())
    for line in data.decode("utf-8").splitlines():
        if not line.strip():
            continue
        try:
            arr = json.loads(line)
            wallet, fill = arr[0], arr[1]
            ts_ms = fill["time"]
            dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
            rows.append((
                dt, "hyperliquid", fill["coin"],
                float(fill["px"]), float(fill["sz"]),
                float(fill["px"]) * float(fill["sz"]),  # quote_qty = notional
                fill.get("side"), fill.get("crossed"),
                fill.get("tid"),
                wallet,
                float(fill["closedPnl"]) if "closedPnl" in fill else None,
                float(fill["fee"]) if "fee" in fill else None,
                fill.get("dir"),
                str(path),
            ))
        except (json.JSONDecodeError, KeyError, ValueError):
            continue
    return rows


def parse_hl_json(path: Path) -> list[tuple]:
    """Parse uncompressed Hyperliquid NDJSON."""
    rows = []
    with open(path, "r") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                arr = json.loads(line)
                wallet, fill = arr[0], arr[1]
                ts_ms = fill["time"]
                dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
                rows.append((
                    dt, "hyperliquid", fill["coin"],
                    float(fill["px"]), float(fill["sz"]),
                    float(fill["px"]) * float(fill["sz"]),
                    fill.get("side"), fill.get("crossed"),
                    fill.get("tid"),
                    wallet,
                    float(fill["closedPnl"]) if "closedPnl" in fill else None,
                    float(fill["fee"]) if "fee" in fill else None,
                    fill.get("dir"),
                    str(path),
                ))
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
    return rows


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def discover_files(source: Path, exchange: str, symbol: str | None) -> list[Path]:
    """Find trade data files in the source directory."""
    files = []
    if exchange == "binance":
        if symbol:
            pattern = source / symbol / "*.csv"
            files = sorted(pattern.parent.glob(pattern.name))
        else:
            files = sorted(source.rglob("*.csv"))
    elif exchange == "hyperliquid":
        files = sorted(source.rglob("*.lz4"))
        if not files:
            files = sorted(source.rglob("*.json")) + sorted(source.rglob("*.jsonl"))
    return files


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------

INSERT_SQL = """
INSERT INTO trades (time, exchange, symbol, price, quantity, quote_qty,
                    side, is_maker, trade_id, wallet, closed_pnl, fee,
                    direction, source_file)
VALUES %s
ON CONFLICT DO NOTHING
"""


def ingest_file(path: Path, exchange: str, symbol: str | None,
                conn, dry_run: bool = False) -> tuple[int, int]:
    """Ingest one file. Returns (rows_inserted, rows_skipped)."""
    if exchange == "binance":
        rows = parse_binance_csv(path)
        # Inject symbol from directory name
        if symbol:
            sym = symbol
        else:
            sym = path.parent.name  # e.g., bn_trades/BTCUSDT/2025-05-25.csv
        rows = [(r[0], r[1], sym, *r[3:]) for r in rows]
    elif exchange == "hyperliquid":
        if path.suffix == ".lz4":
            rows = parse_hl_lz4(path)
        else:
            rows = parse_hl_json(path)
    else:
        return (0, 0)

    if dry_run:
        return (len(rows), 0)

    if not rows:
        return (0, 0)

    cur = conn.cursor()
    total = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        execute_values(cur, INSERT_SQL, batch, page_size=BATCH_SIZE)
        total += len(batch)
        if total % COMMIT_EVERY == 0:
            conn.commit()
    conn.commit()
    cur.close()
    return (total, 0)


def cmd_ingest(source: str, exchange: str, symbol: str | None,
               workers: int, dry_run: bool) -> None:
    source_dir = Path(source)
    files = discover_files(source_dir, exchange, symbol)
    print(f"Found {len(files)} files in {source_dir} (exchange={exchange})")

    if not files:
        print("Nothing to ingest.")
        return

    if dry_run:
        total_rows = 0
        for f in files[:5]:
            if exchange == "binance":
                rows = parse_binance_csv(f)
            elif f.suffix == ".lz4":
                rows = parse_hl_lz4(f)
            else:
                rows = parse_hl_json(f)
            print(f"  {f.name}: {len(rows):,} rows")
            total_rows += len(rows)
        if len(files) > 5:
            avg = total_rows / 5
            print(f"  ... +{len(files) - 5} more (est. {avg * len(files):,.0f} total rows)")
        return

    conn = get_conn()
    total_rows = 0
    total_files = 0
    t0 = time.monotonic()

    for i, f in enumerate(files):
        n_inserted, _ = ingest_file(f, exchange, symbol, conn, dry_run=False)
        total_rows += n_inserted
        total_files += 1
        if total_files % 10 == 0:
            elapsed = time.monotonic() - t0
            rate = total_rows / elapsed if elapsed > 0 else 0
            print(f"  [{total_files}/{len(files)}] {total_rows:,} rows "
                  f"({rate:,.0f} rows/s)", flush=True)

    conn.close()
    elapsed = time.monotonic() - t0
    rate = total_rows / elapsed if elapsed > 0 else 0
    print(f"\nDone in {elapsed:.0f}s. {total_files} files, {total_rows:,} rows "
          f"({rate:,.0f} rows/s).")


def main():
    p = argparse.ArgumentParser(
        description="Ingest trade data into TimescaleDB (port 5434)")
    p.add_argument("--source", required=True, help="Directory with trade files")
    p.add_argument("--exchange", required=True, choices=["binance", "hyperliquid"])
    p.add_argument("--symbol", default=None, help="Filter to specific symbol (Binance only)")
    p.add_argument("--workers", type=int, default=1, help="Parallel file processing")
    p.add_argument("--dry-run", action="store_true", help="Count files/rows without inserting")
    args = p.parse_args()
    cmd_ingest(args.source, args.exchange, args.symbol, args.workers, args.dry_run)


if __name__ == "__main__":
    main()
