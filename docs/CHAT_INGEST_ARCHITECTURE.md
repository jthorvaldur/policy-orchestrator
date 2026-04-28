# Chat Ingest Architecture

## Goal
Every Claude Code session from any repo gets chunked, embedded, and stored in Qdrant so future sessions can semantically search past conversations.

## Data Source
```
~/.claude/projects/
├── -Users-jthor-GitHub-div-legal/
│   ├── UUID.jsonl              <- session transcript
│   └── memory/                 <- agent memory (separate concern)
├── -Users-jthor-d72/
│   ├── UUID1.jsonl
│   ├── UUID2.jsonl
│   └── UUID3.jsonl
└── ...16 project dirs, 1793 sessions, 33K lines total
```

### JSONL format
```jsonl
{"type": "user", "message": {"role": "user", "content": "text..."}}
{"type": "assistant", "message": {"role": "assistant", "content": [{"type": "thinking", ...}, {"type": "text", "text": "..."}]}}
{"type": "system", "message": {...}}
```

Key fields to extract:
- `type == "user"` → `message.content` (string)
- `type == "assistant"` → `message.content` (list of blocks, filter for `type == "text"`, extract `.text`)
- Skip: system, permission-mode, queue-operation, file-history-snapshot, agent-name, custom-title

## Qdrant Collection: `claude_sessions`

```yaml
collection: claude_sessions
vector_dim: 768           # nomic-embed-text via Ollama
distance: Cosine

# Point schema
id: UUID (generated per chunk)
vector: float[768]
payload:
  session_id: str         # UUID from filename
  project: str            # project dir name (e.g. "-Users-jthor-GitHub-div-legal")
  repo: str               # extracted repo name (e.g. "div_legal")
  role: str               # "user" or "assistant"
  turn_index: int         # message ordinal within session
  chunk_index: int        # chunk ordinal within message
  content_preview: str    # first 200 chars
  date: str               # from file mtime or first message timestamp
  text: str               # full chunk text (for retrieval display)
```

## Pipeline: `scripts/ingest_sessions.py`

```
discover_sessions()
  ~/.claude/projects/*/*.jsonl
    ↓
parse_session(jsonl_path) → list[Turn]
  Turn = {role, content, turn_index}
    ↓
for each Turn:
  chunk_text(content, target=512 tokens, overlap=64)
    ↓
  for each chunk:
    vector = embed_text(chunk)  # Ollama nomic-embed-text
    payload = {session_id, project, repo, role, turn_index, chunk_index, ...}
    batch.append(PointStruct(id=uuid, vector=vector, payload=payload))
    ↓
upsert_to_qdrant(batch, collection="claude_sessions", batch_size=100)
    ↓
save_state(embedded_session_ids)  # incremental — skip next run
```

## Existing Code to Reuse

| Component | Source | File |
|-----------|--------|------|
| Qdrant client | div_legal | `src/vectordb/qdrant_client.py` |
| Embedder (Ollama) | div_legal | `src/vectordb/embedder.py` |
| Chunker | div_legal | `src/vectordb/chunker.py` |
| Incremental state | div_legal | `src/scripts/embed_incremental.py` |
| Claude JSON parser | d72 | `src/tools/ingest_claude.py` |
| Config pattern | div_legal | `src/config.py` |

## CLI Integration

```bash
# Ingest all sessions from all projects
devctl ingest-sessions

# Ingest sessions from specific repo
devctl ingest-sessions --repo=div_legal

# Ingest only new sessions since last run
devctl ingest-sessions --incremental

# Search across all sessions
devctl search-sessions "filing strategy for May 5"

# Search within a repo's sessions
devctl search-sessions "order language objection" --repo=div_legal
```

## Per-Repo Propagation

Any repo can search its own sessions via:
```python
# In any repo's scripts or agent code:
from qdrant_client import QdrantClient
client = QdrantClient(host="localhost", port=6333)
results = client.search(
    collection_name="claude_sessions",
    query_vector=embed_text("what did we discuss about X"),
    query_filter=Filter(must=[
        FieldCondition(key="repo", match=MatchValue(value="div_legal"))
    ]),
    limit=10,
)
```

Or via the control plane:
```bash
devctl search-sessions "what embedding model for legal docs" --repo=div_legal
```

## Requirements
- Qdrant running locally (`docker run -d -p 6333:6333 qdrant/qdrant`)
- Ollama running with nomic-embed-text (`ollama pull nomic-embed-text`)
- Python: `qdrant-client`, `httpx` (for Ollama API)

## Dependencies to add to policy-orchestrator
```toml
dependencies = [
    "pyyaml>=6.0",
    "click>=8.1",
    "qdrant-client>=1.9",
    "httpx>=0.27",
]
```
