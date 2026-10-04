"""Índice/Grafo fingerprint (#21): what a Retomada compares against the current state.

Recorded on `experiment.config["fingerprint"]` when the Experimento is created and
refreshed at the start of every Retomada that is allowed to proceed. `_resumable_reason`
(backend/app/api/experiments.py) recomputes the current fingerprint and diffs it against
the stored one: a mismatch (a reingested Índice, a rebuilt or now-stale Grafo) blocks the
Retomada with a 409 listing what changed, in PT-BR for the UI. An Experimento created
before this feature has no stored fingerprint and is never blocked by this check.
"""
from app.core.graph.build import current_graph
from app.core.rag.base import rag_registry
from app.core.vectorstore.qdrant import QdrantStore, collection_name
from app.experiments.schemas import ExperimentConfig, index_pairs


def _pair_key(chunking: str, embedding: str) -> str:
    return f"{chunking}__{embedding}"


def uses_graph(config: ExperimentConfig) -> bool:
    """Whether any chosen RAG técnica queries a Grafo de conhecimento (needs graph_extractor)."""
    return bool(config.graph_extractor) and any(
        r in rag_registry.names() and rag_registry.get(r).uses_graph for r in config.rags
    )


def index_fingerprint(store: QdrantStore, base: str, chunking: str, embedding: str) -> dict:
    """Identity of one Índice's Qdrant collection: whether it exists, its point count, and
    an ingestion timestamp when its payload carries one.

    No ingestion pipeline stamps a timestamp on its payload today, so `ingested_at` is
    always None for now; reading it defensively here means a future pipeline that does
    record one is picked up without changing this fingerprint's shape. Point count alone
    already catches the common case: reingesting adds rows (ingest never replaces, only
    appends after `store.count`).
    """
    name = collection_name(base, chunking, embedding)
    if name not in store.list_collections():
        return {"exists": False, "points": 0, "ingested_at": None}
    sample = store.scroll(name, limit=1)
    ingested_at = sample[0]["payload"].get("ingested_at") if sample else None
    return {"exists": True, "points": store.count(name), "ingested_at": ingested_at}


def graph_fingerprint(
    store: QdrantStore, base: str, chunking: str, embedding: str, extractor: str
) -> dict | None:
    """Identity of the current Grafo de conhecimento `extractor` built for this Índice.

    None when there is none right now (missing, or stale per `current_graph`'s own
    currency check: a different GRAPH_VERSION, extraction prompt, or Índice chunks). A
    Retomada compares this like any other value, so a Grafo that went from present to
    None (or vice versa, or to a different `built_at`) is reported as changed.
    """
    graph = current_graph(store, base, chunking, embedding, extractor)
    if graph is None:
        return None
    meta = graph.meta
    return {
        "extractor": meta.get("extractor"),
        "chunks_fingerprint": meta.get("chunks_fingerprint"),
        "prompt_version": meta.get("prompt_version"),
        "built_at": meta.get("built_at"),
    }


def experiment_fingerprint(config: ExperimentConfig, store: QdrantStore) -> dict:
    """Every Índice (and, with a GraphRAG técnica, Grafo) fingerprint this config uses.

    Keyed by "chunking__embedding", one entry per distinct Índice pair the Experimento's
    Combinações read from (see `index_pairs`).
    """
    graphs = uses_graph(config)
    fingerprint: dict[str, dict] = {}
    for chunking, embedding in dict.fromkeys(index_pairs(config)):
        entry = {"index": index_fingerprint(store, config.base, chunking, embedding)}
        if graphs:
            entry["graph"] = graph_fingerprint(
                store, config.base, chunking, embedding, config.graph_extractor
            )
        fingerprint[_pair_key(chunking, embedding)] = entry
    return fingerprint


def fingerprint_changes(old: dict, new: dict) -> list[str]:
    """What changed between two `experiment_fingerprint` results, in PT-BR; [] if nothing did.

    One message per Índice pair whose Índice or Grafo diverged (added, removed pairs
    count as changed too, though that should not happen within one Experimento's config).
    """
    changes = []
    for key in sorted(set(old) | set(new)):
        chunking, _, embedding = key.partition("__")
        label = f"{chunking} × {embedding}"
        old_entry, new_entry = old.get(key), new.get(key)
        if old_entry is None or new_entry is None:
            changes.append(f"Índice {label} não faz mais parte do Experimento")
            continue
        if old_entry.get("index") != new_entry.get("index"):
            changes.append(f"Índice {label} foi reingerido")
        if old_entry.get("graph") != new_entry.get("graph"):
            changes.append(f"Grafo de conhecimento de {label} mudou")
    return changes
