# Fatia A — Plano 3: Ingestão — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar a ingestão de documentos: estratégias de corte (chunking) plugáveis, um pipeline que para cada combinação `chunking × embedding` corta → embeda → grava no Qdrant com metadata, e os endpoints `/ingest` (upload + config) e `/options` (técnicas disponíveis).

**Architecture:** Um subpacote `app/core/` para chunkers (interface + registry, espelhando llm/embedding). Um módulo `app/ingestion/` com o pipeline que consome os providers do Plano 2 (`build_embedder`, `QdrantStore`, `collection_name`) e os chunkers. Routers finos em `app/api/`. Tudo testado sem rede (embedders fake, Qdrant em memória).

**Tech Stack:** Python 3.11, FastAPI, langchain-text-splitters, qdrant-client, Pydantic v2, pytest.

## Global Constraints

- **Código em inglês:** identificadores, docstrings e mensagens de erro em inglês. Apenas dados de domínio em PT-BR.
- PEP-8; docstrings nas funções públicas; comentários só quando agregam.
- Toda técnica plugável atrás de interface + registry (reusa `app.core.registry.Registry`).
- Sem duplicação: ingestão usa os providers do `core/` (`build_embedder`, `QdrantStore`, `collection_name`); nunca instancia clientes direto.
- **Testes sem rede:** embedders são injetados (fakes nos testes); Qdrant em memória (`QdrantClient(":memory:")`). Nenhum download de modelo.
- Chunkers disponíveis: `fixed`, `recursive`, `token`, `semantic`. O `semantic` usa um `Embedder` injetado.
- Convenção de coleção (Plano 2): `collection_name(base, chunking, embedding)` → `base__chunking__embedding`. Metadata por vetor: `source_doc`, `chunking_strategy`, `embedding_model`, `chunk_index`, `text`.
- venv de dev em `backend/.venv`. Rodar testes: `cd backend && ./.venv/bin/python -m pytest`. Saída pristina (zero warnings).
- Documento real de teste disponível em `database/faq_manus_completa.md` (guia de viagem PT-BR). Acesse-o por caminho relativo à raiz do repo: `Path(__file__).resolve().parents[2] / "database" / "faq_manus_completa.md"`.
- Commits frequentes, um por task.

---

## File Structure

```
backend/
  pyproject.toml                  # + langchain-text-splitters, tiktoken
  app/core/chunking/
    __init__.py                   # expõe Chunker, chunking_registry, build_chunker
    base.py                       # interface Chunker (ABC) + Registry + build_chunker
    splitters.py                  # FixedSizeChunker, RecursiveChunker, TokenChunker
    semantic.py                   # SemanticChunker (usa Embedder injetado)
  app/ingestion/
    __init__.py
    schemas.py                    # IngestConfig (Pydantic), IngestResult, Document
    pipeline.py                   # ingest_documents(...)
  app/api/
    options.py                    # GET /options (técnicas dos registries)
    ingest.py                     # POST /ingest (upload + config)
  tests/
    test_chunking.py
    test_semantic_chunker.py
    test_ingestion_pipeline.py
    test_ingest_api.py
```

`app/main.py` passa a incluir os routers `options` e `ingest`.

---

### Task 1: Interface de chunking + chunkers fixed/recursive/token

**Files:**
- Modify: `backend/pyproject.toml` (deps)
- Create: `backend/app/core/chunking/__init__.py`
- Create: `backend/app/core/chunking/base.py`
- Create: `backend/app/core/chunking/splitters.py`
- Create: `backend/tests/test_chunking.py`

**Interfaces:**
- Consumes: `app.core.registry.Registry`, `langchain_text_splitters`.
- Produces:
  - `Chunker` (ABC) com `split(self, text: str) -> list[str]`.
  - `chunking_registry: Registry[type[Chunker]]` com `"fixed"`, `"recursive"`, `"token"` (e `"semantic"` na Task 2).
  - `build_chunker(name: str, **kwargs) -> Chunker`.
  - `FixedSizeChunker(chunk_size: int = 1000, chunk_overlap: int = 100)`; `RecursiveChunker(chunk_size: int = 1000, chunk_overlap: int = 100)`; `TokenChunker(chunk_size: int = 256, chunk_overlap: int = 20)`.

- [ ] **Step 1: Adicionar dependências ao `pyproject.toml`**

