# Fatia A — Plano 4: RAG — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar a recuperação e a geração de respostas: estender o `QdrantStore` para suportar os retrievers, implementar 4 retrievers (`similarity`, `mmr`, `multi_query`, `parent_document`) e 2 técnicas de RAG (`naive`, `agentic`) — tudo atrás de interface + registry e testável sem rede.

**Architecture:** Um subpacote `app/core/retrieval/` (interface Retriever + registry + 4 retrievers) e `app/core/rag/` (interface RAG + registry + NaiveRAG + AgenticRAG). Retrievers consomem `QdrantStore` + `Embedder`; técnicas de RAG consomem um `Retriever` + `LLM`. O AgenticRAG é um loop agêntico compacto e limitado sobre a interface `LLM` (sem LangGraph — esse fica para a Fatia B). Tudo injetável para testes sem rede.

**Tech Stack:** Python 3.11, qdrant-client, pytest. Sem dependências novas.

## Global Constraints

- **Código em inglês:** identificadores, docstrings e mensagens de erro em inglês. Apenas dados de domínio em PT-BR.
- PEP-8; docstrings nas funções públicas; comentários só quando agregam.
- Toda técnica plugável atrás de interface + registry (reusa `app.core.registry.Registry`).
- Sem duplicação: retrievers usam `QdrantStore`/`Embedder` do `core/`; RAG usa `Retriever` + `LLM`. Nunca instanciam clientes direto.
- **Testes sem rede:** `QdrantClient(":memory:")`; `Embedder`/`LLM`/`Retriever` injetados como fakes. Nenhum download de modelo, nenhuma chamada de API.
- Retrievers disponíveis: `similarity`, `mmr`, `multi_query`, `parent_document`. Técnicas de RAG: `naive`, `agentic`.
- venv de dev em `backend/.venv`. Rodar testes: `cd backend && ./.venv/bin/python -m pytest`. Saída pristina (zero warnings).
- Contrato de contexto: um retriever retorna `list[dict]`, cada dict com ao menos `text`, `score`, `source_doc`, `chunk_index` (campos vindos do payload da ingestão, mais `score`).
- Commits frequentes, um por task.

---

## File Structure

```
backend/
  app/core/vectorstore/qdrant.py     # estendido: search(+id,+with_vectors), scroll(...)
  app/core/retrieval/
    __init__.py                      # Retriever, retrieval_registry, build_retriever
    base.py                          # interface Retriever (ABC) + Registry + build_retriever + helpers de similaridade
    similarity.py                    # SimilarityRetriever
    mmr.py                           # MMRRetriever
    multi_query.py                   # MultiQueryRetriever
    parent_document.py               # ParentDocumentRetriever
  app/core/rag/
    __init__.py                      # RAG, RAGResult, rag_registry, build_rag
    base.py                          # interface RAG (ABC) + RAGResult + Registry + build_rag + prompt helpers
    naive.py                         # NaiveRAG
    agentic.py                       # AgenticRAG
  tests/
    test_vectorstore_retrieval.py    # extensões do QdrantStore
    test_retrievers.py               # similarity, mmr
    test_retrievers_advanced.py      # multi_query, parent_document
    test_rag_naive.py
    test_rag_agentic.py
```

---

### Task 1: Estender o QdrantStore (id, vetores, scroll)

**Files:**
- Modify: `backend/app/core/vectorstore/qdrant.py`
- Create: `backend/tests/test_vectorstore_retrieval.py`

**Interfaces:**
- Consumes: `qdrant_client`.
- Produces (alterações aditivas — não quebram o contrato atual):
  - `search(name, query_vector, top_k=5, where=None, with_vectors=False) -> list[dict]` — cada item agora inclui `"id"`; inclui `"vector"` quando `with_vectors=True` (caso contrário a chave `"vector"` não é incluída).
  - `scroll(name, where=None, limit=1000) -> list[dict]` — retorna pontos por filtro de payload (sem similaridade), cada item `{"id", "payload"}`.
  - Helper interno `_payload_filter(where)` reusado por `search` e `scroll`.

- [ ] **Step 1: Escrever o teste que falha**

`backend/tests/test_vectorstore_retrieval.py`:

