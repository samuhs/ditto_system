"""Build an Índice's Grafo de conhecimento on demand, as a LangGraph StateGraph.

    START -> load_chunks -> [Send("extract", chunk) per chunk] -> merge -> write -> END

Each chunk is extracted on its own branch (run in parallel up to max_concurrency)
and the results accumulate through a reducer, then are consolidated without an LLM
(names, aliases, synonyms by spelling: see consolidation.py).
"""
import hashlib
import logging
import operator
import threading
from abc import ABC, abstractmethod
from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from datetime import datetime, timezone
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from app.core.graph.cache import ExtractionCache, extraction_key, prompt_version
from app.core.graph.consolidation import consolidate, link_synonyms
from app.core.graph.extraction import Extraction, extract
from app.core.graph.knowledge import (
    GraphEntity,
    GraphRelation,
    KnowledgeGraph,
    index_chunks,
    load_graph,
    write_graph,
)
from app.core.llm.base import LLM
from app.core.prompts import load_prompt
from app.core.registry import Registry
from app.core.vectorstore.qdrant import QdrantStore, graph_collection_names

logger = logging.getLogger(__name__)


class GraphBuildError(RuntimeError):
    """The graph could not be built (no chunk could be extracted)."""


class GraphBuildPaused(RuntimeError):
    """A pause was requested before every chunk was extracted; nothing was written.

    The chunks already extracted are in the extraction cache: the next build
    asks the LLM extrator only for the others.
    """


# Opens the Índice's embedder for the write step (a lease the caller controls).
EmbedderScope = Callable[[], AbstractContextManager]


def chunks_fingerprint(chunks: dict[int, str]) -> str:
    """Hash of the Índice's chunk ids and texts, as the graph's chunk ids refer to them.

    Re-ingesting the Índice changes it, so a graph pointing at old ids is rebuilt.
    """
    digest = hashlib.sha256()
    for cid in sorted(chunks):
        digest.update(f"{cid}\0{chunks[cid]}\0".encode())
    return digest.hexdigest()[:16]


class ChunkExtraction(TypedDict):
    chunk_id: int
    extraction: Extraction | None  # None: the LLM call failed


class BuildState(TypedDict, total=False):
    chunks: dict[int, str]
    extractions: Annotated[list[ChunkExtraction], operator.add]
    entities: list[GraphEntity]
    relations: list[GraphRelation]
    stats: dict


def _stats(extractions: list[ChunkExtraction], entities, relations) -> dict:
    read = [x["extraction"] for x in extractions if x["extraction"] is not None]
    failed = sum(e.failed_lines for e in read)
    valid = sum(len(e.entities) + len(e.relations) for e in read)
    return {
        "entities": len(entities),
        "relations": len(relations),
        "chunks": len(extractions),
        "lines": valid + failed,
        "failed_lines": failed,
        "failed_chunks": len(extractions) - len(read),
    }


class GraphBuilder(ABC):
    """Builds and stores the Grafo de conhecimento of one Índice."""

    @abstractmethod
    def build(
        self, store: QdrantStore, base: str, chunking: str, embedding: str,
        embedder_scope: EmbedderScope,
    ) -> None:
        """Extract the Índice's graph and write it to its collections.

        `embedder_scope` is opened only to embed the entities and relations, after
        the extraction, so the caller decides what is in memory at each step.
        """


graph_builder_registry: Registry[type[GraphBuilder]] = Registry("graph_builder")


