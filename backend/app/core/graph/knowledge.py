"""An Índice's Grafo de conhecimento: stored in two Qdrant collections, read back as networkx.

Entities and relations each get a vector (from the Índice's embedder) and a payload
with the ids of the chunks they came from. The entities collection also holds one
metadata point (LLM extrator, prompt, stats), written last: a graph without it was
never finished.
"""
import networkx as nx
from pydantic import BaseModel

from app.core.vectorstore.qdrant import QdrantStore, collection_name, graph_collection_names

_META_ID = 0
_META, _ENTITY, _RELATION = "meta", "entity", "relation"


def normalize_name(name: str) -> str:
    """The key entities are merged by: casefolded, with single spaces."""
    return " ".join(name.casefold().split())


class GraphEntity(BaseModel):
    """An entity of the Grafo de conhecimento, merged across the chunks that mention it."""

    key: str
    name: str
    type: str
    description: str
    chunk_ids: list[int]
    # Other names of the same entity (nicknames between parentheses).
    aliases: list[str] = []
    # Keys of entities with a close name, by cosine; linked, never merged.
    synonyms: dict[str, float] = {}


class GraphRelation(BaseModel):
    """A relation of the Grafo de conhecimento between two entity keys."""

    source: str
    target: str
    source_key: str
    target_key: str
    keywords: str
    description: str
    chunk_ids: list[int]

    def fact(self) -> str:
        """One line for the answer prompt."""
        return f"{self.source} → {self.target}: {self.description}"


def _entity_text(entity: GraphEntity) -> str:
    return f"{entity.name}: {entity.description}"


def _relation_text(relation: GraphRelation) -> str:
    return f"{relation.keywords} {relation.source} {relation.target} {relation.description}"


def _all_points(store: QdrantStore, name: str, where: dict | None = None) -> list[dict]:
    return store.scroll(name, where=where, limit=max(store.count(name), 1))


def index_chunks(store: QdrantStore, base: str, chunking: str, embedding: str) -> dict[int, dict]:
    """Every chunk of the Índice, by point id, as its payload."""
    name = collection_name(base, chunking, embedding)
    return {p["id"]: p["payload"] for p in _all_points(store, name)}


def write_graph(
    store: QdrantStore,
    names: tuple[str, str],
    entities: list[GraphEntity],
    relations: list[GraphRelation],
    embedder,
    meta: dict,
) -> None:
    """Replace the graph's collections with these entities, relations and metadata."""
    entities_name, relations_name = names
    entity_vectors = embedder.embed_documents([_entity_text(e) for e in entities]) if entities else []
    relation_vectors = (
        embedder.embed_documents([_relation_text(r) for r in relations]) if relations else []
    )
    # The vectors' own length: a query-cache embedder may not know it before loading.
    dimension = len((entity_vectors or relation_vectors or [[]])[0]) or embedder.dimension
    for name in names:
        store.delete_collection(name)
        store.ensure_collection(name, dimension)
    if entities:
        store.add(
            entities_name, entity_vectors,
            [{"record": _ENTITY, **e.model_dump()} for e in entities],
            start_id=_META_ID + 1,
        )
    if relations:
        store.add(
            relations_name, relation_vectors,
            [{"record": _RELATION, **r.model_dump()} for r in relations],
            start_id=0,
        )
    # Last: its presence marks the graph as complete. Cosine needs a non-zero vector.
    unit = [1.0] + [0.0] * (dimension - 1)
    store.add(entities_name, [unit], [{"record": _META, **meta}], start_id=_META_ID)


class KnowledgeGraph:
    """A built Grafo de conhecimento, with its chunks and a networkx view for expansion."""

    def __init__(
        self,
        store: QdrantStore,
        names: tuple[str, str],
        meta: dict,
        entities: list[GraphEntity],
        relations: list[GraphRelation],
        chunks: dict[int, dict],
    ) -> None:
        self._store = store
        self._entities_name, self._relations_name = names
        self._meta = meta
        self.entities = {e.key: e for e in entities}
        self.relations = relations
        self.chunks = chunks
        self.graph = nx.Graph()
        self.graph.add_nodes_from(self.entities)
        self.graph.add_edges_from((r.source_key, r.target_key) for r in relations)

    @property
    def extractor(self) -> str:
        """The LLM extrator that built this graph."""
        return self._meta["extractor"]

    @property
    def meta(self) -> dict:
        """What the graph was built with: LLM extrator, prompt version, chunks, stats."""
        return dict(self._meta)

    @property
    def stats(self) -> dict:
        """Entities, relations, chunks, extraction lines and failures."""
        return dict(self._meta["stats"])

    def search_entities(self, vector: list[float], top_k: int) -> list[tuple[GraphEntity, float]]:
        """The entities nearest to the vector, with their similarity."""
        hits = self._store.search(self._entities_name, vector, top_k, where={"record": _ENTITY})
        return [(self.entities[h["payload"]["key"]], h["score"]) for h in hits]

    def search_relations(self, vector: list[float], top_k: int) -> list[tuple[GraphRelation, float]]:
        """The relations nearest to the vector, with their similarity."""
        if not self.relations:
            return []
        hits = self._store.search(self._relations_name, vector, top_k, where={"record": _RELATION})
        return [(GraphRelation.model_validate(h["payload"]), h["score"]) for h in hits]

    def specificity(self, key: str) -> float:
        """1 / the number of chunks the entity appears in (HippoRAG's node specificity)."""
        entity = self.entities.get(key)
        return 1.0 / max(len(entity.chunk_ids), 1) if entity else 0.0

    def neighbours(self, key: str) -> list[str]:
        """Entity keys one hop away."""
        return list(self.graph.neighbors(key)) if key in self.graph else []


def load_graph(
    store: QdrantStore, base: str, chunking: str, embedding: str, extractor: str
) -> KnowledgeGraph | None:
    """The finished graph of this Índice x LLM extrator, or None if there is none."""
    names = graph_collection_names(base, chunking, embedding, extractor)
    entities_name, relations_name = names
    existing = set(store.list_collections())
    if entities_name not in existing or relations_name not in existing:
        return None
    meta = _all_points(store, entities_name, where={"record": _META})
    if not meta:
        return None
    entities = [
        GraphEntity.model_validate(p["payload"])
        for p in _all_points(store, entities_name, where={"record": _ENTITY})
    ]
    relations = [
        GraphRelation.model_validate(p["payload"]) for p in _all_points(store, relations_name)
    ]
    return KnowledgeGraph(
        store, names, meta[0]["payload"], entities, relations,
        index_chunks(store, base, chunking, embedding),
    )