```python
"""Tests for QdrantStore retrieval extensions (id, vectors, scroll)."""
import pytest
from qdrant_client import QdrantClient

from app.core.vectorstore.qdrant import QdrantStore


@pytest.fixture
def store():
    s = QdrantStore(client=QdrantClient(":memory:"))
    s.ensure_collection("c", dimension=3)
    s.add(
        "c",
        vectors=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        payloads=[
            {"source_doc": "a.txt", "chunk_index": 0, "text": "x"},
            {"source_doc": "a.txt", "chunk_index": 1, "text": "y"},
            {"source_doc": "b.txt", "chunk_index": 0, "text": "z"},
        ],
    )
    return s


def test_search_includes_id(store):
    hits = store.search("c", query_vector=[1.0, 0.0, 0.0], top_k=1)
    assert "id" in hits[0]
    assert hits[0]["payload"]["text"] == "x"


def test_search_with_vectors_returns_vector(store):
    hits = store.search("c", query_vector=[1.0, 0.0, 0.0], top_k=1, with_vectors=True)
    assert hits[0]["vector"] == [1.0, 0.0, 0.0]


def test_search_without_vectors_omits_vector_key(store):
    hits = store.search("c", query_vector=[1.0, 0.0, 0.0], top_k=1)
    assert "vector" not in hits[0]


def test_scroll_by_payload_filter(store):
    points = store.scroll("c", where={"source_doc": "a.txt"})
    texts = sorted(p["payload"]["text"] for p in points)
    assert texts == ["x", "y"]
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_vectorstore_retrieval.py -v`
Expected: FAIL (`search` ainda não inclui `id`; `scroll` não existe).

- [ ] **Step 3: Estender o `qdrant.py`**

Em `backend/app/core/vectorstore/qdrant.py`, refatore a construção do filtro para um helper e atualize `search`, adicionando `scroll`. Substitua o corpo do método `search` e adicione `_payload_filter` e `scroll` (mantenha `collection_name`, `__init__`, `ensure_collection`, `add` inalterados):

```python
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
```

`search`:

```python
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
```

Remova o antigo bloco de construção de `query_filter` inline do `search` (agora vem de `_payload_filter`).

- [ ] **Step 4: Rodar e ver passar (inclui a suíte toda)**

Run: `cd backend && ./.venv/bin/python -m pytest -v`
Expected: PASS — os 4 novos testes e todos os anteriores (o `search` continua devolvendo `score`/`payload`, agora também `id`; testes antigos não quebram). Zero warnings.

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/vectorstore/qdrant.py backend/tests/test_vectorstore_retrieval.py
git commit -m "feat: extend QdrantStore with point id, vectors, and scroll"
```

---

### Task 2: Interface de Retriever + similarity + mmr

**Files:**
- Create: `backend/app/core/retrieval/__init__.py`
- Create: `backend/app/core/retrieval/base.py`
- Create: `backend/app/core/retrieval/similarity.py`
- Create: `backend/app/core/retrieval/mmr.py`
- Create: `backend/tests/test_retrievers.py`

**Interfaces:**
- Consumes: `app.core.registry.Registry`, `app.core.vectorstore.QdrantStore`, `app.core.embedding.base.Embedder`.
- Produces:
  - `Retriever` (ABC) com `retrieve(self, query: str) -> list[dict]` (cada dict = payload + `"score"`).
  - Helpers `cosine_similarity(a, b) -> float` em `base.py`.
  - `retrieval_registry: Registry[type[Retriever]]`; `build_retriever(name: str, **kwargs) -> Retriever`.
  - `SimilarityRetriever(store, collection, embedder, top_k=5)` registrado `"similarity"`.
  - `MMRRetriever(store, collection, embedder, top_k=5, fetch_k=20, lambda_mult=0.5)` registrado `"mmr"`.

- [ ] **Step 1: Escrever o teste que falha**

`backend/tests/test_retrievers.py`:

```python
"""Tests for similarity and MMR retrievers."""
import pytest
from qdrant_client import QdrantClient

from app.core.retrieval.base import Retriever, build_retriever, retrieval_registry
from app.core.retrieval.mmr import MMRRetriever
from app.core.retrieval.similarity import SimilarityRetriever
from app.core.vectorstore.qdrant import QdrantStore


class _FakeEmbedder:
    """Maps a query to a fixed 3-dim vector based on its first character."""

    def embed_documents(self, texts):
        return [self.embed_query(t) for t in texts]

    def embed_query(self, text):
        table = {"a": [1.0, 0.0, 0.0], "b": [0.0, 1.0, 0.0], "c": [0.0, 0.0, 1.0]}
        return table.get(text[:1].lower(), [1.0, 0.0, 0.0])

    @property
    def dimension(self) -> int:
        return 3


@pytest.fixture
def store():
    s = QdrantStore(client=QdrantClient(":memory:"))
    s.ensure_collection("col", dimension=3)
    s.add(
        "col",
        vectors=[[1.0, 0.0, 0.0], [0.9, 0.1, 0.0], [0.0, 1.0, 0.0]],
        payloads=[
            {"source_doc": "a.txt", "chunk_index": 0, "text": "alpha one"},
            {"source_doc": "a.txt", "chunk_index": 1, "text": "alpha two"},
            {"source_doc": "b.txt", "chunk_index": 0, "text": "beta"},
        ],
    )
    return s