class LLMGraphBuilder(GraphBuilder):
    """Extracts each chunk's entities and relations with the LLM extrator."""

    def __init__(
        self,
        llm: LLM,
        extractor: str,
        prompt: str | None = None,
        max_concurrency: int = 1,
        cache: ExtractionCache | None = None,
        should_stop: Callable[[], bool] | None = None,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> None:
        self._llm = llm
        self._extractor = extractor
        self._prompt = prompt or load_prompt("graph", "extract")
        self._max_concurrency = max_concurrency
        self._cache = cache
        self._should_stop = should_stop or (lambda: False)
        self._on_progress = on_progress or (lambda done, total: None)

    def _flow(self, store, base, chunking, embedding, embedder_scope):
        llm, prompt, extractor, cache = self._llm, self._prompt, self._extractor, self._cache
        names = graph_collection_names(base, chunking, embedding, extractor)
        progress = {"extracted": 0, "total": 0}
        progress_lock = threading.Lock()

        def tick(extracted: int = 1) -> None:
            with progress_lock:
                progress["extracted"] += extracted
                self._on_progress(progress["extracted"], progress["total"])

        def load_chunks(state: BuildState) -> dict:
            chunks = index_chunks(store, base, chunking, embedding)
            texts = {cid: p.get("text", "") for cid, p in chunks.items()}
            # Chunks some earlier build already extracted (any Índice with this chunking).
            keys = {cid: extraction_key(text, extractor, prompt) for cid, text in texts.items()}
            known = cache.get_many(list(keys.values())) if cache else {}
            cached = [
                {"chunk_id": cid, "extraction": known[key]}
                for cid, key in keys.items() if key in known
            ]
            progress["total"] = len(texts)
            tick(len(cached))
            return {"chunks": texts, "extractions": cached}

        def fan_out(state: BuildState) -> list[Send] | str:
            done = {x["chunk_id"] for x in state.get("extractions", [])}
            sends = [
                Send("extract", {"chunk_id": cid, "text": text})
                for cid, text in state["chunks"].items()
                if cid not in done
            ]
            return sends or "merge"  # an empty Índice still yields an (empty) graph

        def extract_chunk(task: dict) -> dict:
            # Checkpoint: a chunk not started before a pause is left for the next build.
            if self._should_stop():
                raise GraphBuildPaused("pause requested while building the Grafo")
            try:
                found = extract(llm, task["text"], prompt)
            except Exception as exc:  # noqa: BLE001  one chunk never fails the graph
                logger.warning("graph extraction failed for chunk %s: %s", task["chunk_id"], exc)
                found = None
            # A failed call is not cached: the next build asks for that chunk again.
            if found is not None and cache is not None:
                cache.put(extraction_key(task["text"], extractor, prompt), extractor, prompt, found)
            tick()
            return {"extractions": [{"chunk_id": task["chunk_id"], "extraction": found}]}

        def merge(state: BuildState) -> dict:
            extractions = state.get("extractions", [])
            if extractions and all(x["extraction"] is None for x in extractions):
                raise GraphBuildError("the LLM extrator failed on every chunk")
            entities, relations = consolidate(extractions)
            return {
                "entities": link_synonyms(entities),
                "relations": relations,
                "stats": _stats(extractions, entities, relations),
            }

        def write(state: BuildState) -> dict:
            meta = {
                "extractor": extractor, "prompt": prompt, "stats": state["stats"],
                "prompt_version": prompt_version(prompt),
                "chunks_fingerprint": chunks_fingerprint(state["chunks"]),
                "built_at": datetime.now(timezone.utc).isoformat(),
            }
            # The Índice's embedder is leased only here (memory profile), to embed
            # the entities and relations.
            with embedder_scope() as embedder:
                write_graph(store, names, state["entities"], state["relations"], embedder, meta)
            return {}

        flow = StateGraph(BuildState)
        flow.add_node("load_chunks", load_chunks)
        flow.add_node("extract", extract_chunk)
        flow.add_node("merge", merge)
        flow.add_node("write", write)
        flow.add_edge(START, "load_chunks")
        flow.add_conditional_edges("load_chunks", fan_out, ["extract", "merge"])
        flow.add_edge("extract", "merge")
        flow.add_edge("merge", "write")
        flow.add_edge("write", END)
        return flow.compile()

    def build(self, store, base, chunking, embedding, embedder_scope) -> None:
        self._flow(store, base, chunking, embedding, embedder_scope).invoke(
            {"extractions": []}, config={"max_concurrency": self._max_concurrency}
        )


graph_builder_registry.register("llm", LLMGraphBuilder)


def current_graph(
    store: QdrantStore, base: str, chunking: str, embedding: str, extractor: str,
    prompt: str | None = None,
) -> KnowledgeGraph | None:
    """The Índice's graph for this LLM extrator, or None if it is missing or stale.

    Stale: built with another extraction prompt, or from chunks the Índice no
    longer has (re-ingested), since its chunk ids would point at the wrong text.
    """
    graph = load_graph(store, base, chunking, embedding, extractor)
    if graph is None:
        return None
    prompt = prompt or load_prompt("graph", "extract")
    texts = {cid: p.get("text", "") for cid, p in graph.chunks.items()}
    if (
        graph.meta.get("prompt_version") != prompt_version(prompt)
        or graph.meta.get("chunks_fingerprint") != chunks_fingerprint(texts)
    ):
        return None
    return graph


def build_graph(
    store: QdrantStore,
    base: str,
    chunking: str,
    embedding: str,
    extractor: str,
    llm: LLM,
    embedder_scope: EmbedderScope,
    prompt: str | None = None,
    max_concurrency: int = 1,
    cache: ExtractionCache | None = None,
    should_stop: Callable[[], bool] | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> KnowledgeGraph:
    """Build (or rebuild) the Índice's graph for this LLM extrator and return it.

    Raises GraphBuildPaused when `should_stop` turns true during the extraction.
    """
    builder = graph_builder_registry.get("llm")(
        llm=llm, extractor=extractor, prompt=prompt, max_concurrency=max_concurrency,
        cache=cache, should_stop=should_stop, on_progress=on_progress,
    )
    builder.build(store, base, chunking, embedding, embedder_scope)
    graph = load_graph(store, base, chunking, embedding, extractor)
    assert graph is not None  # build always writes the metadata point last
    return graph


def ensure_graph(
    store: QdrantStore,
    base: str,
    chunking: str,
    embedding: str,
    extractor: str,
    llm: LLM,
    embedder,
    prompt: str | None = None,
    max_concurrency: int = 1,
    cache: ExtractionCache | None = None,
) -> KnowledgeGraph:
    """The Índice's current graph for this LLM extrator, built first if missing or stale."""
    graph = current_graph(store, base, chunking, embedding, extractor, prompt)
    if graph is not None:
        return graph
    return build_graph(
        store, base, chunking, embedding, extractor, llm, lambda: nullcontext(embedder),
        prompt=prompt, max_concurrency=max_concurrency, cache=cache,
    )
