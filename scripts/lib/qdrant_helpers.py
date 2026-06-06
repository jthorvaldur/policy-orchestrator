"""Qdrant client helpers — shared across all vector scripts."""

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

QDRANT_HOST = "localhost"
QDRANT_PORT = 6333
VECTOR_DIM = 768
DISTANCE = Distance.COSINE

# Ports whose server version differs from the installed qdrant-client by more
# than one minor version. The client emits a UserWarning on every connection to
# these, even though the REST API works fine for compatible requests. We skip
# the compatibility check only for these ports to silence the cosmetic warning
# without disabling the check globally.
#   :8333 -> qdrant-research, server v1.14.0 (client is v1.17.x)
COMPAT_CHECK_SKIP_PORTS = {8333}


def connect(port: int = QDRANT_PORT, host: str = QDRANT_HOST, **kwargs) -> QdrantClient:
    """Build a QdrantClient, skipping the version-compat check for known
    version-skewed servers (see COMPAT_CHECK_SKIP_PORTS)."""
    if port in COMPAT_CHECK_SKIP_PORTS:
        kwargs.setdefault("check_compatibility", False)
    return QdrantClient(host=host, port=port, **kwargs)


def get_client() -> QdrantClient:
    return connect(QDRANT_PORT)


def ensure_collection(client: QdrantClient, name: str):
    existing = [c.name for c in client.get_collections().collections]
    if name not in existing:
        client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=VECTOR_DIM, distance=DISTANCE),
        )