def test_similarity_returns_nearest_first(store):
    retriever = SimilarityRetriever(store, "col", _FakeEmbedder(), top_k=2)
    results = retriever.retrieve("alpha question")
    assert len(results) == 2
    assert results[0]["text"] == "alpha one"
    assert "score" in results[0]


def test_mmr_diversifies_results(store):
    retriever = MMRRetriever(store, "col", _FakeEmbedder(), top_k=2, fetch_k=3, lambda_mult=0.5)
    results = retriever.retrieve("alpha question")
    texts = [r["text"] for r in results]
    assert len(results) == 2
    assert "alpha one" in texts


def test_retrievers_registered_and_built(store):
    assert {"similarity", "mmr"} <= set(retrieval_registry.names())
    retriever = build_retriever("similarity", store=store, collection="col", embedder=_FakeEmbedder())
    assert isinstance(retriever, Retriever)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_retrievers.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'app.core.retrieval'`.

- [ ] **Step 3: Implementar a base**

`backend/app/core/retrieval/base.py`:

```python
"""Retriever interface, registry, factory, and similarity helpers."""
from abc import ABC, abstractmethod

from app.core.registry import Registry


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Return the cosine similarity between two vectors (0 if either is zero)."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class Retriever(ABC):
    """Minimal interface every retriever implements."""

    @abstractmethod
    def retrieve(self, query: str) -> list[dict]:
        """Return relevant contexts (payload dicts plus a 'score')."""


retrieval_registry: Registry[type[Retriever]] = Registry("retrieval")


def build_retriever(name: str, **kwargs) -> Retriever:
    """Instantiate a registered retriever by name."""
    return retrieval_registry.get(name)(**kwargs)
```

- [ ] **Step 4: Implementar o SimilarityRetriever**

`backend/app/core/retrieval/similarity.py`:

```python
"""Dense similarity retriever (top-k vector search)."""
from app.core.embedding.base import Embedder
from app.core.retrieval.base import Retriever, retrieval_registry
from app.core.vectorstore.qdrant import QdrantStore


class SimilarityRetriever(Retriever):
    """Retrieves the top-k nearest chunks by vector similarity."""

    def __init__(
        self,
        store: QdrantStore,
        collection: str,
        embedder: Embedder,
        top_k: int = 5,
    ) -> None:
        self._store = store
        self._collection = collection
        self._embedder = embedder
        self._top_k = top_k

    def retrieve(self, query: str) -> list[dict]:
        """Embed the query and return the nearest chunks."""
        query_vector = self._embedder.embed_query(query)
        hits = self._store.search(self._collection, query_vector, top_k=self._top_k)
        return [{**hit["payload"], "score": hit["score"]} for hit in hits]


retrieval_registry.register("similarity", SimilarityRetriever)
```

- [ ] **Step 5: Implementar o MMRRetriever**

`backend/app/core/retrieval/mmr.py`:

```python
"""Maximal Marginal Relevance retriever (diversifies results)."""
from app.core.embedding.base import Embedder
from app.core.retrieval.base import Retriever, cosine_similarity, retrieval_registry
from app.core.vectorstore.qdrant import QdrantStore


def _mmr_select(
    query_vector: list[float],
    candidate_vectors: list[list[float]],
    top_k: int,
    lambda_mult: float,
) -> list[int]:
    """Select indices maximizing relevance while penalizing redundancy."""
    selected: list[int] = []
    remaining = list(range(len(candidate_vectors)))
    while remaining and len(selected) < top_k:
        best_index = remaining[0]
        best_score = None
        for index in remaining:
            relevance = cosine_similarity(query_vector, candidate_vectors[index])
            diversity = max(
                (cosine_similarity(candidate_vectors[index], candidate_vectors[s]) for s in selected),
                default=0.0,
            )
            score = lambda_mult * relevance - (1 - lambda_mult) * diversity
            if best_score is None or score > best_score:
                best_score = score
                best_index = index
        selected.append(best_index)
        remaining.remove(best_index)
    return selected


class MMRRetriever(Retriever):
    """Retrieves diverse chunks using Maximal Marginal Relevance."""

    def __init__(
        self,
        store: QdrantStore,
        collection: str,
        embedder: Embedder,
        top_k: int = 5,
        fetch_k: int = 20,
        lambda_mult: float = 0.5,
    ) -> None:
        self._store = store
        self._collection = collection
        self._embedder = embedder
        self._top_k = top_k
        self._fetch_k = fetch_k
        self._lambda_mult = lambda_mult

    def retrieve(self, query: str) -> list[dict]:
        """Fetch candidates, then re-rank for diversity with MMR."""
        query_vector = self._embedder.embed_query(query)
        hits = self._store.search(
            self._collection, query_vector, top_k=self._fetch_k, with_vectors=True
        )
        if not hits:
            return []
        indices = _mmr_select(
            query_vector,
            [hit["vector"] for hit in hits],
            self._top_k,
            self._lambda_mult,
        )
        return [{**hits[i]["payload"], "score": hits[i]["score"]} for i in indices]


