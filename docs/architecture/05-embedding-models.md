# Embedding & ML Models

## Model Stack

| Model | Type | Dim | Backend | Purpose |
|-------|------|-----|---------|---------|
| BAAI/bge-base-en-v1.5 | Dense embedding | 768 | sentence-transformers (PyTorch Metal) | Primary semantic search |
| prithivida/Splade_PP_en_v1 | Sparse embedding | variable | fastembed (ONNX) | Keyword-aware hybrid search |
| cross-encoder/ms-marco-MiniLM-L-6-v2 | Cross-encoder | - | sentence-transformers | Result reranking |
| llama3.1:8b | LLM | - | Ollama | Fact extraction, classification |
| gemma4:12b | Vision LLM | - | Ollama | Image/screenshot → markdown |
| llava:13b | Vision LLM | - | Ollama | Fallback image analysis |

## docvec Embedding Service (Port 8100)

**Repo:** `docvec/src/docvec/service.py`

Always-warm FastAPI service. Loads all 3 embedding models once on startup (~10s), then serves instantly.

### Endpoints

```
GET  /health                → { status, models: {dense, sparse, reranker} }
POST /embed                 → { texts: [...] } → { vectors: [[768 floats], ...] }
POST /embed/sparse          → { texts: [...] } → { embeddings: [{indices, values}, ...] }
POST /embed/hybrid          → { text: "..." } → { dense: [...], sparse: {indices, values} }
POST /rerank                → { query, results, text_key, limit } → { results: [...] }
```

### Auto-Detection (Transparent)

All consumers (search_unified.py, ingest_sessions.py) automatically use the service when it's running:

```python
# In docvec/embedder.py — one-shot health check per process
def _try_service() -> bool:
    global _service_checked, _service_ok
    if not _service_checked:
        resp = httpx.get("http://localhost:8100/health", timeout=1.0)
        _service_ok = resp.status_code == 200
        _service_checked = True
    return _service_ok

# If service is up → HTTP call (0.1s)
# If service is down → in-process model load (1.5s first call, then cached)
```

### LaunchAgent (Always Running)

```xml
<!-- ~/Library/LaunchAgents/com.jthor.docvec-service.plist -->
<key>ProgramArguments</key>
<array>
    <string>/Users/jthor/.local/bin/uv</string>
    <string>run</string>
    <string>--directory</string>
    <string>/Users/jthor/GitHub/docvec</string>
    <string>--extra</string>
    <string>service</string>
    <string>uvicorn</string>
    <string>docvec.service:app</string>
    <string>--host</string>
    <string>127.0.0.1</string>
    <string>--port</string>
    <string>8100</string>
</array>
<key>KeepAlive</key><true/>
<key>RunAtLoad</key><true/>
```

### Backend Selection

```python
from docvec.config import EmbedConfig

# Options: st | fastembed | tei | ollama | service
config = EmbedConfig(embed_backend="st")  # default — auto-detects service

# Force specific backend
config = EmbedConfig(embed_backend="service")    # fail if service down
config = EmbedConfig(embed_backend="ollama")     # nomic-embed-text via Ollama
config = EmbedConfig(embed_backend="tei")        # HuggingFace TEI server
```

## GPU Workers (Vast.ai Batch Embedding)

**Repo:** `gpu-workers/`

For large-scale embedding (full re-embed of 1.7M docs), provision GPU instances:

```bash
gpuw up 2xa40          # 2x A40, 90GB VRAM, ~$1.50/hr
gpuw upload data/ ~/data/
gpuw run embed_hybrid --input ~/data/md/
gpuw download ~/data/results/ ./results/
gpuw down
```

**Throughput:** 150 chunks/sec (GPU) vs 3-4/sec (local M4)
**Cost:** Full re-embed (1.7M docs) ≈ $1.50 (30 min on 2xA40)

### Available Specs

| Spec | GPU | VRAM | Price/hr | Use Case |
|------|-----|------|----------|----------|
| `2xa40` | 2x A40 | 90GB | ~$1.50 | Batch embedding (default) |
| `4090` | RTX 4090 | 24GB | ~$0.40 | Budget single-GPU |
| `l40s` | L40S | 48GB | ~$1.00 | Balanced |
| `h100` | H100 | 80GB | ~$3.00 | Max throughput |

## Hybrid Search Strategy

Every search uses **two-stage retrieval**:

```
Query → embed_hybrid() → { dense_vector, sparse_vector }
                              ↓                    ↓
                     Qdrant HNSW ANN      Qdrant inverted index
                     (semantic match)     (keyword match)
                              ↓                    ↓
                         RRF Fusion (Reciprocal Rank Fusion)
                              ↓
                     Top-K candidates (diverse pool)
                              ↓
                     Cross-encoder rerank (precision)
                              ↓
                     Content fingerprint dedup
                              ↓
                     Final results (20 default)
```

**Why hybrid?** Legal documents are keyword-heavy (statute numbers, case names, specific dates). Dense-only search misses exact matches. Sparse-only misses semantic similarity. Hybrid + reranking gives best of both.

## Search Deduplication

Two-tier dedup applied before reranking:

1. **Content fingerprint** — normalize text (lowercase, collapse whitespace), hash first 500 chars. Same PDF ingested from 3 email sources → caught.
2. **doc_id dedup** — keep highest-scored chunk per document.

Display shows `[+N similar]` for collapsed duplicates.

## Ollama (Local LLM Inference)

```bash
# Required models
ollama pull llama3.1:8b      # Fact extraction, classification
ollama pull gemma4:12b       # Vision (screenshots → markdown)
```

**Usage in pipeline:**
- Fact extraction: structured prompt, temperature 0.1, max 4000 chars/doc
- Topic classification: categorize documents
- Image summarization: legal-focused vision prompt
- Contradiction detection: compare fact pairs

**Port:** 11434 (default)

## AWS Lambda Equivalent

| Local | AWS | Notes |
|-------|-----|-------|
| docvec service (:8100) | Lambda + EFS (model cache) | Or SageMaker endpoint for warm inference |
| Ollama (llama3.1:8b) | Bedrock (Claude Haiku) | Or SageMaker with vLLM |
| GPU Workers (Vast.ai) | SageMaker Batch Transform | Same models, managed scaling |
| sentence-transformers | Lambda with EFS | Models cached on EFS, cold start ~30s |