No array `dependencies` de `backend/pyproject.toml`, acrescente:

```toml
    "langchain-text-splitters>=0.2",
    "tiktoken>=0.7",
```

Instale: `cd backend && ./.venv/bin/pip install -e ".[dev]"`.

- [ ] **Step 2: Escrever o teste que falha**

`backend/tests/test_chunking.py`:

```python
"""Tests for chunking strategies."""
from app.core.chunking.base import Chunker, build_chunker, chunking_registry
from app.core.chunking.splitters import (
    FixedSizeChunker,
    RecursiveChunker,
    TokenChunker,
)

_TEXT = (
    "First paragraph about the city center and the main square.\n\n"
    "Second paragraph about food, restaurants and local cuisine.\n\n"
    "Third paragraph about transport, taxis and walking around town."
)


def test_fixed_chunker_respects_size():
    chunker = FixedSizeChunker(chunk_size=40, chunk_overlap=0)
    chunks = chunker.split(_TEXT)
    assert len(chunks) > 1
    assert all(len(c) <= 60 for c in chunks)


def test_recursive_chunker_produces_chunks():
    chunker = RecursiveChunker(chunk_size=50, chunk_overlap=0)
    chunks = chunker.split(_TEXT)
    assert len(chunks) > 1
    assert "".join(chunks).replace(" ", "").replace("\n", "") != ""


def test_token_chunker_produces_chunks():
    chunker = TokenChunker(chunk_size=8, chunk_overlap=0)
    chunks = chunker.split(_TEXT)
    assert len(chunks) > 1


def test_chunkers_registered_and_built():
    assert {"fixed", "recursive", "token"} <= set(chunking_registry.names())
    chunker = build_chunker("recursive", chunk_size=50, chunk_overlap=0)
    assert isinstance(chunker, Chunker)
    assert len(chunker.split(_TEXT)) > 1
```

- [ ] **Step 3: Rodar e ver falhar**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_chunking.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'app.core.chunking'`.

- [ ] **Step 4: Implementar a interface e o registry**

`backend/app/core/chunking/base.py`:

```python
"""Chunking strategy interface, registry, and factory."""
from abc import ABC, abstractmethod

from app.core.registry import Registry


class Chunker(ABC):
    """Minimal interface every chunking strategy implements."""

    @abstractmethod
    def split(self, text: str) -> list[str]:
        """Split a document's text into chunks."""


chunking_registry: Registry[type[Chunker]] = Registry("chunking")


def build_chunker(name: str, **kwargs) -> Chunker:
    """Instantiate a registered chunking strategy by name."""
    return chunking_registry.get(name)(**kwargs)
```

- [ ] **Step 5: Implementar os splitters**

`backend/app/core/chunking/splitters.py`:

```python
"""Chunkers backed by langchain-text-splitters."""
from langchain_text_splitters import (
    CharacterTextSplitter,
    RecursiveCharacterTextSplitter,
    TokenTextSplitter,
)

from app.core.chunking.base import Chunker, chunking_registry


class FixedSizeChunker(Chunker):
    """Splits text into fixed-size character windows with overlap."""

    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 100) -> None:
        self._splitter = CharacterTextSplitter(
            separator="",
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

    def split(self, text: str) -> list[str]:
        """Split text into fixed-size chunks."""
        return self._splitter.split_text(text)


class RecursiveChunker(Chunker):
    """Splits text respecting paragraph and sentence boundaries."""

    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 100) -> None:
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

    def split(self, text: str) -> list[str]:
        """Split text recursively into chunks."""
        return self._splitter.split_text(text)


class TokenChunker(Chunker):
    """Splits text by token count."""

    def __init__(self, chunk_size: int = 256, chunk_overlap: int = 20) -> None:
        self._splitter = TokenTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

    def split(self, text: str) -> list[str]:
        """Split text into token-bounded chunks."""
        return self._splitter.split_text(text)


chunking_registry.register("fixed", FixedSizeChunker)
chunking_registry.register("recursive", RecursiveChunker)
chunking_registry.register("token", TokenChunker)
```

- [ ] **Step 6: Implementar o `__init__.py`**

`backend/app/core/chunking/__init__.py`:

```python
"""Chunking package. Importing it registers the built-in strategies."""
from app.core.chunking.base import Chunker, build_chunker, chunking_registry
from app.core.chunking.splitters import (
    FixedSizeChunker,
    RecursiveChunker,
    TokenChunker,
)

