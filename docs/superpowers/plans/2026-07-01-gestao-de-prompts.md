# Gestão de Prompts — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permitir visualizar e editar os prompts de cada técnica (naive, agentic, multi_query) e gravar um snapshot dos prompts usados por cada experimento no momento do disparo.

**Architecture:** Prompts passam a viver em arquivos `.md` sob `backend/prompts/<tecnica>/<chave>.md`, carregados por um módulo `app/core/prompts` (com defaults embutidos e validação de placeholders). As técnicas recebem os prompts por injeção. Ao criar um experimento, o backend grava um snapshot em `experiment.config["prompts"]`; o orchestrator injeta esse snapshot. A UI ganha botões read-only na tela do experimento (mostram o snapshot) e uma página global "Prompts" para editar os templates.

**Tech Stack:** Backend FastAPI + SQLAlchemy (Python 3.11 no container, 3.13 no venv local). Frontend React + TypeScript + Mantine v7 + Vitest.

## Global Constraints

- Técnicas cobertas: **naive**, **agentic**, **multi_query**. Métricas de avaliação ficam fora.
- Placeholders são estilo `str.format`: `naive/answer` → `{context}`,`{question}`; `agentic/decide` e `agentic/answer` → `{context}`,`{question}`; `multi_query/generate` → `{n}`,`{question}`.
- Snapshot é gravado em `experiment.config["prompts"]` (coluna JSON já existente) — **sem migração de schema**.
- Se um `.md` estiver ausente, usar o default embutido (nunca quebrar).
- Injeção mantém compatibilidade: construtores aceitam `prompts=None` e caem no default.
- Testes backend rodam de `backend/` com `.venv/bin/python -m pytest`. Testes frontend com `cd frontend && npm run test -- --run`.
- Placeholders extras num prompt são permitidos; só os obrigatórios são exigidos na escrita.

---

## File Structure

- `backend/app/core/prompts/__init__.py` — re-exporta a API pública do módulo.
- `backend/app/core/prompts/loader.py` — manifesto, defaults, load/save/validate.
- `backend/prompts/naive/answer.md`, `backend/prompts/agentic/decide.md`, `backend/prompts/agentic/answer.md`, `backend/prompts/multi_query/generate.md` — templates iniciais.
- `backend/app/core/rag/naive.py`, `agentic.py`, `backend/app/core/retrieval/multi_query.py` — passam a injetar prompts.
- `backend/app/api/experiments.py`, `backend/app/experiments/orchestrator.py` — snapshot + injeção.
- `backend/app/api/prompts.py` — endpoints GET/PUT.
- `backend/app/main.py` — registra o router de prompts.
- `docker-compose.yml` — bind mount de `./backend/prompts`.
- `frontend/src/api/types.ts`, `frontend/src/api/client.ts` — tipos e funções.
- `frontend/src/pages/ExperimentDetailPage.tsx` — botões + modal de snapshot.
- `frontend/src/pages/PromptsPage.tsx`, `frontend/src/App.tsx`, `frontend/src/components/Sidebar.tsx` — página de edição + navegação.

---

### Task 1: Módulo de prompts (manifesto, defaults, loader, validação) + arquivos .md

**Files:**
- Create: `backend/app/core/prompts/__init__.py`
- Create: `backend/app/core/prompts/loader.py`
- Create: `backend/prompts/naive/answer.md`
- Create: `backend/prompts/agentic/decide.md`
- Create: `backend/prompts/agentic/answer.md`
- Create: `backend/prompts/multi_query/generate.md`
- Test: `backend/tests/test_prompts_loader.py`

**Interfaces:**
- Produces:
  - `PROMPT_SPECS: dict[str, dict[str, set[str]]]`
  - `DEFAULT_PROMPTS: dict[str, dict[str, str]]`
  - `prompts_dir() -> Path`
  - `load_prompt(technique: str, key: str) -> str`
  - `load_technique(technique: str) -> dict[str, str]`
  - `load_all() -> dict[str, dict[str, str]]`
  - `validate_placeholders(technique: str, key: str, text: str) -> None` (raises `ValueError`)
  - `save_prompt(technique: str, key: str, text: str) -> None`
  - Chave/técnica desconhecida → `KeyError`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_prompts_loader.py`:

```python
"""Tests for the file-backed prompt loader."""
import pytest

from app.core.prompts import (
    DEFAULT_PROMPTS,
    PROMPT_SPECS,
    load_all,
    load_prompt,
    load_technique,
    save_prompt,
    validate_placeholders,
)


@pytest.fixture(autouse=True)
def prompts_tmp(tmp_path, monkeypatch):
    """Point the loader at a temp dir so tests never touch repo files."""
    monkeypatch.setenv("PROMPTS_DIR", str(tmp_path))
    return tmp_path


def test_load_prompt_falls_back_to_default_when_file_absent():
    assert load_prompt("naive", "answer") == DEFAULT_PROMPTS["naive"]["answer"]


def test_save_then_load_roundtrip(prompts_tmp):
    text = "New answer using {context} and {question}."
    save_prompt("naive", "answer", text)
    assert (prompts_tmp / "naive" / "answer.md").exists()
    assert load_prompt("naive", "answer") == text


def test_load_technique_returns_all_keys():
    result = load_technique("agentic")
    assert set(result) == {"decide", "answer"}


def test_load_all_covers_manifest():
    result = load_all()
    assert set(result) == set(PROMPT_SPECS)
    assert set(result["multi_query"]) == {"generate"}


