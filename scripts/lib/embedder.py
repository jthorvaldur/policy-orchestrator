"""Ollama embedding client — shared across all vector scripts."""

import time

import httpx

OLLAMA_BASE_URL = "http://localhost:11434"
EMBEDDING_MODEL = "nomic-embed-text"


def embed_text(text: str, max_chars: int = 8000, max_retries: int = 3) -> list[float]:
    """Get 768-dim embedding vector via Ollama nomic-embed-text."""
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