__all__ = [
    "Chunker",
    "build_chunker",
    "chunking_registry",
    "FixedSizeChunker",
    "RecursiveChunker",
    "TokenChunker",
]
```

- [ ] **Step 7: Rodar e ver passar**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_chunking.py -v`
Expected: PASS (4 testes). Suíte inteira verde, zero warnings. (Se `TokenTextSplitter` emitir warning sobre tiktoken/encoding, trate como achado: ajuste para passar `encoding_name="cl100k_base"` ou adicione filtro direcionado; saída pristina.)

- [ ] **Step 8: Commit**

```bash
git add backend/pyproject.toml backend/app/core/chunking backend/tests/test_chunking.py
git commit -m "feat: chunking interface + fixed/recursive/token splitters"
```

---

### Task 2: Semantic chunker (usa Embedder injetado)

**Files:**
- Create: `backend/app/core/chunking/semantic.py`
- Modify: `backend/app/core/chunking/__init__.py` (registrar `semantic`)
- Create: `backend/tests/test_semantic_chunker.py`

**Interfaces:**
- Consumes: `app.core.chunking.base.Chunker`, `chunking_registry`, `app.core.embedding.base.Embedder`.
- Produces:
  - `SemanticChunker(embedder, threshold: float = 0.5)` — registrado como `"semantic"`.
  - Quebra o texto em sentenças e inicia um novo chunk quando a distância de cosseno entre embeddings de sentenças consecutivas excede `threshold`.

- [ ] **Step 1: Escrever o teste que falha**

`backend/tests/test_semantic_chunker.py`:

```python
"""Tests for the semantic chunker."""
from app.core.chunking.base import build_chunker, chunking_registry
from app.core.chunking.semantic import SemanticChunker


class _FakeEmbedder:
    """Returns one of two orthogonal vectors based on the sentence's first word.

    Sentences starting with 'A' map to topic 1, others to topic 2, so the
    semantic boundary is deterministic and testable.
    """

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for t in texts:
            if t.strip().startswith("A"):
                vectors.append([1.0, 0.0])
            else:
                vectors.append([0.0, 1.0])
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return [0.0, 0.0]

    @property
    def dimension(self) -> int:
        return 2


def test_semantic_chunker_splits_on_topic_change():
    text = "Apples are red. Apples are sweet. Cars are fast. Cars are loud."
    chunker = SemanticChunker(embedder=_FakeEmbedder(), threshold=0.5)
    chunks = chunker.split(text)
    assert len(chunks) == 2
    assert "Apples" in chunks[0] and "Apples" in chunks[0]
    assert "Cars" in chunks[1]


def test_semantic_single_sentence_returns_one_chunk():
    chunker = SemanticChunker(embedder=_FakeEmbedder())
    assert chunker.split("Apples are red.") == ["Apples are red."]


def test_semantic_registered_and_built():
    assert "semantic" in chunking_registry.names()
    chunker = build_chunker("semantic", embedder=_FakeEmbedder())
    assert isinstance(chunker, SemanticChunker)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_semantic_chunker.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'app.core.chunking.semantic'`.

- [ ] **Step 3: Implementar o semantic chunker**

`backend/app/core/chunking/semantic.py`:

```python
"""Semantic chunker: splits where consecutive sentences change topic."""
import re

from app.core.chunking.base import Chunker, chunking_registry
from app.core.embedding.base import Embedder

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def _cosine_distance(a: list[float], b: list[float]) -> float:
    """Return 1 - cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 1.0
    return 1.0 - dot / (norm_a * norm_b)


class SemanticChunker(Chunker):
    """Groups consecutive sentences while they stay semantically close."""

    def __init__(self, embedder: Embedder, threshold: float = 0.5) -> None:
        self._embedder = embedder
        self._threshold = threshold

    def split(self, text: str) -> list[str]:
        """Split text at sentence boundaries where topic shifts."""
        sentences = [s for s in _SENTENCE_RE.split(text.strip()) if s]
        if len(sentences) <= 1:
            return sentences or [text]
        vectors = self._embedder.embed_documents(sentences)
        chunks: list[str] = []
        current = [sentences[0]]
        for i in range(1, len(sentences)):
            if _cosine_distance(vectors[i - 1], vectors[i]) > self._threshold:
                chunks.append(" ".join(current))
                current = [sentences[i]]
            else:
                current.append(sentences[i])
        chunks.append(" ".join(current))
        return chunks


chunking_registry.register("semantic", SemanticChunker)
```