def test_validate_placeholders_accepts_extra_but_requires_mandatory():
    validate_placeholders("naive", "answer", "{context} {question} {extra}")
    with pytest.raises(ValueError, match="context"):
        validate_placeholders("naive", "answer", "only {question}")


def test_save_prompt_rejects_missing_placeholder(prompts_tmp):
    with pytest.raises(ValueError):
        save_prompt("multi_query", "generate", "no placeholders here")


def test_unknown_prompt_raises_keyerror():
    with pytest.raises(KeyError):
        load_prompt("naive", "nope")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_prompts_loader.py -v`
Expected: FAIL (ModuleNotFoundError: No module named 'app.core.prompts').

- [ ] **Step 3: Create the loader module**

Create `backend/app/core/prompts/loader.py`:

```python
"""File-backed prompt templates with built-in defaults and placeholder validation."""
import os
import re
from pathlib import Path

# Required placeholders per technique/key.
PROMPT_SPECS: dict[str, dict[str, set[str]]] = {
    "naive": {"answer": {"context", "question"}},
    "agentic": {
        "decide": {"question", "context"},
        "answer": {"context", "question"},
    },
    "multi_query": {"generate": {"n", "question"}},
}

# Built-in fallbacks (used when a .md file is absent).
DEFAULT_PROMPTS: dict[str, dict[str, str]] = {
    "naive": {
        "answer": (
            "Use the context below to answer the question. If the context is not "
            "enough, say what you can.\n\nContext:\n{context}\n\n"
            "Question: {question}\n\nAnswer:"
        ),
    },
    "agentic": {
        "decide": (
            "You are answering a question using retrieved context. Based on the "
            "context so far, decide your next action. Reply with exactly one line:\n"
            "'SEARCH: <a better search query>' if you need more information, or\n"
            "'ANSWER: <your final answer>' if the context is sufficient.\n\n"
            "Question: {question}\n\nContext so far:\n{context}"
        ),
        "answer": (
            "Answer the question using the context.\n\nContext:\n{context}\n\n"
            "Question: {question}\n\nAnswer:"
        ),
    },
    "multi_query": {
        "generate": (
            "Generate {n} alternative search queries, one per line, that rephrase "
            "the following question to improve document retrieval. Question: {question}"
        ),
    },
}

_PLACEHOLDER_RE = re.compile(r"{(\w+)}")


def prompts_dir() -> Path:
    """Root directory of prompt files (env PROMPTS_DIR overrides the default)."""
    env = os.environ.get("PROMPTS_DIR")
    if env:
        return Path(env)
    # loader.py is at <root>/app/core/prompts/loader.py -> root is parents[3]
    return Path(__file__).resolve().parents[3] / "prompts"


def _check_known(technique: str, key: str) -> None:
    if technique not in PROMPT_SPECS or key not in PROMPT_SPECS[technique]:
        raise KeyError(f"unknown prompt: {technique}/{key}")


def load_prompt(technique: str, key: str) -> str:
    """Read a prompt's .md; fall back to the built-in default when absent."""
    _check_known(technique, key)
    path = prompts_dir() / technique / f"{key}.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return DEFAULT_PROMPTS[technique][key]


def load_technique(technique: str) -> dict[str, str]:
    """All prompts for one technique."""
    if technique not in PROMPT_SPECS:
        raise KeyError(f"unknown technique: {technique}")
    return {key: load_prompt(technique, key) for key in PROMPT_SPECS[technique]}


def load_all() -> dict[str, dict[str, str]]:
    """All prompts for every technique in the manifest."""
    return {technique: load_technique(technique) for technique in PROMPT_SPECS}


def validate_placeholders(technique: str, key: str, text: str) -> None:
    """Raise ValueError if any required placeholder is missing from text."""
    _check_known(technique, key)
    present = set(_PLACEHOLDER_RE.findall(text))
    missing = PROMPT_SPECS[technique][key] - present
    if missing:
        raise ValueError(
            f"prompt {technique}/{key} missing required placeholder(s): "
            + ", ".join("{" + m + "}" for m in sorted(missing))
        )


def save_prompt(technique: str, key: str, text: str) -> None:
    """Validate placeholders and write the prompt's .md file."""
    _check_known(technique, key)
    validate_placeholders(technique, key, text)
    path = prompts_dir() / technique / f"{key}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
```

Create `backend/app/core/prompts/__init__.py`:

```python
"""Prompt management: file-backed templates per technique with defaults."""
from app.core.prompts.loader import (
    DEFAULT_PROMPTS,
    PROMPT_SPECS,
    load_all,
    load_prompt,
    load_technique,
    prompts_dir,
    save_prompt,
    validate_placeholders,
)

__all__ = [
    "DEFAULT_PROMPTS",
    "PROMPT_SPECS",
    "load_all",
    "load_prompt",
    "load_technique",
    "prompts_dir",
    "save_prompt",
    "validate_placeholders",
]
```

- [ ] **Step 4: Create the .md files with the default content**

Write each file with exactly the corresponding default text (same strings as `DEFAULT_PROMPTS`), single trailing newline allowed:

`backend/prompts/naive/answer.md`:
```
Use the context below to answer the question. If the context is not enough, say what you can.

Context:
{context}

Question: {question}

Answer:
```

`backend/prompts/agentic/decide.md`:
```
You are answering a question using retrieved context. Based on the context so far, decide your next action. Reply with exactly one line:
'SEARCH: <a better search query>' if you need more information, or
'ANSWER: <your final answer>' if the context is sufficient.

