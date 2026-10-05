"""Qdrant vector store wrapper: named collections, metadata, similarity search."""
import hashlib
import re

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    Range,
    VectorParams,
)

from app.core.config.settings import get_settings


def _payload_filter(
    where: dict | None, ranges: dict[str, tuple[int, int]] | None = None
) -> Filter | None:
    """Build a Qdrant filter from equality matches and inclusive (low, high) ranges, or None."""
    conditions = [
        FieldCondition(key=key, match=MatchValue(value=value)) for key, value in (where or {}).items()
    ]
    conditions += [
        FieldCondition(key=key, range=Range(gte=low, lte=high))
        for key, (low, high) in (ranges or {}).items()
    ]
    return Filter(must=conditions) if conditions else None


def collection_name(base: str, chunking: str, embedding: str) -> str:
    """Build the Qdrant collection name for a chunking x embedding combination."""
    return f"{base}__{chunking}__{embedding}"


# Marks the collections of a Grafo de conhecimento, so they never read as an Índice.
_GRAPH_MARKER = "__kg_"

# A Base name becomes the first segment of every collection_name() (and, through it,
# every graph_collection_names()). "__" is the separator between segments, so a Base
# name containing it could split into the wrong (base, chunking, embedding) when
# parse_collection_name()/collection_base() read it back, or hide a plain Índice as a
# Grafo collection (or vice versa) if it contains the "__kg_" marker specifically.
MAX_BASE_NAME_LENGTH = 64
_BASE_NAME_RE = re.compile(
    rf"^\w(?:[\w -]{{0,{MAX_BASE_NAME_LENGTH - 2}}}\w)?$", re.UNICODE
)


def validate_base_name(name: str) -> None:
    """Raise ValueError (message in PT-BR, shown as-is in the UI) if `name` is not a
    safe Base name: it would collide with, or be misread as, another Base's or a
    Grafo's Qdrant collection.
    """
    if "__" in name:
        raise ValueError(
            'Nome da base não pode conter "__": esse trecho separa base, corte e '
            "embedding (e marca o Grafo de conhecimento) no nome da coleção."
        )
    if not _BASE_NAME_RE.fullmatch(name):
        raise ValueError(
            f"Nome da base deve ter de 1 a {MAX_BASE_NAME_LENGTH} caracteres (letras, "
            "números, espaços, hífens ou underscores simples), sem espaços nas pontas."
        )


def graph_collection_names(
    base: str, chunking: str, embedding: str, extractor: str
) -> tuple[str, str]:
    """The (entities, relations) collections of an Índice's Grafo de conhecimento.

    They extend the Índice's name, so collection_base() finds the Base they belong to, and
    carry the LLM extrator (sanitized: Qdrant names take no '/' or ':'). A name
    that had to change gets a short hash of the original, so two LLMs never share one.
    """
    index = collection_name(base, chunking, embedding)
    llm = re.sub(r"[^A-Za-z0-9.-]+", "-", extractor).strip("-")
    if llm != extractor:
        llm += "-" + hashlib.sha1(extractor.encode()).hexdigest()[:8]
    return f"{index}{_GRAPH_MARKER}ent__{llm}", f"{index}{_GRAPH_MARKER}rel__{llm}"


def parse_collection_name(name: str) -> tuple[str, str, str] | None:
    """Split an Índice's collection name into (base, chunking, embedding); None if it is not one."""
    if _GRAPH_MARKER in name:
        return None
    parts = name.rsplit("__", 2)
    return (parts[0], parts[1], parts[2]) if len(parts) == 3 else None


def graph_entities_index(name: str) -> str | None:
    """The Índice whose Grafo this entities collection holds; None for any other collection."""
    index, marker, rest = name.partition(_GRAPH_MARKER)
    if not marker or not rest.startswith("ent__") or parse_collection_name(index) is None:
        return None
    return index


def collection_base(name: str) -> str | None:
    """The Base an Índice's or Grafo's collection belongs to; None for any other collection.

    Parsed from the Índice's name, never matched by prefix: Base "viagem" must
    not claim "viagem2__..." or "viagem__x__...".
    """
    parsed = parse_collection_name(name.split(_GRAPH_MARKER, 1)[0])
    return parsed[0] if parsed else None


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

    def delete_collection(self, name: str) -> None:
        """Drop the collection if it exists."""
        if self._client.collection_exists(name):
            self._client.delete_collection(name)

    def delete_base(self, base: str) -> list[str]:
        """Drop every Índice of the Base and the Grafos built from them; return their names."""
        names = [name for name in self.list_collections() if collection_base(name) == base]
        for name in names:
            self._client.delete_collection(name)
        return names

    def count(self, name: str) -> int:
        """Number of points in the collection."""
        return self._client.count(name).count

    def add(
        self,
        name: str,
        vectors: list[list[float]],
        payloads: list[dict],
        start_id: int | None = None,
    ) -> None:
        """Insert vectors with their metadata payloads under sequential ids.

        `start_id` saves a count() round trip when the caller tracks the ids.
        """
        if len(vectors) != len(payloads):
            raise ValueError("vectors and payloads must have the same length")
        first = self.count(name) if start_id is None else start_id
        points = [
            PointStruct(id=first + i, vector=vector, payload=payload)
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
        ranges: dict[str, tuple[int, int]] | None = None,
    ) -> list[dict]:
        """Return points matching a payload filter (no similarity ranking)."""
        points, _ = self._client.scroll(
            collection_name=name,
            scroll_filter=_payload_filter(where, ranges),
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
        return [{"id": point.id, "payload": point.payload} for point in points]