- [ ] **Step 4: Registrar no `__init__.py`**

Atualize `backend/app/core/chunking/__init__.py` para importar e exportar `SemanticChunker`:

```python
"""Chunking package. Importing it registers the built-in strategies."""
from app.core.chunking.base import Chunker, build_chunker, chunking_registry
from app.core.chunking.semantic import SemanticChunker
from app.core.chunking.splitters import (
    FixedSizeChunker,
    RecursiveChunker,
    TokenChunker,
)

__all__ = [
    "Chunker",
    "build_chunker",
    "chunking_registry",
    "FixedSizeChunker",
    "RecursiveChunker",
    "TokenChunker",
    "SemanticChunker",
]
```

- [ ] **Step 5: Rodar e ver passar**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_semantic_chunker.py -v`
Expected: PASS (3 testes). Suíte inteira verde, zero warnings.

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/chunking/semantic.py backend/app/core/chunking/__init__.py backend/tests/test_semantic_chunker.py
git commit -m "feat: semantic chunker using injected embedder"
```

---

### Task 3: Pipeline de ingestão

**Files:**
- Create: `backend/app/ingestion/__init__.py`
- Create: `backend/app/ingestion/schemas.py`
- Create: `backend/app/ingestion/pipeline.py`
- Create: `backend/tests/test_ingestion_pipeline.py`

**Interfaces:**
- Consumes: `app.core.chunking.build_chunker`, `app.core.embedding.build_embedder`, `app.core.vectorstore.QdrantStore`, `app.core.vectorstore.collection_name`.
- Produces:
  - `Document` (Pydantic): `name: str`, `text: str`.
  - `IngestConfig` (Pydantic): `base: str`, `chunkings: list[str]`, `embeddings: list[str]`.
  - `IngestResult` (Pydantic): `collections: list[str]`, `total_chunks: int`.
  - `ingest_documents(documents: list[Document], config: IngestConfig, store: QdrantStore, embedder_factory=build_embedder) -> IngestResult` — para cada `chunking × embedding`: cria a coleção e insere os chunks com metadata. O `embedder_factory` é injetável para testes (default `build_embedder`).

- [ ] **Step 1: Escrever o teste que falha**

`backend/tests/test_ingestion_pipeline.py`:

```python
"""Tests for the ingestion pipeline."""
from pathlib import Path

from qdrant_client import QdrantClient

from app.core.vectorstore.qdrant import QdrantStore, collection_name
from app.ingestion.pipeline import ingest_documents
from app.ingestion.schemas import Document, IngestConfig


class _FakeEmbedder:
    """Deterministic 3-dim embedder; no network."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(t) % 7), 1.0, 0.0] for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return [float(len(text) % 7), 1.0, 0.0]

    @property
    def dimension(self) -> int:
        return 3


def _factory(name: str, **kwargs) -> _FakeEmbedder:
    return _FakeEmbedder()


def test_ingest_creates_collections_and_inserts(tmp_store_factory=None):
    store = QdrantStore(client=QdrantClient(":memory:"))
    docs = [Document(name="a.txt", text="Para 1.\n\nPara 2 is here.\n\nPara 3 ok.")]
    config = IngestConfig(base="viagem", chunkings=["recursive"], embeddings=["gemini"])

    result = ingest_documents(docs, config, store, embedder_factory=_factory)

    name = collection_name("viagem", "recursive", "gemini")
    assert result.collections == [name]
    assert result.total_chunks > 0
    hits = store.search(name, query_vector=[1.0, 1.0, 0.0], top_k=10)
    assert len(hits) == result.total_chunks
    assert hits[0]["payload"]["source_doc"] == "a.txt"
    assert hits[0]["payload"]["chunking_strategy"] == "recursive"
    assert hits[0]["payload"]["embedding_model"] == "gemini"
    assert "text" in hits[0]["payload"]
    assert "chunk_index" in hits[0]["payload"]


def test_ingest_cartesian_over_combinations():
    store = QdrantStore(client=QdrantClient(":memory:"))
    docs = [Document(name="a.txt", text="One sentence. Two sentence. Three sentence.")]
    config = IngestConfig(
        base="viagem", chunkings=["recursive", "token"], embeddings=["gemini"]
    )
    result = ingest_documents(docs, config, store, embedder_factory=_factory)
    assert set(result.collections) == {
        collection_name("viagem", "recursive", "gemini"),
        collection_name("viagem", "token", "gemini"),
    }


def test_ingest_real_travel_guide_document():
    store = QdrantStore(client=QdrantClient(":memory:"))
    path = Path(__file__).resolve().parents[2] / "database" / "faq_manus_completa.md"
    text = path.read_text(encoding="utf-8")
    docs = [Document(name=path.name, text=text)]
    config = IngestConfig(base="viagem", chunkings=["recursive"], embeddings=["gemini"])
    result = ingest_documents(docs, config, store, embedder_factory=_factory)
    assert result.total_chunks > 5
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_ingestion_pipeline.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'app.ingestion'`.