Question: {question}

Context so far:
{context}
```

`backend/prompts/agentic/answer.md`:
```
Answer the question using the context.

Context:
{context}

Question: {question}

Answer:
```

`backend/prompts/multi_query/generate.md`:
```
Generate {n} alternative search queries, one per line, that rephrase the following question to improve document retrieval. Question: {question}
```

Note: os testes usam `PROMPTS_DIR` temporário, então não dependem destes arquivos; eles são o conteúdo de produção. Não é preciso que o texto do `.md` seja byte-idêntico ao default (o default é só fallback), mas mantenha o significado.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_prompts_loader.py -v`
Expected: PASS (7 passed).

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/prompts backend/prompts backend/tests/test_prompts_loader.py
git commit -m "feat: file-backed prompt loader with defaults and placeholder validation"
```

---

### Task 2: Injeção de prompts em naive, agentic e multi_query

**Files:**
- Modify: `backend/app/core/rag/naive.py`
- Modify: `backend/app/core/rag/agentic.py`
- Modify: `backend/app/core/retrieval/multi_query.py`
- Test: `backend/tests/test_rag_naive.py`, `backend/tests/test_rag_agentic.py`, `backend/tests/test_prompts_injection.py`

**Interfaces:**
- Consumes: `load_technique` de Task 1.
- Produces:
  - `NaiveRAG(retriever, llm, prompts: dict[str, str] | None = None)`
  - `AgenticRAG(retriever, llm, prompts: dict[str, str] | None = None, max_steps: int = 3)`
  - `MultiQueryRetriever(store, collection, embedder, llm, top_k=5, n_queries=3, prompts: dict[str, str] | None = None)`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_rag_naive.py`:

```python
def test_naive_rag_uses_injected_answer_prompt():
    llm = _EchoLLM()
    rag = NaiveRAG(_StubRetriever(), llm, prompts={"answer": "CUSTOM {context} :: {question}"})
    rag.answer("Where is the center?")
    assert llm.last_prompt.startswith("CUSTOM ")
    assert "Where is the center?" in llm.last_prompt
```

Create `backend/tests/test_prompts_injection.py`:

```python
"""Injected prompts flow into agentic RAG and the multi_query retriever."""
from app.core.rag.agentic import AgenticRAG
from app.core.retrieval.multi_query import MultiQueryRetriever


class _StubRetriever:
    def retrieve(self, query: str) -> list[dict]:
        return [{"text": "ctx", "source_doc": "a.txt", "chunk_index": 0, "score": 0.9}]


class _EchoLLM:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return "ANSWER: done"


def test_agentic_uses_injected_decide_prompt():
    llm = _EchoLLM()
    rag = AgenticRAG(
        _StubRetriever(),
        llm,
        prompts={"decide": "DECIDE {question} // {context}", "answer": "ANS {context} {question}"},
    )
    rag.answer("q?")
    assert llm.prompts[0].startswith("DECIDE ")


class _FakeEmbedder:
    def embed_documents(self, texts):
        return [self.embed_query(t) for t in texts]

    def embed_query(self, text):
        return [1.0, 0.0, 0.0]

    @property
    def dimension(self) -> int:
        return 3


class _RecordingLLM:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return "variation one\nvariation two"


def test_multi_query_uses_injected_prompt():
    from qdrant_client import QdrantClient

    from app.core.vectorstore.qdrant import QdrantStore

    store = QdrantStore(client=QdrantClient(":memory:"))
    llm = _RecordingLLM()
    retriever = MultiQueryRetriever(
        store=store,
        collection="missing__x__y",
        embedder=_FakeEmbedder(),
        llm=llm,
        prompts={"generate": "MQ {n} :: {question}"},
    )
    # retrieve() will query an empty/missing collection; we only assert the prompt used.
    try:
        retriever.retrieve("q?")
    except Exception:
        pass
    assert llm.prompts and llm.prompts[0].startswith("MQ 3 :: ")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/test_rag_naive.py tests/test_prompts_injection.py -v`
