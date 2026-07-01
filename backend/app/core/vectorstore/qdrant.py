"""Qdrant vector store wrapper: named collections, metadata, similarity search."""
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

from app.core.config.settings import get_settings


def _payload_filter(where: dict | None) -> Filter | None:
    """Build a Qdrant equality filter from a payload dict, or None."""
    if not where:
        return None
    return Filter(
        must=[
            FieldCondition(key=key, match=MatchValue(value=value))
            for key, value in where.items()
        ]
    )


def collection_name(base: str, chunking: str, embedding: str) -> str:
    """Build the Qdrant collection name for a chunking x embedding combination."""
    return f"{base}__{chunking}__{embedding}"


class QdrantStore:
    """Thin wrapper over qdrant-client for the project's collection conventions."""

    def __init__(self, client: QdrantClient | None = None) -> None:
        self._client = client or QdrantClient(url=get_settings().qdrant_url)

    def list_collections(self) -> list[str]:
        """Return the names of all collections in the store."""
        return [c.name for c in self._client.get_collections().collections]

    def ensure_collection(self, name: str, dimension: int) -> None:
        """Create the collection (cosine distance) if it does not exist yet."""
        if self._client.collection_exists(name):
            return
        self._client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=dimension, distance=Distance.COSINE),
        )

    def add(
        self,
        name: str,
        vectors: list[list[float]],
        payloads: list[dict],
    ) -> None:
        """Insert vectors with their metadata payloads under sequential ids."""
        if len(vectors) != len(payloads):
            raise ValueError("vectors and payloads must have the same length")
        count = self._client.count(name).count
        points = [
            PointStruct(id=count + i, vector=vector, payload=payload)
            for i, (vector, payload) in enumerate(zip(vectors, payloads))
        ]
        self._client.upsert(collection_name=name, points=points)

    def search(
        self,
        name: str,
        query_vector: list[float],
        top_k: int = 5,
        where: dict | None = None,
        with_vectors: bool = False,
    ) -> list[dict]:
        """Return the nearest points as {"id", "score", "payload"[, "vector"]}."""
        response = self._client.query_points(
            collection_name=name,
            query=query_vector,
            limit=top_k,
            query_filter=_payload_filter(where),
            with_vectors=with_vectors,
        )
        results = []
        for point in response.points:
            item = {"id": point.id, "score": point.score, "payload": point.payload}
            if with_vectors:
                item["vector"] = list(point.vector)
            results.append(item)
        return results

    def scroll(
        self,
        name: str,
        where: dict | None = None,
        limit: int = 1000,
    ) -> list[dict]:
        """Return points matching a payload filter (no similarity ranking)."""
        points, _ = self._client.scroll(
            collection_name=name,
            scroll_filter=_payload_filter(where),
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
        return [{"id": point.id, "payload": point.payload} for point in points]