- [ ] **Step 3: Implementar os schemas**

`backend/app/ingestion/schemas.py`:

```python
"""Pydantic schemas for ingestion."""
from pydantic import BaseModel


class Document(BaseModel):
    """A source document to ingest."""

    name: str
    text: str


class IngestConfig(BaseModel):
    """Configuration for an ingestion run."""

    base: str
    chunkings: list[str]
    embeddings: list[str]


class IngestResult(BaseModel):
    """Outcome of an ingestion run."""

    collections: list[str]
    total_chunks: int
```

- [ ] **Step 4: Implementar o pipeline**

`backend/app/ingestion/pipeline.py`:

```python
"""Ingestion pipeline: chunk, embed, and store documents per combination."""
from collections.abc import Callable

from app.core.chunking.base import build_chunker
from app.core.embedding.base import Embedder, build_embedder
from app.core.vectorstore.qdrant import QdrantStore, collection_name
from app.ingestion.schemas import Document, IngestConfig, IngestResult


def _build_chunker_for(chunking: str, embedder: Embedder):
    """Build a chunker, injecting the embedder only for the semantic strategy."""
    if chunking == "semantic":
        return build_chunker(chunking, embedder=embedder)
    return build_chunker(chunking)


def ingest_documents(
    documents: list[Document],
    config: IngestConfig,
    store: QdrantStore,
    embedder_factory: Callable[..., Embedder] = build_embedder,
) -> IngestResult:
    """Chunk, embed, and store every chunking x embedding combination."""
    collections: list[str] = []
    total_chunks = 0
    for embedding in config.embeddings:
        embedder = embedder_factory(embedding)
        for chunking in config.chunkings:
            name = collection_name(config.base, chunking, embedding)
            store.ensure_collection(name, embedder.dimension)
            chunker = _build_chunker_for(chunking, embedder)
            for document in documents:
                chunks = chunker.split(document.text)
                if not chunks:
                    continue
                vectors = embedder.embed_documents(chunks)
                payloads = [
                    {
                        "source_doc": document.name,
                        "chunking_strategy": chunking,
                        "embedding_model": embedding,
                        "chunk_index": index,
                        "text": chunk,
                    }
                    for index, chunk in enumerate(chunks)
                ]
                store.add(name, vectors, payloads)
                total_chunks += len(chunks)
            collections.append(name)
    return IngestResult(collections=collections, total_chunks=total_chunks)
```

- [ ] **Step 5: Implementar o `__init__.py`**

`backend/app/ingestion/__init__.py`:

```python
"""Ingestion package."""
from app.ingestion.pipeline import ingest_documents
from app.ingestion.schemas import Document, IngestConfig, IngestResult

__all__ = ["ingest_documents", "Document", "IngestConfig", "IngestResult"]
```