retrieval_registry.register("mmr", MMRRetriever)
```

- [ ] **Step 6: Implementar o `__init__.py`**

`backend/app/core/retrieval/__init__.py`:

```python
"""Retrieval package. Importing it registers the built-in retrievers."""
from app.core.retrieval.base import (
    Retriever,
    build_retriever,
    cosine_similarity,
    retrieval_registry,
)
from app.core.retrieval.mmr import MMRRetriever
from app.core.retrieval.similarity import SimilarityRetriever

__all__ = [
    "Retriever",
    "build_retriever",
    "cosine_similarity",
    "retrieval_registry",
    "SimilarityRetriever",
    "MMRRetriever",
]
```

- [ ] **Step 7: Rodar e ver passar**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_retrievers.py -v`
Expected: PASS (3 testes). Suíte inteira verde, zero warnings.

- [ ] **Step 8: Commit**

```bash
git add backend/app/core/retrieval backend/tests/test_retrievers.py
git commit -m "feat: retriever interface + similarity and mmr retrievers"
```

---

### Task 3: Retrievers multi_query e parent_document

**Files:**
- Create: `backend/app/core/retrieval/multi_query.py`
- Create: `backend/app/core/retrieval/parent_document.py`
- Modify: `backend/app/core/retrieval/__init__.py` (registrar/exportar)
- Create: `backend/tests/test_retrievers_advanced.py`

**Interfaces:**
- Consumes: `app.core.retrieval.base.Retriever`, `SimilarityRetriever`, `app.core.llm.base.LLM`, `QdrantStore`, `Embedder`.
- Produces:
  - `MultiQueryRetriever(store, collection, embedder, llm, top_k=5, n_queries=3)` registrado `"multi_query"`. Gera variações da query com o LLM, recupera para cada (via um `SimilarityRetriever` interno) e une os resultados deduplicando por `(source_doc, chunk_index)`.
  - `ParentDocumentRetriever(store, collection, embedder, top_k=3, window=1)` registrado `"parent_document"`. Recupera os top-k chunks e, para cada, junta os chunks vizinhos do mesmo `source_doc` dentro de `±window` (via `store.scroll`), devolvendo o texto expandido.

- [ ] **Step 1: Escrever o teste que falha**

`backend/tests/test_retrievers_advanced.py`:

```python
"""Tests for multi-query and parent-document retrievers."""
import pytest
from qdrant_client import QdrantClient

from app.core.retrieval.base import build_retriever, retrieval_registry
from app.core.retrieval.multi_query import MultiQueryRetriever
from app.core.retrieval.parent_document import ParentDocumentRetriever
from app.core.vectorstore.qdrant import QdrantStore


class _FakeEmbedder:
    def embed_documents(self, texts):
        return [self.embed_query(t) for t in texts]

    def embed_query(self, text):
        if "beta" in text.lower():
            return [0.0, 1.0, 0.0]
        return [1.0, 0.0, 0.0]

    @property
    def dimension(self) -> int:
        return 3


class _ScriptedLLM:
    """Returns a fixed multi-line set of query variations."""

    def generate(self, prompt: str) -> str:
        return "alpha variant one\nbeta variant two"


@pytest.fixture
def store():
    s = QdrantStore(client=QdrantClient(":memory:"))
    s.ensure_collection("col", dimension=3)
    s.add(
        "col",
        vectors=[[1.0, 0.0, 0.0], [0.95, 0.05, 0.0], [0.0, 1.0, 0.0]],
        payloads=[
            {"source_doc": "a.txt", "chunk_index": 0, "text": "alpha zero"},
            {"source_doc": "a.txt", "chunk_index": 1, "text": "alpha one"},
            {"source_doc": "b.txt", "chunk_index": 0, "text": "beta zero"},
        ],
    )
    return s


def test_multi_query_unions_results(store):
    retriever = MultiQueryRetriever(
        store, "col", _FakeEmbedder(), _ScriptedLLM(), top_k=1, n_queries=2
    )
    results = retriever.retrieve("alpha question")
    texts = {r["text"] for r in results}
    assert "alpha zero" in texts
    assert "beta zero" in texts  # the 'beta' variant pulled a different chunk


def test_parent_document_expands_with_neighbors(store):
    retriever = ParentDocumentRetriever(store, "col", _FakeEmbedder(), top_k=1, window=1)
    results = retriever.retrieve("alpha question")
    assert len(results) == 1
    assert "alpha zero" in results[0]["text"]
    assert "alpha one" in results[0]["text"]  # neighbor included


def test_advanced_retrievers_registered(store):
    assert {"multi_query", "parent_document"} <= set(retrieval_registry.names())
    retriever = build_retriever(
        "parent_document", store=store, collection="col", embedder=_FakeEmbedder()
    )
    assert isinstance(retriever, ParentDocumentRetriever)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_retrievers_advanced.py -v`
