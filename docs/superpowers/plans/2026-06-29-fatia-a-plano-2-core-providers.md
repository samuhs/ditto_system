# Fatia A — Plano 2: Core Providers — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar as peças compartilhadas do `core/` que falam com modelos e com o banco vetorial: provedores de LLM (Gemini + custom OpenAI-compatible), de Embedding (Gemini + dois locais multilíngues) e o wrapper do Qdrant — todos atrás de interface + registry, e testados sem depender de rede.

**Architecture:** Cada categoria (`llm`, `embedding`, `vectorstore`) vive em um subpacote de `backend/app/core/`. Provedores são classes que implementam uma interface mínima e recebem seu cliente por injeção (default constrói o real), o que permite testar com fakes. Registries (instâncias do `Registry[T]` do Plano 1) expõem os provedores por nome. O wrapper Qdrant é testado contra uma instância em memória (`QdrantClient(":memory:")`).

**Tech Stack:** Python 3.11, LangChain (`langchain-google-genai`, `langchain-openai`, `langchain-core`), sentence-transformers (opcional, grupo `[local]`), qdrant-client, pytest.

## Global Constraints

- **Código em inglês:** identificadores, docstrings e mensagens de erro de runtime em inglês. Apenas dados de domínio em PT-BR. Onde exemplos abaixo tragam prosa em português, traduza.
- PEP-8; docstrings nas funções públicas; comentários só quando agregam.
- Sem duplicação: todo acesso a LLM/embedding/vetor passa por estes módulos do `core/`.
- Toda técnica plugável vive atrás de interface + registry (reusa `app.core.registry.Registry`).
- **Testes sem rede:** nenhum teste pode chamar a API do Gemini nem baixar pesos de modelo. Provedores recebem o cliente/modelo por injeção; testes passam fakes. Imports de bibliotecas pesadas (sentence-transformers/torch) são lazy, dentro do método que constrói o modelo real.
- Modelo de LLM default: `gemini-2.5-flash-lite`. Embedding Gemini: `text-embedding-004`. Locais: `intfloat/multilingual-e5-small` e `paraphrase-multilingual-MiniLM-L12-v2`.
- Segredos via ambiente (`get_settings().gemini_api_key`); nunca hardcoded nem commitados.
- venv de dev em `backend/.venv` (Homebrew Python 3.13). Rodar testes: `cd backend && ./.venv/bin/python -m pytest`. Saída pristina (zero warnings).
- Commits frequentes, um por task.

---

## File Structure

```
backend/
  pyproject.toml                     # + deps langchain/qdrant; grupo opcional [local]
  app/core/
    llm/
      __init__.py                    # expõe LLM, llm_registry, build_llm
      base.py                        # interface LLM (ABC) + Registry + build_llm
      gemini.py                      # GeminiLLM
      custom.py                      # CustomLLM (endpoint OpenAI-compatible)
    embedding/
      __init__.py                    # expõe Embedder, embedding_registry, build_embedder
      base.py                        # interface Embedder (ABC) + Registry + build_embedder
      gemini.py                      # GeminiEmbedder
      huggingface.py                 # E5Embedder, ParaphraseEmbedder (lazy import)
    vectorstore/
      __init__.py                    # expõe QdrantStore, collection_name
      qdrant.py                      # QdrantStore wrapper + helper collection_name
  tests/
    test_llm.py
    test_embedding.py
    test_vectorstore.py
```

---

### Task 1: Dependências + interface de LLM + provedores Gemini e custom

**Files:**
- Modify: `backend/pyproject.toml` (adicionar dependências de runtime)
- Create: `backend/app/core/llm/__init__.py`
- Create: `backend/app/core/llm/base.py`
- Create: `backend/app/core/llm/gemini.py`
- Create: `backend/app/core/llm/custom.py`
- Create: `backend/tests/test_llm.py`

**Interfaces:**
- Consumes: `app.core.registry.Registry`, `app.core.config.settings.get_settings`.
- Produces:
  - `LLM` (ABC) com método `generate(self, prompt: str) -> str`.
  - `llm_registry: Registry[type[LLM]]` com `"gemini"` e `"custom"` registrados.
  - `build_llm(name: str, **kwargs) -> LLM` → `llm_registry.get(name)(**kwargs)`.
  - `GeminiLLM(model: str = "gemini-2.5-flash-lite", api_key: str | None = None, client=None)`; usa `client.invoke(prompt).content`. Default `client` = `ChatGoogleGenerativeAI(model=..., google_api_key=api_key or get_settings().gemini_api_key)`.
  - `CustomLLM(model: str, base_url: str, api_key: str = "not-needed", client=None)`; default `client` = `ChatOpenAI(model=..., base_url=..., api_key=...)`.