- [ ] **Step 6: Rodar e ver passar**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_ingestion_pipeline.py -v`
Expected: PASS (3 testes). Suíte inteira verde, zero warnings.

- [ ] **Step 7: Commit**

```bash
git add backend/app/ingestion backend/tests/test_ingestion_pipeline.py
git commit -m "feat: ingestion pipeline (chunk x embed -> qdrant with metadata)"
```

---

### Task 4: Endpoints `/options` e `/ingest`

**Files:**
- Create: `backend/app/api/options.py`
- Create: `backend/app/api/ingest.py`
- Modify: `backend/app/main.py` (incluir os routers)
- Create: `backend/tests/test_ingest_api.py`

**Interfaces:**
- Consumes: `app.core.chunking.chunking_registry`, `app.core.embedding.embedding_registry`, `app.core.llm.llm_registry`, `app.ingestion.ingest_documents`, `app.core.vectorstore.QdrantStore`.
- Produces:
  - `GET /options` → `{"chunkings": [...], "embeddings": [...], "llms": [...]}` (nomes dos registries).
  - `POST /ingest` (multipart): campos `base: str`, `chunkings: str` (CSV), `embeddings: str` (CSV), `files: list[UploadFile]`. Lê o texto de cada arquivo (UTF-8), monta `Document`s e chama `ingest_documents`. Retorna `IngestResult`.
  - Para testabilidade, `app/api/ingest.py` expõe `get_store() -> QdrantStore` como dependência FastAPI (override nos testes para Qdrant em memória) e usa `build_embedder` real por padrão; o teste sobrescreve a store e injeta um embedder fake via `app.dependency_overrides`.

Nota de design: para o `/ingest` aceitar um embedder fake no teste sem rede, a rota deve obter o `embedder_factory` por dependência também (`get_embedder_factory`), default `build_embedder`. O teste sobrescreve `get_store` e `get_embedder_factory`.

- [ ] **Step 1: Escrever o teste que falha**

`backend/tests/test_ingest_api.py`:

```python
"""Tests for the /options and /ingest endpoints."""
import io

import pytest
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient

from app.api.ingest import get_embedder_factory, get_store
from app.core.vectorstore.qdrant import QdrantStore
from app.main import create_app


class _FakeEmbedder:
    def embed_documents(self, texts):
        return [[float(len(t) % 5), 1.0, 0.0] for t in texts]

    def embed_query(self, text):
        return [0.0, 1.0, 0.0]

    @property
    def dimension(self) -> int:
        return 3


@pytest.fixture
def client():
    app = create_app()
    store = QdrantStore(client=QdrantClient(":memory:"))
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_embedder_factory] = lambda: (lambda name, **kw: _FakeEmbedder())
    return TestClient(app)


def test_options_lists_registered_techniques(client):
    response = client.get("/options")
    assert response.status_code == 200
    body = response.json()
    assert {"fixed", "recursive", "token", "semantic"} <= set(body["chunkings"])
    assert {"gemini", "e5", "paraphrase"} <= set(body["embeddings"])
    assert {"gemini", "custom"} <= set(body["llms"])


def test_ingest_uploads_and_stores(client):
    files = [("files", ("a.txt", io.BytesIO(b"Para one.\n\nPara two here.\n\nPara three."), "text/plain"))]
    data = {"base": "viagem", "chunkings": "recursive", "embeddings": "gemini"}
    response = client.post("/ingest", data=data, files=files)
    assert response.status_code == 200
    body = response.json()
    assert body["collections"] == ["viagem__recursive__gemini"]
    assert body["total_chunks"] > 0
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_ingest_api.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'app.api.ingest'`.

- [ ] **Step 3: Implementar o router de options**

`backend/app/api/options.py`:

```python
"""Endpoint exposing the available techniques from the registries."""
from fastapi import APIRouter

from app.core.chunking.base import chunking_registry
from app.core.embedding.base import embedding_registry
from app.core.llm.base import llm_registry

router = APIRouter()


@router.get("/options")
def options() -> dict[str, list[str]]:
    """List the registered chunking, embedding, and LLM techniques."""
    return {
        "chunkings": chunking_registry.names(),
        "embeddings": embedding_registry.names(),
        "llms": llm_registry.names(),
    }
```

Importante: o módulo deve garantir que os pacotes que fazem o registro foram importados. Como `app.main` importa estes routers e os pacotes, garanta no `app/main.py` (Step 5) que `app.core.chunking`, `app.core.embedding`, `app.core.llm` sejam importados para popular os registries.

- [ ] **Step 4: Implementar o router de ingest**

`backend/app/api/ingest.py`:

```python
"""Endpoint to ingest uploaded documents."""
from collections.abc import Callable

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.core.embedding.base import Embedder, build_embedder
from app.core.vectorstore.qdrant import QdrantStore
from app.ingestion.pipeline import ingest_documents
from app.ingestion.schemas import Document, IngestConfig, IngestResult

router = APIRouter()