Expected: FAIL com `ModuleNotFoundError`.

- [ ] **Step 3: Implementar o MultiQueryRetriever**

`backend/app/core/retrieval/multi_query.py`:

```python
"""Multi-query retriever: expands the query with LLM-generated variations."""
from app.core.embedding.base import Embedder
from app.core.llm.base import LLM
from app.core.retrieval.base import Retriever, retrieval_registry
from app.core.retrieval.similarity import SimilarityRetriever
from app.core.vectorstore.qdrant import QdrantStore

_PROMPT = (
    "Generate {n} alternative search queries, one per line, that rephrase the "
    "following question to improve document retrieval. Question: {question}"
)


class MultiQueryRetriever(Retriever):
    """Retrieves with the original query plus LLM-generated variations."""

    def __init__(
        self,
        store: QdrantStore,
        collection: str,
        embedder: Embedder,
        llm: LLM,
        top_k: int = 5,
        n_queries: int = 3,
    ) -> None:
        self._base = SimilarityRetriever(store, collection, embedder, top_k=top_k)
        self._llm = llm
        self._n_queries = n_queries

    def _variations(self, query: str) -> list[str]:
        """Ask the LLM for alternative phrasings of the query."""
        raw = self._llm.generate(_PROMPT.format(n=self._n_queries, question=query))
        return [line.strip() for line in raw.splitlines() if line.strip()]

    def retrieve(self, query: str) -> list[dict]:
        """Union retrieval over the query and its variations, deduplicated."""
        merged: dict[tuple, dict] = {}
        for candidate in [query, *self._variations(query)]:
            for context in self._base.retrieve(candidate):
                key = (context.get("source_doc"), context.get("chunk_index"))
                merged.setdefault(key, context)
        return list(merged.values())


retrieval_registry.register("multi_query", MultiQueryRetriever)
```

- [ ] **Step 4: Implementar o ParentDocumentRetriever**

`backend/app/core/retrieval/parent_document.py`:

```python
"""Parent-document retriever: expands hits with neighboring chunks."""
from app.core.embedding.base import Embedder
from app.core.retrieval.base import Retriever, retrieval_registry
from app.core.vectorstore.qdrant import QdrantStore


class ParentDocumentRetriever(Retriever):
    """Retrieves top chunks and expands each with its neighbors."""

    def __init__(
        self,
        store: QdrantStore,
        collection: str,
        embedder: Embedder,
        top_k: int = 3,
        window: int = 1,
    ) -> None:
        self._store = store
        self._collection = collection
        self._embedder = embedder
        self._top_k = top_k
        self._window = window

    def retrieve(self, query: str) -> list[dict]:
        """Return top chunks expanded with same-document neighbors."""
        query_vector = self._embedder.embed_query(query)
        hits = self._store.search(self._collection, query_vector, top_k=self._top_k)
        results = []
        for hit in hits:
            payload = hit["payload"]
            source = payload["source_doc"]
            index = payload["chunk_index"]
            siblings = self._store.scroll(self._collection, where={"source_doc": source})
            window_chunks = sorted(
                (
                    s["payload"]
                    for s in siblings
                    if abs(s["payload"]["chunk_index"] - index) <= self._window
                ),
                key=lambda p: p["chunk_index"],
            )
            text = " ".join(chunk["text"] for chunk in window_chunks)
            results.append(
                {
                    "text": text,
                    "score": hit["score"],
                    "source_doc": source,
                    "chunk_index": index,
                }
            )
        return results


retrieval_registry.register("parent_document", ParentDocumentRetriever)
```

- [ ] **Step 5: Atualizar o `__init__.py`**

Atualize `backend/app/core/retrieval/__init__.py` para importar e exportar `MultiQueryRetriever` e `ParentDocumentRetriever` (mantendo os anteriores):

```python
"""Retrieval package. Importing it registers the built-in retrievers."""
from app.core.retrieval.base import (
    Retriever,
    build_retriever,
    cosine_similarity,
    retrieval_registry,
)
from app.core.retrieval.mmr import MMRRetriever
from app.core.retrieval.multi_query import MultiQueryRetriever
from app.core.retrieval.parent_document import ParentDocumentRetriever
from app.core.retrieval.similarity import SimilarityRetriever

__all__ = [
    "Retriever",
    "build_retriever",
    "cosine_similarity",
    "retrieval_registry",
    "SimilarityRetriever",
    "MMRRetriever",
    "MultiQueryRetriever",
    "ParentDocumentRetriever",
]
```