- [ ] **Step 1: Adicionar dependências ao `pyproject.toml`**

No array `dependencies` de `backend/pyproject.toml`, acrescente (mantendo as existentes):

```toml
    "langchain-core>=0.2",
    "langchain-google-genai>=1.0",
    "langchain-openai>=0.1",
```

Logo após a tabela `[project.optional-dependencies]` (que hoje tem só `dev`), acrescente o grupo `local`:

```toml
local = [
    "sentence-transformers>=2.7",
]
```

Instale: `cd backend && ./.venv/bin/pip install -e ".[dev]"` (o grupo `local` fica de fora de propósito).

- [ ] **Step 2: Escrever o teste que falha**

`backend/tests/test_llm.py`:

```python
"""Tests for the LLM provider interface and implementations."""
import pytest

from app.core.llm.base import LLM, build_llm, llm_registry
from app.core.llm.custom import CustomLLM
from app.core.llm.gemini import GeminiLLM


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeClient:
    """Stands in for a LangChain chat client."""

    def __init__(self) -> None:
        self.last_prompt: str | None = None

    def invoke(self, prompt: str) -> _FakeResponse:
        self.last_prompt = prompt
        return _FakeResponse("generated answer")


def test_gemini_generate_uses_injected_client():
    client = _FakeClient()
    llm = GeminiLLM(client=client)
    result = llm.generate("question?")
    assert result == "generated answer"
    assert client.last_prompt == "question?"


def test_custom_generate_uses_injected_client():
    client = _FakeClient()
    llm = CustomLLM(model="qwen2", base_url="http://localhost:11434/v1", client=client)
    assert llm.generate("hi") == "generated answer"


def test_providers_registered():
    assert set(llm_registry.names()) >= {"gemini", "custom"}


def test_build_llm_constructs_provider():
    client = _FakeClient()
    llm = build_llm("gemini", client=client)
    assert isinstance(llm, GeminiLLM)
    assert isinstance(llm, LLM)
    assert llm.generate("x") == "generated answer"
```

- [ ] **Step 3: Rodar e ver falhar**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_llm.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'app.core.llm'`.

- [ ] **Step 4: Implementar a interface e o registry**

`backend/app/core/llm/base.py`:

```python
"""LLM provider interface, registry, and factory."""
from abc import ABC, abstractmethod

from app.core.registry import Registry


class LLM(ABC):
    """Minimal interface every LLM provider implements."""

    @abstractmethod
    def generate(self, prompt: str) -> str:
        """Return the model's answer for a single prompt."""


llm_registry: Registry[type[LLM]] = Registry("llm")


def build_llm(name: str, **kwargs) -> LLM:
    """Instantiate a registered LLM provider by name."""
    return llm_registry.get(name)(**kwargs)
```

- [ ] **Step 5: Implementar `GeminiLLM`**

`backend/app/core/llm/gemini.py`:

```python
"""Gemini LLM provider (via langchain-google-genai)."""
from app.core.config.settings import get_settings
from app.core.llm.base import LLM, llm_registry


class GeminiLLM(LLM):
    """Generates answers with a Google Gemini chat model."""

    def __init__(
        self,
        model: str = "gemini-2.5-flash-lite",
        api_key: str | None = None,
        client=None,
    ) -> None:
        if client is None:
            from langchain_google_genai import ChatGoogleGenerativeAI

            client = ChatGoogleGenerativeAI(
                model=model,
                google_api_key=api_key or get_settings().gemini_api_key,
            )
        self._client = client

    def generate(self, prompt: str) -> str:
        """Return the Gemini answer for the prompt."""
        return self._client.invoke(prompt).content


llm_registry.register("gemini", GeminiLLM)
```

- [ ] **Step 6: Implementar `CustomLLM`**

`backend/app/core/llm/custom.py`:

```python
"""Custom LLM provider for any OpenAI-compatible endpoint (Ollama, vLLM, etc.)."""
from app.core.llm.base import LLM, llm_registry