Expected: FAIL (`NaiveRAG`/`AgenticRAG`/`MultiQueryRetriever` don't accept `prompts`).

- [ ] **Step 3: Update naive.py**

Replace `backend/app/core/rag/naive.py` with:

```python
"""Naive RAG: retrieve top-k, stuff into the prompt, generate."""
from app.core.llm.base import LLM
from app.core.prompts import load_technique
from app.core.rag.base import RAG, RAGResult, format_context, rag_registry
from app.core.retrieval.base import Retriever


class NaiveRAG(RAG):
    """Single-shot retrieve-then-generate technique."""

    def __init__(
        self, retriever: Retriever, llm: LLM, prompts: dict[str, str] | None = None
    ) -> None:
        self._retriever = retriever
        self._llm = llm
        resolved = prompts or load_technique("naive")
        self._answer_prompt = resolved["answer"]

    def answer(self, query: str) -> RAGResult:
        """Retrieve context and generate a grounded answer."""
        contexts = self._retriever.retrieve(query)
        prompt = self._answer_prompt.format(
            context=format_context(contexts), question=query
        )
        generated = self._llm.generate(prompt)
        return RAGResult(answer=generated.strip(), contexts=contexts)


rag_registry.register("naive", NaiveRAG)
```

- [ ] **Step 4: Update agentic.py**

Replace `backend/app/core/rag/agentic.py` with:

```python
"""Agentic RAG: a bounded loop where the LLM decides to search or answer."""
from app.core.llm.base import LLM
from app.core.prompts import load_technique
from app.core.rag.base import RAG, RAGResult, format_context, rag_registry
from app.core.retrieval.base import Retriever

_SEARCH_TAG = "SEARCH:"
_ANSWER_TAG = "ANSWER:"


class AgenticRAG(RAG):
    """Iteratively retrieves and lets the LLM decide when to answer."""

    def __init__(
        self,
        retriever: Retriever,
        llm: LLM,
        prompts: dict[str, str] | None = None,
        max_steps: int = 3,
    ) -> None:
        self._retriever = retriever
        self._llm = llm
        self._max_steps = max_steps
        resolved = prompts or load_technique("agentic")
        self._decide_prompt = resolved["decide"]
        self._answer_prompt = resolved["answer"]

    def answer(self, query: str) -> RAGResult:
        """Run the bounded search-or-answer loop and return the result."""
        contexts: list[dict] = []
        current_query = query
        for _ in range(self._max_steps):
            contexts.extend(self._retriever.retrieve(current_query))
            decision = self._llm.generate(
                self._decide_prompt.format(
                    question=query, context=format_context(contexts)
                )
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
            self._answer_prompt.format(
                question=query, context=format_context(contexts)
            )
        )
        return RAGResult(answer=final.strip(), contexts=contexts)


rag_registry.register("agentic", AgenticRAG)
```

- [ ] **Step 5: Update multi_query.py**

Replace `backend/app/core/retrieval/multi_query.py` with:

```python
"""Multi-query retriever: expands the query with LLM-generated variations."""
from app.core.embedding.base import Embedder
from app.core.llm.base import LLM
from app.core.prompts import load_technique
from app.core.retrieval.base import Retriever, retrieval_registry
from app.core.retrieval.similarity import SimilarityRetriever
from app.core.vectorstore.qdrant import QdrantStore


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
        prompts: dict[str, str] | None = None,
    ) -> None:
        self._base = SimilarityRetriever(store, collection, embedder, top_k=top_k)
        self._llm = llm
        self._n_queries = n_queries
        resolved = prompts or load_technique("multi_query")
        self._prompt = resolved["generate"]

    def _variations(self, query: str) -> list[str]:
        """Ask the LLM for alternative phrasings of the query."""
        raw = self._llm.generate(
            self._prompt.format(n=self._n_queries, question=query)
        )
        return [line.strip() for line in raw.splitlines() if line.strip()]

    def retrieve(self, query: str) -> list[dict]:
        """Union retrieval over the query and its variations, deduplicated."""
        merged: dict[tuple, dict] = {}
        for candidate in [query, *self._variations(query)]:
            for context in self._base.retrieve(candidate):
                key = (context["source_doc"], context["chunk_index"])
                merged.setdefault(key, context)
        return list(merged.values())


retrieval_registry.register("multi_query", MultiQueryRetriever)
```

- [ ] **Step 6: Run the full backend suite to verify nothing regressed**

Run: `cd backend && .venv/bin/python -m pytest tests/test_rag_naive.py tests/test_rag_agentic.py tests/test_prompts_injection.py tests/test_retrievers_advanced.py -v`
Expected: PASS (all green).

- [ ] **Step 7: Commit**

```bash
git add backend/app/core/rag/naive.py backend/app/core/rag/agentic.py backend/app/core/retrieval/multi_query.py backend/tests/test_rag_naive.py backend/tests/test_prompts_injection.py
git commit -m "feat: inject prompts into naive, agentic and multi_query"
```

---

### Task 3: Snapshot no disparo + injeção no orchestrator + prompts no GET

**Files:**
- Modify: `backend/app/api/experiments.py`
- Modify: `backend/app/experiments/orchestrator.py`
- Test: `backend/tests/test_experiments_api.py`

**Interfaces:**
- Consumes: `PROMPT_SPECS`, `load_technique` (Task 1); construtores com `prompts=` (Task 2).
- Produces: `experiment.config["prompts"] = {technique: {key: text}}`; GET `/experiments/{id}` retorna `"prompts"`.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_experiments_api.py` (o arquivo já importa `io` e `json` no topo). Adicione:

```python
def test_experiment_snapshots_prompts(client):
    config = {
        "base": "viagem",
        "chunkings": ["recursive"],
        "embeddings": ["gemini"],
        "rags": ["naive"],
        "retrievers": ["similarity"],
        "metrics": ["answer_relevancy"],
    }
    files = {"questions": ("q.csv", io.BytesIO(b"pergunta\nOnde fica o centro?\n"), "text/csv")}
    data = {"config": json.dumps(config)}
    resp = client.post("/experiments", data=data, files=files)
    assert resp.status_code == 200
    exp_id = resp.json()["id"]

    detail = client.get(f"/experiments/{exp_id}").json()
    assert "prompts" in detail
    assert "naive" in detail["prompts"]
    assert "answer" in detail["prompts"]["naive"]
    assert "{context}" in detail["prompts"]["naive"]["answer"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_experiments_api.py::test_experiment_snapshots_prompts -v`
Expected: FAIL (`prompts` not in detail / KeyError).

- [ ] **Step 3: Snapshot em create_experiment**

In `backend/app/api/experiments.py`, add the import near the top:

```python
from app.core.prompts import PROMPT_SPECS, load_technique
```

Add this helper above `create_experiment`:

```python
def _snapshot_prompts(config: ExperimentConfig) -> dict[str, dict[str, str]]:
    """Capture the current prompts of every technique the experiment uses."""
    techniques = list(config.rags)
    if "multi_query" in config.retrievers:
        techniques.append("multi_query")
    return {t: load_technique(t) for t in techniques if t in PROMPT_SPECS}
```

Change the experiment creation. Replace:

```python
        experiment = Experiment(name=parsed.name, status="pending", config=parsed.model_dump())
```

with:

```python
        config_dump = parsed.model_dump()
        config_dump["prompts"] = _snapshot_prompts(parsed)
        experiment = Experiment(name=parsed.name, status="pending", config=config_dump)
```

- [ ] **Step 4: Return prompts in get_experiment**

In `backend/app/api/experiments.py`, inside `get_experiment`, the return dict already reads `cfg = experiment.config or {}`. Add the `prompts` key to the returned dict (alongside `error` and `progress`):

```python
            "prompts": cfg.get("prompts"),
```

- [ ] **Step 5: Inject snapshot in the orchestrator**

In `backend/app/experiments/orchestrator.py`, change `_build_retriever` to accept prompts:

```python
def _build_retriever(deps: ExperimentDeps, name: str, collection: str, embedder, llm, prompts=None):
    """Build a retriever, injecting the llm/prompts only for retrievers that need it."""
    kwargs = {"store": deps.store, "collection": collection, "embedder": embedder}
    if name == "multi_query":
        kwargs["llm"] = llm
        kwargs["prompts"] = prompts
    return deps.retriever_factory(name, **kwargs)
```

Inside `run_experiment`, after loading `experiment` and before the product loop, read the snapshot:

```python
        prompt_snapshot = (experiment.config or {}).get("prompts", {})
```

In the loop, change the retriever and rag construction lines. Replace:

```python
            retriever = _build_retriever(deps, retriever_name, col, embedder, llm)
            rag = deps.rag_factory(rag_name, retriever=retriever, llm=llm)
```

with:

```python
            retriever = _build_retriever(
                deps, retriever_name, col, embedder, llm,
                prompts=prompt_snapshot.get("multi_query"),
            )
            rag = deps.rag_factory(
                rag_name, retriever=retriever, llm=llm,
                prompts=prompt_snapshot.get(rag_name),
            )
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/test_experiments_api.py tests/test_orchestrator.py -v`
Expected: PASS (existing tests still green + new snapshot test passes).

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/experiments.py backend/app/experiments/orchestrator.py backend/tests/test_experiments_api.py
git commit -m "feat: snapshot prompts on experiment creation and inject them in the run"
```

---

### Task 4: Endpoints de prompts + wiring + bind mount no compose

**Files:**
- Create: `backend/app/api/prompts.py`
- Modify: `backend/app/main.py`
- Modify: `docker-compose.yml`
- Test: `backend/tests/test_prompts_api.py`

**Interfaces:**
- Consumes: `PROMPT_SPECS`, `load_all`, `save_prompt` (Task 1).
- Produces:
  - `GET /prompts` → `{technique: {key: {"text": str, "required_placeholders": [str]}}}`
  - `PUT /prompts/{technique}/{key}` body `{"text": str}` → `{"technique","key","text"}`; 404 desconhecido; 422 placeholder faltando.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_prompts_api.py`:

```python
"""Tests for the prompts endpoints."""
import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMPTS_DIR", str(tmp_path))
    return TestClient(create_app())


def test_list_prompts_returns_manifest_and_text(client):
    body = client.get("/prompts").json()
    assert "naive" in body
    assert "answer" in body["naive"]
    assert "{context}" in body["naive"]["answer"]["text"]
    assert "context" in body["naive"]["answer"]["required_placeholders"]


def test_update_prompt_persists_and_is_returned(client):
    new_text = "Answer with {context} and {question} now."
    resp = client.put("/prompts/naive/answer", json={"text": new_text})
    assert resp.status_code == 200
    assert client.get("/prompts").json()["naive"]["answer"]["text"] == new_text


def test_update_prompt_missing_placeholder_returns_422(client):
    resp = client.put("/prompts/naive/answer", json={"text": "no placeholders"})
    assert resp.status_code == 422


def test_update_unknown_prompt_returns_404(client):
    resp = client.put("/prompts/naive/nope", json={"text": "x"})
    assert resp.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_prompts_api.py -v`
Expected: FAIL (404 for /prompts — router not registered).

- [ ] **Step 3: Create the prompts router**

Create `backend/app/api/prompts.py`:

```python
"""Endpoints to view and edit prompt templates per technique."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.prompts import PROMPT_SPECS, load_all, save_prompt

router = APIRouter()


class PromptUpdate(BaseModel):
    """Body for updating a prompt template."""

    text: str


@router.get("/prompts")
def list_prompts() -> dict:
    """Return every technique's prompts and their required placeholders."""
    texts = load_all()
    return {
        technique: {
            key: {
                "text": texts[technique][key],
                "required_placeholders": sorted(PROMPT_SPECS[technique][key]),
            }
            for key in PROMPT_SPECS[technique]
        }
        for technique in PROMPT_SPECS
    }


@router.put("/prompts/{technique}/{key}")
def update_prompt(technique: str, key: str, body: PromptUpdate) -> dict:
    """Validate placeholders and persist a prompt template."""
    if technique not in PROMPT_SPECS or key not in PROMPT_SPECS.get(technique, {}):
        raise HTTPException(status_code=404, detail=f"unknown prompt: {technique}/{key}")
    try:
        save_prompt(technique, key, body.text)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"technique": technique, "key": key, "text": body.text}
```

- [ ] **Step 4: Register the router**

In `backend/app/main.py`, update the import line:

```python
from app.api import experiments, health, ingest, options, prompts
```

and add inside `create_app`, after the other `include_router` calls:

```python
    app.include_router(prompts.router)
```

- [ ] **Step 5: Add the bind mount to docker-compose.yml**

In `docker-compose.yml`, under the `api:` service, add a `volumes` block (below `build: ./backend`):

```yaml
    volumes:
      - ./backend/prompts:/app/prompts
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/test_prompts_api.py -v`
Expected: PASS (4 passed).

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/prompts.py backend/app/main.py docker-compose.yml backend/tests/test_prompts_api.py
git commit -m "feat: prompts GET/PUT endpoints + durable bind mount for prompt files"
```

---

### Task 5: Frontend — cliente da API e tipos

**Files:**
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/api/client.ts`
- Test: `frontend/src/api/client.test.ts`

**Interfaces:**
- Produces:
  - `PromptInfo { text: string; required_placeholders: string[] }`
  - `PromptsResponse = Record<string, Record<string, PromptInfo>>`
  - `ExperimentDetail.prompts?: Record<string, Record<string, string>>`
  - `getPrompts(): Promise<PromptsResponse>`
  - `savePrompt(technique, key, text): Promise<{technique; key; text}>`

- [ ] **Step 1: Write the failing test**

Append to `frontend/src/api/client.test.ts` (dentro do `describe("api client", ...)`), e adicione `getPrompts, savePrompt` ao import do topo:

```typescript
  it("getPrompts fetches the prompts endpoint", async () => {
    const body = { naive: { answer: { text: "{context} {question}", required_placeholders: ["context", "question"] } } };
    vi.stubGlobal("fetch", mockFetchOnce(body));
    await expect(getPrompts()).resolves.toEqual(body);
    expect(fetch).toHaveBeenCalledWith("/api/prompts");
  });

  it("savePrompt PUTs the new text", async () => {
    const fetchMock = mockFetchOnce({ technique: "naive", key: "answer", text: "t {context} {question}" });
    vi.stubGlobal("fetch", fetchMock);
    await savePrompt("naive", "answer", "t {context} {question}");
    expect(fetchMock).toHaveBeenCalledWith("/api/prompts/naive/answer", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: "t {context} {question}" }),
    });
  });