- [ ] **Step 6: Rodar e ver passar**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_retrievers_advanced.py -v`
Expected: PASS (3 testes). Suíte inteira verde, zero warnings.

- [ ] **Step 7: Commit**

```bash
git add backend/app/core/retrieval/multi_query.py backend/app/core/retrieval/parent_document.py backend/app/core/retrieval/__init__.py backend/tests/test_retrievers_advanced.py
git commit -m "feat: multi-query and parent-document retrievers"
```

---

### Task 4: Interface de RAG + NaiveRAG

**Files:**
- Create: `backend/app/core/rag/__init__.py`
- Create: `backend/app/core/rag/base.py`
- Create: `backend/app/core/rag/naive.py`
- Create: `backend/tests/test_rag_naive.py`

**Interfaces:**
- Consumes: `app.core.registry.Registry`, `app.core.retrieval.base.Retriever`, `app.core.llm.base.LLM`.
- Produces:
  - `RAGResult` (Pydantic): `answer: str`, `contexts: list[dict]`.
  - `RAG` (ABC) com `answer(self, query: str) -> RAGResult`.
  - Helper `format_context(contexts) -> str` em `base.py`.
  - `rag_registry: Registry[type[RAG]]`; `build_rag(name: str, **kwargs) -> RAG`.
  - `NaiveRAG(retriever, llm)` registrado `"naive"`. (Nota: não há `top_context` — a quantidade de contexto já é controlada pelo `top_k` do retriever; adicionar outro limite aqui seria redundante.)

- [ ] **Step 1: Escrever o teste que falha**

`backend/tests/test_rag_naive.py`:

```python
"""Tests for NaiveRAG."""
from app.core.rag.base import RAG, RAGResult, build_rag, rag_registry
from app.core.rag.naive import NaiveRAG


class _StubRetriever:
    def retrieve(self, query: str) -> list[dict]:
        return [
            {"text": "The center is around the main square.", "source_doc": "a.txt", "score": 0.9},
            {"text": "The food street has artisanal cheese.", "source_doc": "a.txt", "score": 0.8},
        ]


class _EchoLLM:
    """Echoes the prompt it received so the test can inspect it."""

    def __init__(self) -> None:
        self.last_prompt = None

    def generate(self, prompt: str) -> str:
        self.last_prompt = prompt
        return "The center is around the main square."


def test_naive_rag_builds_prompt_with_context_and_answers():
    llm = _EchoLLM()
    rag = NaiveRAG(_StubRetriever(), llm)
    result = rag.answer("Where is the center?")
    assert isinstance(result, RAGResult)
    assert result.answer == "The center is around the main square."
    assert len(result.contexts) == 2
    assert "main square" in llm.last_prompt
    assert "Where is the center?" in llm.last_prompt


def test_naive_rag_registered_and_built():
    assert "naive" in rag_registry.names()
    rag = build_rag("naive", retriever=_StubRetriever(), llm=_EchoLLM())
    assert isinstance(rag, RAG)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_rag_naive.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'app.core.rag'`.

- [ ] **Step 3: Implementar a base**

`backend/app/core/rag/base.py`:

```python
"""RAG technique interface, result model, registry, and helpers."""
from abc import ABC, abstractmethod

from pydantic import BaseModel

from app.core.registry import Registry


class RAGResult(BaseModel):
    """Answer produced by a RAG technique, with its supporting contexts."""

    answer: str
    contexts: list[dict]


def format_context(contexts: list[dict]) -> str:
    """Join the contexts' text into a single prompt-ready block."""
    return "\n\n".join(context.get("text", "") for context in contexts)


class RAG(ABC):
    """Minimal interface every RAG technique implements."""

    @abstractmethod
    def answer(self, query: str) -> RAGResult:
        """Answer a question, returning the answer and its contexts."""


rag_registry: Registry[type[RAG]] = Registry("rag")


def build_rag(name: str, **kwargs) -> RAG:
    """Instantiate a registered RAG technique by name."""
    return rag_registry.get(name)(**kwargs)
```

- [ ] **Step 4: Implementar o NaiveRAG**

`backend/app/core/rag/naive.py`:

```python
"""Naive RAG: retrieve top-k, stuff into the prompt, generate."""
from app.core.llm.base import LLM
from app.core.rag.base import RAG, RAGResult, format_context, rag_registry
from app.core.retrieval.base import Retriever