class CustomLLM(LLM):
    """Generates answers via an OpenAI-compatible chat endpoint."""

    def __init__(
        self,
        model: str = "qwen2",
        base_url: str = "http://localhost:11434/v1",
        api_key: str = "not-needed",
        client=None,
    ) -> None:
        if client is None:
            from langchain_openai import ChatOpenAI

            client = ChatOpenAI(model=model, base_url=base_url, api_key=api_key)
        self._client = client

    def generate(self, prompt: str) -> str:
        """Return the endpoint's answer for the prompt."""
        return self._client.invoke(prompt).content


llm_registry.register("custom", CustomLLM)
```

- [ ] **Step 7: Implementar o `__init__.py` que garante o registro**

`backend/app/core/llm/__init__.py`:

```python
"""LLM providers package. Importing it registers all built-in providers."""
from app.core.llm.base import LLM, build_llm, llm_registry
from app.core.llm.custom import CustomLLM
from app.core.llm.gemini import GeminiLLM

__all__ = ["LLM", "build_llm", "llm_registry", "GeminiLLM", "CustomLLM"]
```

Note: `test_llm.py` importa `custom` e `gemini` diretamente, o que dispara os `register(...)`. O `__init__` acima garante o registro também para quem importar só o pacote.

- [ ] **Step 8: Rodar e ver passar**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_llm.py -v`
Expected: PASS (4 testes). Rode a suíte inteira (`./.venv/bin/python -m pytest`) — verde, zero warnings.

- [ ] **Step 9: Commit**

```bash
git add backend/pyproject.toml backend/app/core/llm backend/tests/test_llm.py
git commit -m "feat: LLM providers (gemini, custom) behind interface + registry"
```

---

### Task 2: Interface de Embedding + provedor Gemini

**Files:**
- Create: `backend/app/core/embedding/__init__.py`
- Create: `backend/app/core/embedding/base.py`
- Create: `backend/app/core/embedding/gemini.py`
- Create: `backend/tests/test_embedding.py`

**Interfaces:**
- Consumes: `app.core.registry.Registry`, `app.core.config.settings.get_settings`.
- Produces:
  - `Embedder` (ABC) com `embed_documents(self, texts: list[str]) -> list[list[float]]`, `embed_query(self, text: str) -> list[float]`, e propriedade `dimension: int`.
  - `embedding_registry: Registry[type[Embedder]]` com `"gemini"` registrado (mais os locais na Task 3).
  - `build_embedder(name: str, **kwargs) -> Embedder`.
  - `GeminiEmbedder(model: str = "text-embedding-004", api_key: str | None = None, client=None)`; `embed_documents` → `client.embed_documents(texts)`, `embed_query` → `client.embed_query(text)`; `dimension` derivado de uma query de sondagem cacheada.

- [ ] **Step 1: Escrever o teste que falha**

`backend/tests/test_embedding.py`:

```python
"""Tests for the embedding provider interface and implementations."""
from app.core.embedding.base import Embedder, build_embedder, embedding_registry
from app.core.embedding.gemini import GeminiEmbedder


class _FakeEmbeddings:
    """Stands in for a LangChain embeddings client (3-dim vectors)."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(t)), 1.0, 2.0] for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return [float(len(text)), 1.0, 2.0]


def test_gemini_embed_documents_uses_injected_client():
    emb = GeminiEmbedder(client=_FakeEmbeddings())
    vectors = emb.embed_documents(["ab", "cde"])
    assert vectors == [[2.0, 1.0, 2.0], [3.0, 1.0, 2.0]]


def test_gemini_embed_query_and_dimension():
    emb = GeminiEmbedder(client=_FakeEmbeddings())
    assert emb.embed_query("xy") == [2.0, 1.0, 2.0]
    assert emb.dimension == 3


def test_gemini_registered_and_built():
    assert "gemini" in embedding_registry.names()
    emb = build_embedder("gemini", client=_FakeEmbeddings())
    assert isinstance(emb, Embedder)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_embedding.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'app.core.embedding'`.

- [ ] **Step 3: Implementar a interface e o registry**

`backend/app/core/embedding/base.py`:

```python
"""Embedding provider interface, registry, and factory."""
from abc import ABC, abstractmethod

from app.core.registry import Registry


class Embedder(ABC):
    """Minimal interface every embedding provider implements."""

    @abstractmethod
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of documents."""

    @abstractmethod
    def embed_query(self, text: str) -> list[float]:
        """Embed a single query string."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Length of the vectors this embedder produces."""


embedding_registry: Registry[type[Embedder]] = Registry("embedding")


def build_embedder(name: str, **kwargs) -> Embedder:
    """Instantiate a registered embedding provider by name."""
    return embedding_registry.get(name)(**kwargs)
```