def get_store() -> QdrantStore:
    """FastAPI dependency providing the vector store."""
    return QdrantStore()


def get_embedder_factory() -> Callable[..., Embedder]:
    """FastAPI dependency providing the embedder factory."""
    return build_embedder


def _csv(value: str) -> list[str]:
    """Split a comma-separated form field into a clean list."""
    return [item.strip() for item in value.split(",") if item.strip()]


@router.post("/ingest", response_model=IngestResult)
async def ingest(
    base: str = Form(...),
    chunkings: str = Form(...),
    embeddings: str = Form(...),
    files: list[UploadFile] = File(...),
    store: QdrantStore = Depends(get_store),
    embedder_factory: Callable[..., Embedder] = Depends(get_embedder_factory),
) -> IngestResult:
    """Ingest uploaded documents under the given configuration."""
    documents = [
        Document(name=file.filename, text=(await file.read()).decode("utf-8"))
        for file in files
    ]
    config = IngestConfig(
        base=base, chunkings=_csv(chunkings), embeddings=_csv(embeddings)
    )
    return ingest_documents(documents, config, store, embedder_factory=embedder_factory)
```

- [ ] **Step 5: Incluir os routers e garantir o registro no `main.py`**

Atualize `backend/app/main.py` para importar os pacotes de técnicas (popula registries) e incluir os routers. A versão final:

```python
"""FastAPI application entry point."""
from contextlib import asynccontextmanager

from fastapi import FastAPI

import app.core.chunking  # noqa: F401  registers chunking strategies
import app.core.embedding  # noqa: F401  registers embedding providers
import app.core.llm  # noqa: F401  registers LLM providers
from app.api import health, ingest, options
from app.core.db import models  # noqa: F401  registers models on Base.metadata
from app.core.db.base import create_all


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create database tables on startup."""
    create_all()
    yield


def create_app() -> FastAPI:
    """Create and configure the FastAPI instance."""
    app = FastAPI(title="Ditto - Fatia A", lifespan=lifespan)
    app.include_router(health.router)
    app.include_router(options.router)
    app.include_router(ingest.router)
    return app


app = create_app()
```

- [ ] **Step 6: Rodar e ver passar**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_ingest_api.py -v`
Expected: PASS (2 testes). Suíte inteira verde, zero warnings.

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/options.py backend/app/api/ingest.py backend/app/main.py backend/tests/test_ingest_api.py
git commit -m "feat: /options and /ingest endpoints"
```

---

## Self-Review

**Spec coverage (Plano 3 cobre spec §5 e parte de §9, §10):**
- Chunker interface + registry + 4 estratégias `fixed/recursive/token/semantic` (spec §5) → Tasks 1, 2. ✅
- Pipeline: para cada `chunking × embedding` corta → embeda → cria/popula coleção Qdrant com metadata (spec §5, §4.3) → Task 3. ✅
- `/ingest` (upload `.txt`/texto + config) e `/options` (técnicas para o front, spec §9) → Task 4. ✅
- Semantic usa Embedder (spec §5) → Task 2. ✅
- Metadata por vetor `source_doc/chunking_strategy/embedding_model/chunk_index/text` (spec §4.3) → Task 3. ✅
- Testes sem rede (embedder fake, Qdrant em memória) + documento real de viagem (`database/faq_manus_completa.md`) → Tasks 3, 4. ✅

**Placeholder scan:** sem TBD/TODO; todos os passos com código/comando concreto. ✅

**Type consistency:**
- `Chunker.split(text) -> list[str]` consistente entre base, splitters, semantic e testes. ✅
- `build_chunker(name, **kwargs)`; semantic recebe `embedder`; pipeline injeta só para semantic. ✅
- `ingest_documents(documents, config, store, embedder_factory)` consistente entre pipeline, `__init__` e testes. ✅
- `IngestConfig(base, chunkings, embeddings)` / `IngestResult(collections, total_chunks)` / `Document(name, text)` consistentes entre schemas, pipeline, API e testes. ✅
- Dependências FastAPI `get_store` / `get_embedder_factory` sobrescritas nos testes para rodar sem rede. ✅
- `QdrantStore`/`collection_name` reusados do Plano 2 sem alteração. ✅

**Escopo:** só ingestão (chunkers, pipeline, endpoints). Nada de RAG/avaliação/experimentos (planos seguintes). Sem over-build. ✅
