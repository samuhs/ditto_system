"""The Bases catalog: each Base's Índices and the Grafos de conhecimento built from them.

Read from the Qdrant collection names and each Grafo's metadata point, so it
always reflects what is stored, with no bookkeeping of its own.
"""
from pydantic import BaseModel

from app.core.graph.jobs import GraphBuildJob
from app.core.graph.knowledge import graph_meta
from app.core.vectorstore.qdrant import QdrantStore, graph_entities_index, parse_collection_name


class GraphSummary(BaseModel):
    """A finished Grafo de conhecimento of an Índice, built by one LLM extrator."""

    extractor: str
    entities: int
    relations: int
    # Share of the extraction lines the LLM extrator wrote that could not be read.
    failed_pct: float
    # ISO timestamp; None for a Grafo built before the date was recorded.
    built_at: str | None = None


class IndexSummary(BaseModel):
    """An Índice (chunking x embedding) of a Base."""

    chunking: str
    embedding: str
    chunks: int
    graphs: list[GraphSummary]


class BaseSummary(BaseModel):
    """A Base with its Índices; `in_use` says why it cannot be deleted now (None: it can)."""

    name: str
    indexes: list[IndexSummary]
    in_use: str | None = None
    # Grafo builds of this Base still running, queued or paused, with their progress.
    graph_builds: list[GraphBuildJob] = []


def _graph_summary(store: QdrantStore, entities_name: str) -> GraphSummary | None:
    """The Grafo's summary from its metadata point; None if it was never finished."""
    meta = graph_meta(store, entities_name)
    if meta is None:
        return None
    stats = meta.get("stats", {})
    lines = stats.get("lines", 0)
    failed = stats.get("failed_lines", 0)
    return GraphSummary(
        extractor=meta["extractor"],
        entities=stats.get("entities", 0),
        relations=stats.get("relations", 0),
        failed_pct=round(100 * failed / lines, 1) if lines else 0.0,
        built_at=meta.get("built_at"),
    )


def list_bases(store: QdrantStore) -> list[BaseSummary]:
    """Every Base, sorted by name, with its Índices and their finished Grafos."""
    names = sorted(store.list_collections())
    graphs: dict[str, list[GraphSummary]] = {}
    for name in names:
        index = graph_entities_index(name)
        if index is None:
            continue
        summary = _graph_summary(store, name)
        if summary is not None:
            graphs.setdefault(index, []).append(summary)
    bases: dict[str, list[IndexSummary]] = {}
    for name in names:
        parsed = parse_collection_name(name)
        if parsed is None:
            continue
        base, chunking, embedding = parsed
        bases.setdefault(base, []).append(IndexSummary(
            chunking=chunking, embedding=embedding, chunks=store.count(name),
            graphs=sorted(graphs.get(name, []), key=lambda g: g.extractor),
        ))
    return [BaseSummary(name=base, indexes=indexes) for base, indexes in sorted(bases.items())]
