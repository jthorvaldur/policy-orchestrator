#!/usr/bin/env python3
"""Ingest Claude Code sessions into Qdrant for semantic search."""

import hashlib
import json
import re
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

import httpx
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

QDRANT_HOST = "localhost"
QDRANT_PORT = 6333
COLLECTION_NAME = "claude_code_sessions"
VECTOR_DIM = 768  # nomic-embed-text
DISTANCE = Distance.COSINE

OLLAMA_BASE_URL = "http://localhost:11434"
EMBEDDING_MODEL = "nomic-embed-text"

SESSIONS_ROOT = Path.home() / ".claude" / "projects"
STATE_FILE = Path(__file__).parent.parent / "local" / "ingest_state.json"

CHUNK_TARGET_TOKENS = 512
CHUNK_OVERLAP_TOKENS = 64
BATCH_SIZE = 100

# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------


def embed_text(text: str, max_chars: int = 8000, max_retries: int = 3) -> list[float]:
    """Get embedding vector via Ollama."""
    if len(text) > max_chars:
        text = text[:max_chars]
    for attempt in range(max_retries):
        try:
            resp = httpx.post(
                f"{OLLAMA_BASE_URL}/api/embeddings",
                json={"model": EMBEDDING_MODEL, "prompt": text},
                timeout=120.0,
            )
            resp.raise_for_status()
            return resp.json()["embedding"]
        except (httpx.HTTPStatusError, httpx.ConnectError, httpx.ReadTimeout):
            if attempt < max_retries - 1:
                time.sleep(1.0 * (attempt + 1))
                continue
            raise


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------


def _approx_tokens(text: str) -> int:
    return len(text) // 4


def chunk_text(text: str) -> list[str]:
    """Split text into chunks respecting paragraph boundaries."""
    sections = re.split(r"\n\n+", text)
    sections = [s.strip() for s in sections if s.strip()]

    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0

    for section in sections:
        section_tokens = _approx_tokens(section)

        if current_tokens + section_tokens > CHUNK_TARGET_TOKENS and current:
            chunks.append("\n\n".join(current))

            overlap: list[str] = []
            overlap_tokens = 0
            for s in reversed(current):
                t = _approx_tokens(s)
                if overlap_tokens + t > CHUNK_OVERLAP_TOKENS:
                    break
                overlap.insert(0, s)
                overlap_tokens += t

            current = overlap
            current_tokens = overlap_tokens

        current.append(section)
        current_tokens += section_tokens

    if current:
        chunks.append("\n\n".join(current))

    return chunks if chunks else [text]


# ---------------------------------------------------------------------------
# Session parsing
# ---------------------------------------------------------------------------


def _extract_project_and_repo(project_dir: str) -> tuple[str, str]:
    """Extract repo name from project directory name."""
    # Format: -Users-jthor-GitHub-div-legal or -Users-jthor-projects-ts-embed
    project = project_dir
    repo = project_dir

    # Try to extract the last meaningful segment
    parts = project_dir.split("-")

    # Find the segment after known path components
    path_markers = {"Users", "jthor", "GitHub", "projects", "phantom", "websites"}
    meaningful = []
    skip = True
    for part in parts:
        if part in path_markers:
            skip = True
            meaningful = []
            continue
        if skip and part:
            skip = False
        if not skip:
            meaningful.append(part)

    if meaningful:
        repo = "-".join(meaningful)

    return project, repo


def parse_session(jsonl_path: Path) -> list[dict]:
    """Parse a JSONL session file into turns."""
    turns = []
    turn_index = 0

    with open(jsonl_path) as f:
        for line in f:
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg_type = obj.get("type")
            if msg_type not in ("user", "assistant"):
                continue

            message = obj.get("message", {})
            if not isinstance(message, dict):
                continue

            content = message.get("content", "")
            text = ""

            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                # Assistant messages have content blocks
                text_parts = []
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            text_parts.append(block.get("text", ""))
                        elif block.get("type") == "tool_use":
                            # Include tool name for context
                            tool_name = block.get("name", "")
                            if tool_name:
                                text_parts.append(f"[Tool: {tool_name}]")
                text = "\n".join(text_parts)

            if text.strip():
                turns.append({
                    "role": msg_type,
                    "content": text.strip(),
                    "turn_index": turn_index,
                })
                turn_index += 1

    return turns


def discover_sessions(repo_filter: str | None = None) -> list[dict]:
    """Find all JSONL session files."""
    sessions = []

    if not SESSIONS_ROOT.exists():
        return sessions

    for project_dir in SESSIONS_ROOT.iterdir():
        if not project_dir.is_dir():
            continue

        project_name = project_dir.name
        _, repo_name = _extract_project_and_repo(project_name)

        if repo_filter and repo_name != repo_filter:
            continue

        for jsonl_file in project_dir.glob("*.jsonl"):
            session_id = jsonl_file.stem
            mtime = datetime.fromtimestamp(jsonl_file.stat().st_mtime)

            sessions.append({
                "session_id": session_id,
                "project": project_name,
                "repo": repo_name,
                "path": jsonl_file,
                "date": mtime.strftime("%Y-%m-%d"),
                "size": jsonl_file.stat().st_size,
            })

    return sessions