_PROMPT = (
    "Use the context below to answer the question. If the context is not "
    "enough, say what you can.\n\nContext:\n{context}\n\nQuestion: {question}\n\nAnswer:"
)


class NaiveRAG(RAG):
    """Single-shot retrieve-then-generate technique."""

    def __init__(self, retriever: Retriever, llm: LLM) -> None:
        self._retriever = retriever
        self._llm = llm

    def answer(self, query: str) -> RAGResult:
        """Retrieve context and generate a grounded answer."""
        contexts = self._retriever.retrieve(query)
        prompt = _PROMPT.format(context=format_context(contexts), question=query)
        answer = self._llm.generate(prompt)
        return RAGResult(answer=answer, contexts=contexts)


rag_registry.register("naive", NaiveRAG)
```

- [ ] **Step 5: Implementar o `__init__.py`**

`backend/app/core/rag/__init__.py`:

```python
"""RAG package. Importing it registers the built-in techniques."""
from app.core.rag.base import RAG, RAGResult, build_rag, format_context, rag_registry
from app.core.rag.naive import NaiveRAG

__all__ = [
    "RAG",
    "RAGResult",
    "build_rag",
    "format_context",
    "rag_registry",
    "NaiveRAG",
]
```

- [ ] **Step 6: Rodar e ver passar**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_rag_naive.py -v`
Expected: PASS (2 testes). Suíte inteira verde, zero warnings.

- [ ] **Step 7: Commit**

```bash
git add backend/app/core/rag backend/tests/test_rag_naive.py
git commit -m "feat: RAG interface + naive technique"
```

---

### Task 5: AgenticRAG (loop agêntico compacto)

**Files:**
- Create: `backend/app/core/rag/agentic.py`
- Modify: `backend/app/core/rag/__init__.py` (registrar/exportar)
- Create: `backend/tests/test_rag_agentic.py`

**Interfaces:**
- Consumes: `app.core.rag.base.RAG/RAGResult/format_context`, `Retriever`, `LLM`.
- Produces:
  - `AgenticRAG(retriever, llm, max_steps: int = 3)` registrado `"agentic"`.
  - Loop: a cada passo recupera para a query atual, acumula contextos e pergunta ao LLM uma decisão. O LLM responde `SEARCH: <nova query>` (recupera de novo) ou `ANSWER: <resposta final>` (encerra). Atinge `max_steps` → gera uma resposta final com o contexto acumulado.

- [ ] **Step 1: Escrever o teste que falha**

`backend/tests/test_rag_agentic.py`:

```python
"""Tests for AgenticRAG."""
from app.core.rag.agentic import AgenticRAG
from app.core.rag.base import RAGResult, rag_registry


class _StubRetriever:
    def __init__(self) -> None:
        self.queries = []

    def retrieve(self, query: str) -> list[dict]:
        self.queries.append(query)
        return [{"text": f"context for {query}", "source_doc": "a.txt", "score": 0.5}]


class _ScriptedLLM:
    """Returns a queued list of responses, one per call."""

    def __init__(self, responses) -> None:
        self._responses = list(responses)
        self.calls = 0

    def generate(self, prompt: str) -> str:
        self.calls += 1
        return self._responses.pop(0)


def test_agentic_searches_then_answers():
    retriever = _StubRetriever()
    llm = _ScriptedLLM(["SEARCH: refined query", "ANSWER: final answer"])
    rag = AgenticRAG(retriever, llm, max_steps=3)
    result = rag.answer("original question")
    assert isinstance(result, RAGResult)
    assert result.answer == "final answer"
    assert retriever.queries == ["original question", "refined query"]
    assert len(result.contexts) == 2


def test_agentic_answers_immediately():
    retriever = _StubRetriever()
    llm = _ScriptedLLM(["ANSWER: quick answer"])
    rag = AgenticRAG(retriever, llm, max_steps=3)
    result = rag.answer("question")
    assert result.answer == "quick answer"
    assert retriever.queries == ["question"]


def test_agentic_stops_at_max_steps():
    retriever = _StubRetriever()
    llm = _ScriptedLLM(["SEARCH: a", "SEARCH: b", "final fallback answer"])
    rag = AgenticRAG(retriever, llm, max_steps=2)
    result = rag.answer("question")
    assert result.answer == "final fallback answer"
    assert len(retriever.queries) == 2


def test_agentic_registered():
    assert "agentic" in rag_registry.names()
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_rag_agentic.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'app.core.rag.agentic'`.

- [ ] **Step 3: Implementar o AgenticRAG**

`backend/app/core/rag/agentic.py`:

