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


def collection_name(base: str, chunking: str, embedding: str) -> str:
    """Build the Qdrant collection name for a chunking x embedding combination."""
    return f"{base}__{chunking}__{embedding}"


class QdrantStore:
    """Thin wrapper over qdrant-client for the project's collection conventions."""

    def __init__(self, client: QdrantClient | None = None) -> None:
        self._client = client or QdrantClient(url=get_settings().qdrant_url)

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
    ) -> list[dict]:
        """Return the nearest points as {"score", "payload"}, optionally filtered."""
        query_filter = None
        if where:
            query_filter = Filter(
                must=[
                    FieldCondition(key=key, match=MatchValue(value=value))
                    for key, value in where.items()
                ]
            )
        response = self._client.query_points(
            collection_name=name,
            query=query_vector,
            limit=top_k,
            query_filter=query_filter,
        )
        return [{"score": point.score, "payload": point.payload} for point in response.points]
