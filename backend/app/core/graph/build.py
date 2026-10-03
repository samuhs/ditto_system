"""Build an Índice's Grafo de conhecimento on demand, as a LangGraph StateGraph.

    START -> load_chunks -> [Send("extract", chunk) per chunk] -> merge -> write -> END

Each chunk is extracted on its own branch (run in parallel up to max_concurrency)
and the results accumulate through a reducer. Entities merge by normalized name;
relations by their pair of entity keys.
"""
import logging
import operator
from abc import ABC, abstractmethod
from collections import Counter
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from app.core.graph.extraction import Extraction, extract
from app.core.graph.knowledge import (
    GraphEntity,
    GraphRelation,
    KnowledgeGraph,
    index_chunks,
    load_graph,
    normalize_name,
    write_graph,
)
from app.core.llm.base import LLM
from app.core.prompts import load_prompt
from app.core.registry import Registry
from app.core.vectorstore.qdrant import QdrantStore, graph_collection_names

logger = logging.getLogger(__name__)


class GraphBuildError(RuntimeError):
    """The graph could not be built (no chunk could be extracted)."""


class ChunkExtraction(TypedDict):
    chunk_id: int
    extraction: Extraction | None  # None: the LLM call failed


class BuildState(TypedDict, total=False):
    chunks: dict[int, str]
    extractions: Annotated[list[ChunkExtraction], operator.add]
    entities: list[GraphEntity]
    relations: list[GraphRelation]
    stats: dict


def _join(texts: list[str]) -> str:
    """Distinct non-empty texts, in order, as one."""
    return " ".join(dict.fromkeys(t for t in texts if t))


def merge_extractions(
    extractions: list[ChunkExtraction],
) -> tuple[list[GraphEntity], list[GraphRelation]]:
    """Merge the chunks' entities by normalized name and relations by entity pair.

    An entity keeps its first spelling, the majority type and every description;
    both keep the ids of every chunk they came from.
    """
    entities: dict[str, dict] = {}
    relations: dict[tuple[str, str], dict] = {}
    for item in sorted(extractions, key=lambda x: x["chunk_id"]):
        found = item["extraction"]
        if found is None:
            continue
        chunk_id = item["chunk_id"]
        for e in found.entities:
            slot = entities.setdefault(
                normalize_name(e.name),
                {"name": e.name, "types": Counter(), "descriptions": [], "chunk_ids": set()},
            )
            slot["types"][e.type] += 1
            slot["descriptions"].append(e.description)
            slot["chunk_ids"].add(chunk_id)
        for r in found.relations:
            key = (normalize_name(r.source), normalize_name(r.target))
            slot = relations.setdefault(
                key,
                {"source": r.source, "target": r.target, "keywords": [], "descriptions": [],
                 "chunk_ids": set()},
            )
            slot["keywords"].append(r.keywords)
            slot["descriptions"].append(r.description)
            slot["chunk_ids"].add(chunk_id)
    merged_entities = [
        GraphEntity(
            key=key, name=s["name"], type=s["types"].most_common(1)[0][0],
            description=_join(s["descriptions"]), chunk_ids=sorted(s["chunk_ids"]),
        )
        for key, s in entities.items()
    ]
    merged_relations = [
        GraphRelation(
            source=s["source"], target=s["target"], source_key=source, target_key=target,
            keywords=_join(s["keywords"]), description=_join(s["descriptions"]),
            chunk_ids=sorted(s["chunk_ids"]),
        )
        for (source, target), s in relations.items()
    ]
    return merged_entities, merged_relations


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
        self, store: QdrantStore, base: str, chunking: str, embedding: str, embedder
    ) -> None:
        """Extract the Índice's graph and write it to its collections."""


graph_builder_registry: Registry[type[GraphBuilder]] = Registry("graph_builder")


class LLMGraphBuilder(GraphBuilder):
    """Extracts each chunk's entities and relations with the LLM extrator."""

    def __init__(
        self, llm: LLM, extractor: str, prompt: str | None = None, max_concurrency: int = 1
    ) -> None:
        self._llm = llm
        self._extractor = extractor
        self._prompt = prompt or load_prompt("graph", "extract")
        self._max_concurrency = max_concurrency

    def _flow(self, store, base, chunking, embedding, embedder):
        llm, prompt = self._llm, self._prompt
        names = graph_collection_names(base, chunking, embedding, self._extractor)

        def load_chunks(state: BuildState) -> dict:
            chunks = index_chunks(store, base, chunking, embedding)
            return {"chunks": {cid: p.get("text", "") for cid, p in chunks.items()}}

        def fan_out(state: BuildState) -> list[Send] | str:
            sends = [
                Send("extract", {"chunk_id": cid, "text": text})
                for cid, text in state["chunks"].items()
            ]
            return sends or "merge"  # an empty Índice still yields an (empty) graph

        def extract_chunk(task: dict) -> dict:
            try:
                found = extract(llm, task["text"], prompt)
            except Exception as exc:  # noqa: BLE001  one chunk never fails the graph
                logger.warning("graph extraction failed for chunk %s: %s", task["chunk_id"], exc)
                found = None
            return {"extractions": [{"chunk_id": task["chunk_id"], "extraction": found}]}

        def merge(state: BuildState) -> dict:
            extractions = state.get("extractions", [])
            if extractions and all(x["extraction"] is None for x in extractions):
                raise GraphBuildError("the LLM extrator failed on every chunk")
            entities, relations = merge_extractions(extractions)
            return {
                "entities": entities,
                "relations": relations,
                "stats": _stats(extractions, entities, relations),
            }

        def write(state: BuildState) -> dict:
            meta = {"extractor": self._extractor, "prompt": prompt, "stats": state["stats"]}
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

    def build(self, store, base, chunking, embedding, embedder) -> None:
        self._flow(store, base, chunking, embedding, embedder).invoke(
            {"extractions": []}, config={"max_concurrency": self._max_concurrency}
        )


graph_builder_registry.register("llm", LLMGraphBuilder)


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
) -> KnowledgeGraph:
    """The Índice's graph for this LLM extrator, built first if it does not exist yet."""
    graph = load_graph(store, base, chunking, embedding, extractor)
    if graph is not None:
        return graph
    builder = graph_builder_registry.get("llm")(
        llm=llm, extractor=extractor, prompt=prompt, max_concurrency=max_concurrency
    )
    builder.build(store, base, chunking, embedding, embedder)
    graph = load_graph(store, base, chunking, embedding, extractor)
    assert graph is not None  # build always writes the metadata point last
    return graph