- [ ] **Step 4: Implementar `GeminiEmbedder`**

`backend/app/core/embedding/gemini.py`:

```python
"""Gemini embedding provider (via langchain-google-genai)."""
from app.core.config.settings import get_settings
from app.core.embedding.base import Embedder, embedding_registry


class GeminiEmbedder(Embedder):
    """Embeds text with a Google Gemini embedding model."""

    def __init__(
        self,
        model: str = "text-embedding-004",
        api_key: str | None = None,
        client=None,
    ) -> None:
        if client is None:
            from langchain_google_genai import GoogleGenerativeAIEmbeddings

            client = GoogleGenerativeAIEmbeddings(
                model=model,
                google_api_key=api_key or get_settings().gemini_api_key,
            )
        self._client = client
        self._dimension: int | None = None

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of documents."""
        return self._client.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        """Embed a single query string."""
        return self._client.embed_query(text)

    @property
    def dimension(self) -> int:
        """Vector length, derived once from a probe query and cached."""
        if self._dimension is None:
            self._dimension = len(self.embed_query("dimension probe"))
        return self._dimension


embedding_registry.register("gemini", GeminiEmbedder)
```

- [ ] **Step 5: Implementar o `__init__.py`**

`backend/app/core/embedding/__init__.py`:

```python
"""Embedding providers package. Importing it registers the built-in providers."""
from app.core.embedding.base import Embedder, build_embedder, embedding_registry
from app.core.embedding.gemini import GeminiEmbedder

__all__ = ["Embedder", "build_embedder", "embedding_registry", "GeminiEmbedder"]
```

- [ ] **Step 6: Rodar e ver passar**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_embedding.py -v`
Expected: PASS (3 testes). Suíte inteira verde, zero warnings.

- [ ] **Step 7: Commit**

```bash
git add backend/app/core/embedding backend/tests/test_embedding.py
git commit -m "feat: embedding interface + gemini provider"
```

---

### Task 3: Provedores de embedding locais (e5 e paraphrase) com import lazy

**Files:**
- Create: `backend/app/core/embedding/huggingface.py`
- Modify: `backend/app/core/embedding/__init__.py` (registrar os locais)
- Modify: `backend/tests/test_embedding.py` (testes dos locais com modelo fake)

**Interfaces:**
- Consumes: `app.core.embedding.base.Embedder`, `embedding_registry`.
- Produces:
  - `HuggingFaceEmbedder(model_name: str, model=None)` — base que envolve um `SentenceTransformer`; `embed_documents`/`embed_query` chamam `model.encode(...)` e devolvem listas de floats; `dimension` via `model.get_sentence_embedding_dimension()`. Import de `sentence_transformers` é lazy (só quando `model is None`).
  - `E5Embedder` → `HuggingFaceEmbedder(model_name="intfloat/multilingual-e5-small")`, registrado como `"e5"`.
  - `ParaphraseEmbedder` → `HuggingFaceEmbedder(model_name="paraphrase-multilingual-MiniLM-L12-v2")`, registrado como `"paraphrase"`.

- [ ] **Step 1: Escrever os testes que falham**

Acrescente a `backend/tests/test_embedding.py`:

```python
from app.core.embedding.huggingface import E5Embedder, ParaphraseEmbedder


class _FakeSentenceTransformer:
    """Stands in for a SentenceTransformer model (4-dim)."""

    def encode(self, text):
        if isinstance(text, list):
            return [[float(len(t)), 0.0, 0.0, 1.0] for t in text]
        return [float(len(text)), 0.0, 0.0, 1.0]

    def get_sentence_embedding_dimension(self) -> int:
        return 4


def test_e5_embeds_with_injected_model():
    emb = E5Embedder(model=_FakeSentenceTransformer())
    assert emb.embed_documents(["abc"]) == [[3.0, 0.0, 0.0, 1.0]]
    assert emb.embed_query("ab") == [2.0, 0.0, 0.0, 1.0]
    assert emb.dimension == 4


def test_local_embedders_registered():
    assert {"e5", "paraphrase"} <= set(embedding_registry.names())