# ---------------------------------------------------------------------------
# State management (incremental)
# ---------------------------------------------------------------------------


def load_state() -> set[str]:
    """Load set of already-ingested session IDs."""
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            data = json.load(f)
        return set(data.get("ingested_sessions", []))
    return set()


def save_state(session_ids: set[str]):
    """Save ingested session IDs."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump({
            "ingested_sessions": sorted(session_ids),
            "last_run": datetime.now().isoformat(),
        }, f, indent=2)


# ---------------------------------------------------------------------------
# Qdrant operations
# ---------------------------------------------------------------------------


def ensure_collection(client: QdrantClient):
    """Create collection if it doesn't exist."""
    collections = [c.name for c in client.get_collections().collections]
    if COLLECTION_NAME not in collections:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=VECTOR_DIM, distance=DISTANCE),
        )
        print(f"Created collection: {COLLECTION_NAME}", file=sys.stderr)


def upsert_batch(client: QdrantClient, points: list[PointStruct]):
    """Upsert a batch of points to Qdrant."""
    if not points:
        return
    client.upsert(collection_name=COLLECTION_NAME, points=points)


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def ingest_sessions(
    repo_filter: str | None = None,
    incremental: bool = True,
    dry_run: bool = False,
):
    """Run the full ingest pipeline."""

    # Connect
    if not dry_run:
        client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
        ensure_collection(client)

    # Discover
    sessions = discover_sessions(repo_filter=repo_filter)
    print(f"Found {len(sessions)} sessions", file=sys.stderr)

    # Filter already ingested
    ingested = load_state() if incremental else set()
    new_sessions = [s for s in sessions if s["session_id"] not in ingested]
    print(f"New sessions to ingest: {len(new_sessions)}", file=sys.stderr)

    if not new_sessions:
        print("Nothing to ingest.", file=sys.stderr)
        return

    total_points = 0
    total_turns = 0
    batch: list[PointStruct] = []
    newly_ingested: set[str] = set()

    for i, session in enumerate(new_sessions):
        session_id = session["session_id"]
        repo = session["repo"]
        project = session["project"]
        date = session["date"]

        print(
            f"  [{i+1}/{len(new_sessions)}] {repo} / {session_id[:12]}... ",
            end="", flush=True, file=sys.stderr,
        )

        turns = parse_session(session["path"])
        if not turns:
            print("(empty)", file=sys.stderr)
            newly_ingested.add(session_id)
            continue

        turn_count = 0
        for turn in turns:
            chunks = chunk_text(turn["content"])
            for chunk_idx, chunk in enumerate(chunks):
                if dry_run:
                    total_points += 1
                    continue

                vector = embed_text(chunk)
                point = PointStruct(
                    id=str(uuid.uuid4()),
                    vector=vector,
                    payload={
                        "session_id": session_id,
                        "project": project,
                        "repo": repo,
                        "role": turn["role"],
                        "turn_index": turn["turn_index"],
                        "chunk_index": chunk_idx,
                        "date": date,
                        "content_preview": chunk[:200],
                        "text": chunk,
                    },
                )
                batch.append(point)
                total_points += 1

                if len(batch) >= BATCH_SIZE:
                    upsert_batch(client, batch)
                    batch = []

            turn_count += 1
            total_turns += 1

        newly_ingested.add(session_id)
        print(f"{turn_count} turns, {total_points} points so far", file=sys.stderr)

    # Flush remaining batch
    if batch and not dry_run:
        upsert_batch(client, batch)

    # Save state
    if not dry_run:
        all_ingested = ingested | newly_ingested
        save_state(all_ingested)

    print(f"\nDone. {total_points} points from {total_turns} turns across {len(new_sessions)} sessions.", file=sys.stderr)
    if not dry_run:
        info = client.get_collection(COLLECTION_NAME)
        print(f"Collection '{COLLECTION_NAME}' now has {info.points_count} total points.", file=sys.stderr)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Ingest Claude Code sessions into Qdrant")
    parser.add_argument("--repo", default=None, help="Only ingest sessions from this repo")
    parser.add_argument("--all", action="store_true", help="Re-ingest all sessions (ignore state)")
    parser.add_argument("--dry-run", action="store_true", help="Count what would be ingested without doing it")

    args = parser.parse_args()
    ingest_sessions(
        repo_filter=args.repo,
        incremental=not args.all,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