```python
"""Agentic RAG: a bounded loop where the LLM decides to search or answer."""
from app.core.llm.base import LLM
from app.core.rag.base import RAG, RAGResult, format_context, rag_registry
from app.core.retrieval.base import Retriever

_DECIDE_PROMPT = (
    "You are answering a question using retrieved context. Based on the context "
    "so far, decide your next action. Reply with exactly one line:\n"
    "'SEARCH: <a better search query>' if you need more information, or\n"
    "'ANSWER: <your final answer>' if the context is sufficient.\n\n"
    "Question: {question}\n\nContext so far:\n{context}"
)
_ANSWER_PROMPT = (
    "Answer the question using the context.\n\nContext:\n{context}\n\n"
    "Question: {question}\n\nAnswer:"
)
_SEARCH_TAG = "SEARCH:"
_ANSWER_TAG = "ANSWER:"


class AgenticRAG(RAG):
    """Iteratively retrieves and lets the LLM decide when to answer."""

    def __init__(self, retriever: Retriever, llm: LLM, max_steps: int = 3) -> None:
        self._retriever = retriever
        self._llm = llm
        self._max_steps = max_steps

    def answer(self, query: str) -> RAGResult:
        """Run the bounded search-or-answer loop and return the result."""
        contexts: list[dict] = []
        current_query = query
        for _ in range(self._max_steps):
            contexts.extend(self._retriever.retrieve(current_query))
            decision = self._llm.generate(
                _DECIDE_PROMPT.format(question=query, context=format_context(contexts))
            ).strip()
            if decision.startswith(_ANSWER_TAG):
                return RAGResult(
                    answer=decision[len(_ANSWER_TAG):].strip(), contexts=contexts
                )
            if decision.startswith(_SEARCH_TAG):
                current_query = decision[len(_SEARCH_TAG):].strip()
                continue
            return RAGResult(answer=decision, contexts=contexts)
        final = self._llm.generate(
            _ANSWER_PROMPT.format(question=query, context=format_context(contexts))
        )
        return RAGResult(answer=final, contexts=contexts)


rag_registry.register("agentic", AgenticRAG)
```

- [ ] **Step 4: Atualizar o `__init__.py`**

Atualize `backend/app/core/rag/__init__.py` para importar e exportar `AgenticRAG`:

```python
"""RAG package. Importing it registers the built-in techniques."""
from app.core.rag.agentic import AgenticRAG
from app.core.rag.base import RAG, RAGResult, build_rag, format_context, rag_registry
from app.core.rag.naive import NaiveRAG

__all__ = [
    "RAG",
    "RAGResult",
    "build_rag",
    "format_context",
    "rag_registry",
    "NaiveRAG",
    "AgenticRAG",
]
```

- [ ] **Step 5: Rodar e ver passar**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_rag_agentic.py -v`
Expected: PASS (4 testes). Suíte inteira verde, zero warnings.

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/rag/agentic.py backend/app/core/rag/__init__.py backend/tests/test_rag_agentic.py
git commit -m "feat: agentic RAG with bounded search-or-answer loop"
```

---

## Self-Review

**Spec coverage (Plano 4 cobre spec §6 — técnicas de RAG e retrievers):**
- Retriever interface + registry + 4 retrievers `similarity/mmr/multi_query/parent_document` (spec §6 eixo 2) → Tasks 2, 3. ✅
- RAG interface + `naive` + `agentic` (spec §6 eixo 1; Graph fica para depois) → Tasks 4, 5. ✅
- `QdrantStore` estendido para o que MMR (vetores) e ParentDocument (id/scroll) precisam (carry-forward do Plano 2) → Task 1. ✅
- Tudo atrás de interface + registry; LLM trocável (injetado) → todas as tasks. ✅
- Testes sem rede (Qdrant em memória, Embedder/LLM/Retriever fakes) → todas as tasks. ✅

**Placeholder scan:** sem TBD/TODO; todos os passos com código/comando concreto. ✅

**Type consistency:**
- `Retriever.retrieve(query) -> list[dict]` consistente entre base, similarity, mmr, multi_query, parent_document e testes. ✅
- `RAG.answer(query) -> RAGResult{answer, contexts}` consistente entre base, naive, agentic e testes. ✅
- `QdrantStore.search(..., with_vectors)` e `scroll(...)` consistentes entre wrapper, retrievers e testes; mudança aditiva (search continua com `score`/`payload`, agora `id`). ✅
- `build_retriever`/`build_rag(name, **kwargs)` reusam `Registry.get`. ✅
- Injeção de `store`/`embedder`/`llm`/`retriever` em todos os construtores para testes sem rede. ✅

**Escopo:** só recuperação + geração (retrievers + naive/agentic). Nada de avaliação/experimentos/frontend (planos seguintes); Graph RAG e Hybrid/BM25 explicitamente fora. AgenticRAG é um loop compacto (sem LangGraph) — decisão registrada; o agente conversacional com LangGraph é da Fatia B. ✅