def test_paraphrase_built_with_injected_model():
    emb = ParaphraseEmbedder(model=_FakeSentenceTransformer())
    assert emb.dimension == 4
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_embedding.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'app.core.embedding.huggingface'`.

- [ ] **Step 3: Implementar os provedores locais**

`backend/app/core/embedding/huggingface.py`:

```python
"""Local sentence-transformers embedding providers (multilingual)."""
from app.core.embedding.base import Embedder, embedding_registry


class HuggingFaceEmbedder(Embedder):
    """Embeds text with a local SentenceTransformer model."""

    def __init__(self, model_name: str, model=None) -> None:
        if model is None:
            from sentence_transformers import SentenceTransformer

            model = SentenceTransformer(model_name)
        self._model = model

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of documents."""
        return [list(map(float, vector)) for vector in self._model.encode(texts)]

    def embed_query(self, text: str) -> list[float]:
        """Embed a single query string."""
        return list(map(float, self._model.encode(text)))

    @property
    def dimension(self) -> int:
        """Vector length reported by the underlying model."""
        return self._model.get_sentence_embedding_dimension()


class E5Embedder(HuggingFaceEmbedder):
    """multilingual-e5-small local embedder."""

    def __init__(self, model=None) -> None:
        super().__init__("intfloat/multilingual-e5-small", model=model)


class ParaphraseEmbedder(HuggingFaceEmbedder):
    """paraphrase-multilingual-MiniLM local embedder."""

    def __init__(self, model=None) -> None:
        super().__init__("paraphrase-multilingual-MiniLM-L12-v2", model=model)


embedding_registry.register("e5", E5Embedder)
embedding_registry.register("paraphrase", ParaphraseEmbedder)
```

- [ ] **Step 4: Registrar no `__init__.py`**

Atualize `backend/app/core/embedding/__init__.py`:

```python
"""Embedding providers package. Importing it registers the built-in providers."""
from app.core.embedding.base import Embedder, build_embedder, embedding_registry
from app.core.embedding.gemini import GeminiEmbedder
from app.core.embedding.huggingface import (
    E5Embedder,
    HuggingFaceEmbedder,
    ParaphraseEmbedder,
)

__all__ = [
    "Embedder",
    "build_embedder",
    "embedding_registry",
    "GeminiEmbedder",
    "HuggingFaceEmbedder",
    "E5Embedder",
    "ParaphraseEmbedder",
]
```

- [ ] **Step 5: Rodar e ver passar**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_embedding.py -v`
Expected: PASS (6 testes no arquivo). Suíte inteira verde, zero warnings. Confirme que `sentence-transformers`/`torch` NÃO foram importados (os testes injetam o modelo fake; o import lazy não dispara).

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/embedding/huggingface.py backend/app/core/embedding/__init__.py backend/tests/test_embedding.py
git commit -m "feat: local multilingual embedders (e5, paraphrase) with lazy import"
```

---

### Task 4: Wrapper do Qdrant (coleções nomeadas, metadata, busca)

**Files:**
- Create: `backend/app/core/vectorstore/__init__.py`
- Create: `backend/app/core/vectorstore/qdrant.py`
- Create: `backend/tests/test_vectorstore.py`

**Interfaces:**
- Consumes: `qdrant_client`, `app.core.config.settings.get_settings`.
- Produces:
  - `collection_name(base: str, chunking: str, embedding: str) -> str` → `"{base}__{chunking}__{embedding}"`.
  - `QdrantStore(client=None)` — default `client = QdrantClient(url=get_settings().qdrant_url)`; testes passam `QdrantClient(":memory:")`.
    - `ensure_collection(name: str, dimension: int) -> None` — cria a coleção (distância cosine) se não existir.
    - `add(name: str, vectors: list[list[float]], payloads: list[dict]) -> None` — insere pontos com ids sequenciais e o payload (metadata) de cada vetor.
    - `search(name: str, query_vector: list[float], top_k: int = 5, where: dict | None = None) -> list[dict]` — retorna lista de `{"score": float, "payload": dict}`; `where` filtra por igualdade de campos do payload.

- [ ] **Step 1: Escrever o teste que falha**

`backend/tests/test_vectorstore.py`:

```python
"""Tests for the Qdrant vector store wrapper (in-memory)."""
import pytest
from qdrant_client import QdrantClient

from app.core.vectorstore.qdrant import QdrantStore, collection_name


@pytest.fixture
def store():
    return QdrantStore(client=QdrantClient(":memory:"))


def test_collection_name_convention():
    assert collection_name("viagem", "recursive", "e5") == "viagem__recursive__e5"


def test_add_and_search_returns_nearest(store):
    name = "viagem__recursive__e5"
    store.ensure_collection(name, dimension=3)
    store.add(
        name,
        vectors=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
        payloads=[{"source_doc": "a.txt", "text": "alpha"},
                  {"source_doc": "b.txt", "text": "beta"}],
    )
    hits = store.search(name, query_vector=[0.9, 0.1, 0.0], top_k=1)
    assert len(hits) == 1
    assert hits[0]["payload"]["text"] == "alpha"
    assert hits[0]["score"] > 0


def test_search_with_payload_filter(store):
    name = "viagem__fixed__gemini"
    store.ensure_collection(name, dimension=3)
    store.add(
        name,
        vectors=[[1.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
        payloads=[{"source_doc": "a.txt"}, {"source_doc": "b.txt"}],
    )
    hits = store.search(name, query_vector=[1.0, 0.0, 0.0], top_k=5,
                        where={"source_doc": "b.txt"})
    assert [h["payload"]["source_doc"] for h in hits] == ["b.txt"]


def test_ensure_collection_is_idempotent(store):
    store.ensure_collection("c", dimension=3)
    store.ensure_collection("c", dimension=3)
    hits = store.search("c", query_vector=[1.0, 0.0, 0.0], top_k=1)
    assert hits == []
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_vectorstore.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'app.core.vectorstore'`.

- [ ] **Step 3: Implementar o wrapper**

`backend/app/core/vectorstore/qdrant.py`:

```python
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
        results = self._client.search(
            collection_name=name,
            query_vector=query_vector,
            limit=top_k,
            query_filter=query_filter,
        )
        return [{"score": point.score, "payload": point.payload} for point in results]
```

- [ ] **Step 4: Implementar o `__init__.py`**

`backend/app/core/vectorstore/__init__.py`:

```python
"""Vector store package."""
from app.core.vectorstore.qdrant import QdrantStore, collection_name

__all__ = ["QdrantStore", "collection_name"]
```

- [ ] **Step 5: Rodar e ver passar**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_vectorstore.py -v`
Expected: PASS (4 testes). Suíte inteira verde, zero warnings.

Nota: se a versão instalada do `qdrant-client` emitir `DeprecationWarning` sobre `search` (algumas versões recomendam `query_points`), trate como achado: ou migre para `query_points` mantendo o mesmo contrato de retorno, ou adicione um filtro de warning direcionado em `pyproject.toml`. A saída deve ficar pristina.

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/vectorstore backend/tests/test_vectorstore.py
git commit -m "feat: qdrant vector store wrapper with named collections and metadata"
```

---

## Self-Review

**Spec coverage (Plano 2 cobre spec §4.1, §4.2, §4.3):**
- LLM interface + Gemini + custom (spec §4.1) → Task 1. ✅ Default `gemini-2.5-flash-lite`; custom OpenAI-compatible.
- Embedder interface + Gemini + 2 locais multilíngues + slot custom (spec §4.2) → Tasks 2, 3. ✅ `text-embedding-004`, `multilingual-e5-small`, `paraphrase-multilingual-MiniLM`.
- Qdrant wrapper: coleções nomeadas `base__chunking__embedding`, metadata, busca com filtro (spec §4.3) → Task 4. ✅
- Tudo atrás de interface + registry (spec §2, §7) → todas as tasks reusam `Registry`. ✅
- Provedores trocáveis por configuração → `build_llm`/`build_embedder` por nome. ✅

**Placeholder scan:** sem TBD/TODO; todos os passos têm código ou comando concreto. ✅

**Type consistency:**
- `build_llm`/`build_embedder` retornam `LLM`/`Embedder`; registries guardam `type[LLM]`/`type[Embedder]`. ✅
- `generate(prompt) -> str` consistente entre `base`, `gemini`, `custom` e testes. ✅
- `embed_documents/embed_query/dimension` consistentes entre `base`, `gemini`, `huggingface` e testes. ✅
- `QdrantStore.ensure_collection/add/search` e `collection_name` consistentes entre wrapper, `__init__` e testes. ✅
- Injeção de cliente (`client=`/`model=`) presente em todos os provedores para testes sem rede. ✅

**Escopo:** apenas os provedores do `core/`; nada de ingestão/RAG/avaliação (planos seguintes). Sem over-build. ✅
