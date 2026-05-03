"""Embedding client — delegates to docvec (BGE via sentence-transformers).

Falls back to Ollama nomic-embed-text if sentence-transformers unavailable.
"""
from docvec.config import EmbedConfig
from docvec.embedder import embed_text as _embed_text, embed_batch as _embed_batch

try:
    import sentence_transformers  # noqa: F401
    _config = EmbedConfig(embed_backend="st", dense_model="BAAI/bge-base-en-v1.5")
except ImportError:
    _config = EmbedConfig(
        embed_backend="ollama",
        ollama_url="http://localhost:11434",
        ollama_model="nomic-embed-text",
    )


def embed_text(text: str, max_chars: int = 8000, max_retries: int = 3) -> list[float]:
    """Get 768-dim embedding vector via BGE (preferred) or Ollama (fallback)."""
    if len(text) > max_chars:
        text = text[:max_chars]
    return _embed_text(text, config=_config)


def embed_batch(texts: list[str]) -> list[list[float]]:
    return _embed_batch(texts, config=_config)