```

Update the import at the top of the file to include the new functions:

```typescript
import {
  createExperiment,
  getExperiment,
  getOptions,
  getPrompts,
  ingest,
  listExperiments,
  savePrompt,
} from "./client";
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm run test -- --run src/api/client.test.ts`
Expected: FAIL (getPrompts/savePrompt not exported).

- [ ] **Step 3: Add the types**

In `frontend/src/api/types.ts`, add:

```typescript
export interface PromptInfo {
  text: string;
  required_placeholders: string[];
}

export type PromptsResponse = Record<string, Record<string, PromptInfo>>;
```

and add the `prompts` field to `ExperimentDetail`:

```typescript
  prompts?: Record<string, Record<string, string>>;
```

- [ ] **Step 4: Add the client functions**

In `frontend/src/api/client.ts`, extend the type import to include `PromptsResponse`:

```typescript
import type {
  ExperimentDetail,
  ExperimentRef,
  ExperimentSummary,
  IngestResult,
  Options,
  PromptsResponse,
} from "./types";
```

and add:

```typescript
export async function getPrompts(): Promise<PromptsResponse> {
  return asJson<PromptsResponse>(await fetch(`${BASE}/prompts`));
}

export async function savePrompt(
  technique: string,
  key: string,
  text: string,
): Promise<{ technique: string; key: string; text: string }> {
  return asJson(
    await fetch(`${BASE}/prompts/${technique}/${key}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    }),
  );
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd frontend && npm run test -- --run src/api/client.test.ts`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/types.ts frontend/src/api/client.ts frontend/src/api/client.test.ts
git commit -m "feat(front): prompts API client and types"
```

---

### Task 6: Frontend — botões de prompt + modal na tela do experimento

**Files:**
- Modify: `frontend/src/pages/ExperimentDetailPage.tsx`
- Modify: `frontend/src/styles/global.css`
- Test: `frontend/src/pages/ExperimentDetailPage.test.tsx`

**Interfaces:**
- Consumes: `ExperimentDetail.prompts` (Task 5), vindo de `getExperiment`.

- [ ] **Step 1: Write the failing test**

Append to `frontend/src/pages/ExperimentDetailPage.test.tsx`:

```typescript
  it("shows a prompt button per technique and opens a read-only modal", async () => {
    vi.mocked(client.getExperiment).mockResolvedValue({
      id: 7,
      name: "kind-ember-89",
      status: "done",
      prompts: {
        naive: { answer: "Answer using {context} and {question}." },
      },
      results: [
        {
          chunking: "recursive", embedding: "gemini", rag: "naive", retriever: "similarity",
          question: "Q", answer: "A", scores: { faithfulness: 0.8 }, latency_ms: 1, tokens: 1,
        },
      ],
    });
    renderPage();
    const user = userEvent.setup();
    const btn = await screen.findByRole("button", { name: /prompts: naive/i });
    await user.click(btn);
    expect(await screen.findByText(/Answer using/)).toBeInTheDocument();
  });

  it("shows a notice when the experiment has no prompt snapshot", async () => {
    vi.mocked(client.getExperiment).mockResolvedValue({
      id: 7, name: "old-exp", status: "done", results: [
        { chunking: "recursive", embedding: "gemini", rag: "naive", retriever: "similarity",
          question: "Q", answer: "A", scores: { faithfulness: 0.8 }, latency_ms: 1, tokens: 1 },
      ],
    });
    renderPage();
    expect(await screen.findByText(/Prompts não registrados/i)).toBeInTheDocument();
  });
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm run test -- --run src/pages/ExperimentDetailPage.test.tsx`
Expected: FAIL (no prompt buttons / notice).

- [ ] **Step 3: Add prompt state and UI to ExperimentDetailPage**

In `frontend/src/pages/ExperimentDetailPage.tsx`, add a state near the other `useState` hooks:

```tsx
  const [promptTech, setPromptTech] = useState<string | null>(null);
```

Compute the technique list from the snapshot (after `const results = ...`):

```tsx
  const promptTechniques = detail?.prompts ? Object.keys(detail.prompts) : [];
```

Render the buttons row immediately **above** the `<div className="ditto-filter-bar">` (only in the `results.length > 0` branch; if you prefer, render it right after the status `<Group>`). Insert:

```tsx
          {detail.prompts && promptTechniques.length > 0 ? (
            <div className="ditto-prompt-bar">
              <span className="ditto-eyebrow">Prompts</span>
              {promptTechniques.map((tech) => (
                <Button
                  key={tech}
                  size="xs"
                  variant="light"
                  color="violet"
                  onClick={() => setPromptTech(tech)}
                >
                  Prompts: {tech}
                </Button>
              ))}
            </div>
          ) : (
            <Text size="xs" c="dimmed" mb="sm">
              Prompts não registrados para este experimento.
            </Text>
          )}
```

Add the modal near the existing result modal (before the closing `</div>` of the component):

```tsx
      <Modal
        opened={promptTech !== null}
        onClose={() => setPromptTech(null)}
        title="Prompts usados neste experimento"
        size="lg"
        centered
        overlayProps={{ backgroundOpacity: 0.6, blur: 3 }}
      >
        {promptTech && detail?.prompts?.[promptTech] && (
          <div>
            <Text className="ditto-eyebrow" mb={10}>
              {promptTech}
            </Text>
            {Object.entries(detail.prompts[promptTech]).map(([key, text]) => (
              <div key={key} style={{ marginBottom: 18 }}>
                <Text fw={700} size="sm" mb={4}>
                  {key}
                </Text>
                <pre className="ditto-prompt-pre">{text}</pre>
              </div>
            ))}
          </div>
        )}
      </Modal>
```

Ensure `Modal` is imported (it already is from Task in current file). If the buttons row is placed inside the `results.length > 0` branch, the "no snapshot" notice for experiments **with** results but **without** prompts is still shown by the ternary above. For the empty-results + paused/failed case, the notice is not required (the existing empty Alert covers it).

- [ ] **Step 4: Add CSS**

Append to `frontend/src/styles/global.css`:

```css
/* Prompt buttons on the experiment page */
.ditto-prompt-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
}
.ditto-prompt-pre {
  font-family: var(--font-mono);
  font-size: 0.8rem;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  background: rgba(8, 4, 15, 0.6);
  border: 1px solid var(--stroke);
  border-radius: var(--radius-md);
  padding: 14px 16px;
  color: var(--text-hi);
  margin: 0;
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npm run test -- --run src/pages/ExperimentDetailPage.test.tsx`
Expected: PASS (existing detail tests + 2 new).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/ExperimentDetailPage.tsx frontend/src/styles/global.css frontend/src/pages/ExperimentDetailPage.test.tsx
git commit -m "feat(front): read-only prompt snapshot buttons on the experiment page"
```

---

### Task 7: Frontend — página Prompts + rota + navegação

**Files:**
- Create: `frontend/src/pages/PromptsPage.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/Sidebar.tsx`
- Test: `frontend/src/pages/PromptsPage.test.tsx`

**Interfaces:**
- Consumes: `getPrompts`, `savePrompt` (Task 5).

- [ ] **Step 1: Write the failing test**

Create `frontend/src/pages/PromptsPage.test.tsx`:

```typescript
import { MantineProvider } from "@mantine/core";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as client from "../api/client";
import { PromptsPage } from "./PromptsPage";

vi.mock("../api/client");

function renderPage() {
  return render(
    <MantineProvider>
      <PromptsPage />
    </MantineProvider>,
  );
}

beforeEach(() => {
  vi.mocked(client.getPrompts).mockResolvedValue({
    naive: { answer: { text: "Use {context} and {question}.", required_placeholders: ["context", "question"] } },
  });
  vi.mocked(client.savePrompt).mockResolvedValue({ technique: "naive", key: "answer", text: "x" });
});

describe("PromptsPage", () => {
  it("loads and shows the prompt text and its required placeholders", async () => {
    renderPage();
    expect(await screen.findByDisplayValue(/Use \{context\} and \{question\}/)).toBeInTheDocument();
    expect(screen.getByText(/context/)).toBeInTheDocument();
  });

  it("saves an edited prompt", async () => {
    renderPage();
    const user = userEvent.setup();
    const area = await screen.findByDisplayValue(/Use \{context\}/);
    await user.clear(area);
    await user.type(area, "New {context} {question}");
    await user.click(screen.getByRole("button", { name: /salvar/i }));
    await waitFor(() =>
      expect(client.savePrompt).toHaveBeenCalledWith("naive", "answer", "New {context} {question}"),
    );
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm run test -- --run src/pages/PromptsPage.test.tsx`
Expected: FAIL (PromptsPage does not exist).

- [ ] **Step 3: Create PromptsPage**

Create `frontend/src/pages/PromptsPage.tsx`:

```tsx
import { Alert, Button, Group, Stack, Text, Textarea } from "@mantine/core";
import { useEffect, useState } from "react";

import { getPrompts, savePrompt } from "../api/client";
import type { PromptsResponse } from "../api/types";
import { PageHeader } from "../components/PageHeader";

export function PromptsPage() {
  const [prompts, setPrompts] = useState<PromptsResponse | null>(null);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [savingKey, setSavingKey] = useState<string | null>(null);
  const [savedKey, setSavedKey] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<Record<string, string>>({});

  useEffect(() => {
    getPrompts()
      .then((data) => {
        setPrompts(data);
        const initial: Record<string, string> = {};
        for (const [tech, keys] of Object.entries(data)) {
          for (const [key, info] of Object.entries(keys)) {
            initial[`${tech}/${key}`] = info.text;
          }
        }
        setDrafts(initial);
      })
      .catch((e) => setError(String(e)));
  }, []);

  async function handleSave(tech: string, key: string) {
    const id = `${tech}/${key}`;
    setSavingKey(id);
    setSavedKey(null);
    setSaveError((s) => ({ ...s, [id]: "" }));
    try {
      await savePrompt(tech, key, drafts[id]);
      setSavedKey(id);
    } catch (e) {
      setSaveError((s) => ({ ...s, [id]: String(e) }));
    } finally {
      setSavingKey(null);
    }
  }

  return (
    <div>
      <PageHeader
        eyebrow="Configuração"
        title="Prompts"
        subtitle="Edite os templates usados por cada técnica. Alterações valem para os próximos experimentos — experimentos já rodados mantêm o snapshot que usaram."
      />

      {error && (
        <Alert color="red" variant="light" title="Erro ao carregar" radius="lg" maw={820}>
          {error}
        </Alert>
      )}

      {prompts &&
        Object.entries(prompts).map(([tech, keys]) => (
          <div key={tech} className="ditto-glass" style={{ padding: 24, maxWidth: 820, marginBottom: 20 }}>
            <Text className="ditto-eyebrow" mb={14}>
              {tech}
            </Text>
            <Stack gap="lg">
              {Object.entries(keys).map(([key, info]) => {
                const id = `${tech}/${key}`;
                return (
                  <div key={id}>
                    <Text fw={700} size="sm" mb={6}>
                      {key}
                    </Text>
                    <Textarea
                      autosize
                      minRows={4}
                      value={drafts[id] ?? ""}
                      onChange={(e) => setDrafts((d) => ({ ...d, [id]: e.currentTarget.value }))}
                      styles={{ input: { fontFamily: "var(--font-mono)", fontSize: "0.82rem" } }}
                    />
                    <Text size="xs" c="dimmed" mt={6}>
                      Placeholders obrigatórios: {info.required_placeholders.map((p) => `{${p}}`).join(", ")}
                    </Text>
                    {saveError[id] && (
                      <Text size="xs" c="red.4" mt={4}>
                        {saveError[id]}
                      </Text>
                    )}
                    <Group mt={8}>
                      <Button
                        size="xs"
                        variant="light"
                        color="violet"
                        loading={savingKey === id}
                        onClick={() => handleSave(tech, key)}
                      >
                        Salvar
                      </Button>
                      {savedKey === id && (
                        <Text size="xs" c="#07f285">
                          Prompt salvo
                        </Text>
                      )}
                    </Group>
                  </div>
                );
              })}
            </Stack>
          </div>
        ))}
    </div>
  );
}
```

- [ ] **Step 4: Add the route**

In `frontend/src/App.tsx`, import the page:

```tsx
import { PromptsPage } from "./pages/PromptsPage";
```

and add a route after the `/results/:id` route:

```tsx
                <Route
                  path="/prompts"
                  element={
                    <PageTransition>
                      <PromptsPage />
                    </PageTransition>
                  }
                />
```

- [ ] **Step 5: Add the sidebar nav item**

In `frontend/src/components/Sidebar.tsx`, add to the `NAV` array (after the results entry). Reuse an existing icon to avoid new assets:

```tsx
  { to: "/prompts", label: "Prompts", icon: <FlaskIcon /> },
```

(`FlaskIcon` is already imported in this file.)

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd frontend && npm run test -- --run`
Expected: PASS (all suites, including App.test.tsx which must still find its nav links).

- [ ] **Step 7: Build to verify types**

Run: `cd frontend && npm run build`
Expected: build succeeds (no TS errors).

- [ ] **Step 8: Commit**

```bash
git add frontend/src/pages/PromptsPage.tsx frontend/src/App.tsx frontend/src/components/Sidebar.tsx frontend/src/pages/PromptsPage.test.tsx
git commit -m "feat(front): Prompts management page with per-prompt editing"
```

---

## Deploy (após todas as tasks)

```bash
cd /Users/samuelhenriquesilva/Desktop/doutorado/ditto_system
make front-build
docker compose up -d --build api frontend
```

O bind mount `./backend/prompts:/app/prompts` faz as edições da UI gravarem nos arquivos do host (versionáveis no git). Confirme que nenhum experimento está `running` antes do rebuild da API.
