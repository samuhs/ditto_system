# Fatia A — Plano 6: Experimentos & API — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar o orquestrador que amarra ingestão + RAG + avaliação: para cada combinação `chunking × embedding × rag × retriever`, roda as perguntas de um CSV, gera respostas, mede latência/tokens, avalia com as métricas selecionadas e persiste em `Experiment/ExperimentRun/RunResult`. Expor via endpoints com execução em background e polling.

**Architecture:** Um módulo `app/experiments/` com schemas (Pydantic), gerador de nome, parser de CSV e o orquestrador `run_experiment`. O orquestrador recebe um `ExperimentDeps` injetável (store, fábrica de sessão e as factories de llm/embedder/retriever/rag) para ser testável sem rede e sem Postgres. Router fino em `app/api/experiments.py` cria o experimento, dispara um `BackgroundTask` e expõe consulta por polling. Persistência reusa os models do Plano 1.

**Tech Stack:** Python 3.11, FastAPI (BackgroundTasks), SQLAlchemy, Pydantic v2, pytest (SQLite StaticPool nos testes).

## Global Constraints

- **Código em inglês:** identificadores, docstrings e mensagens de erro em inglês. Apenas dados de domínio (perguntas, respostas) em PT-BR.
- PEP-8; docstrings nas funções públicas; comentários só quando agregam.
- Sem duplicação: o orquestrador consome `build_embedder`/`build_llm`/`build_retriever`/`build_rag`, `QdrantStore`/`collection_name`, `evaluate_sample`/`EvalSample` e os models do `core/`. Nunca reimplementa.
- **Testes sem rede e sem Postgres:** `ExperimentDeps` é injetado; testes usam SQLite em memória (StaticPool, conexão compartilhada), Qdrant em memória e factories fake. Nenhuma chamada de API, nenhum download.
- Composição: produto cartesiano `chunkings × embeddings × rags × retrievers`. LLM de geração e embedder de avaliação são config global do experimento (default `gemini`).
- Operacionais: `latency_ms` medido com `time.perf_counter`; `tokens` = nº de palavras da resposta (proxy aproximado, documentado — a interface `LLM` não expõe contagem de tokens).
- O retriever `multi_query` recebe o `llm`; os demais não (decisão explícita por nome, como o `semantic` na ingestão).
- venv de dev em `backend/.venv`. Rodar testes: `cd backend && ./.venv/bin/python -m pytest`. Saída pristina (zero warnings).
- Commits frequentes, um por task.

---

## File Structure

```
backend/
  app/experiments/
    __init__.py                  # exporta schemas, run_experiment, ExperimentDeps, helpers
    schemas.py                   # ExperimentConfig, QuestionItem
    naming.py                    # generate_experiment_name()
    csv_loader.py                # parse_questions_csv(text)
    orchestrator.py              # ExperimentDeps, run_experiment(...)
  app/api/experiments.py         # router + get_experiment_deps + background wiring
  app/main.py                    # inclui o router de experiments
  tests/
    test_experiment_schemas.py   # naming + csv
    test_orchestrator.py         # run_experiment end-to-end (SQLite + Qdrant em memória)
    test_experiments_api.py      # POST/GET com dependency overrides
```

---

### Task 1: Schemas, gerador de nome e parser de CSV

**Files:**
- Create: `backend/app/experiments/__init__.py` (parcial; completado nas tasks seguintes)
- Create: `backend/app/experiments/schemas.py`
- Create: `backend/app/experiments/naming.py`
- Create: `backend/app/experiments/csv_loader.py`
- Create: `backend/tests/test_experiment_schemas.py`

**Interfaces:**
- Consumes: Pydantic, `csv`, `random`.
- Produces:
  - `QuestionItem` (Pydantic): `text: str`, `reference: str | None = None`.
  - `ExperimentConfig` (Pydantic): `name: str | None = None`, `base: str`, `chunkings: list[str]`, `embeddings: list[str]`, `rags: list[str]`, `retrievers: list[str]`, `metrics: list[str]`, `llm: str = "gemini"`, `eval_embedding: str = "gemini"`.
  - `generate_experiment_name() -> str` → algo como `"brave-otter-42"`.
  - `parse_questions_csv(content: str) -> list[QuestionItem]` — lê colunas `pergunta` (obrigatória; linhas sem ela são puladas) e `resposta_referencia` (opcional; vazia vira `None`).

- [ ] **Step 1: Escrever o teste que falha**

`backend/tests/test_experiment_schemas.py`:

```python
"""Tests for experiment schemas, naming, and CSV parsing."""
from app.experiments.csv_loader import parse_questions_csv
from app.experiments.naming import generate_experiment_name
from app.experiments.schemas import ExperimentConfig, QuestionItem


def test_generate_experiment_name_format():
    name = generate_experiment_name()
    parts = name.split("-")
    assert len(parts) == 3
    assert parts[2].isdigit()


def test_generate_experiment_name_varies():
    names = {generate_experiment_name() for _ in range(20)}
    assert len(names) > 1


def test_parse_questions_csv_with_and_without_reference():
    content = (
        "pergunta,resposta_referencia\n"
        "Onde fica o centro?,Na praca da matriz\n"
        "Tem wifi?,\n"
    )
    items = parse_questions_csv(content)
    assert len(items) == 2
    assert items[0] == QuestionItem(text="Onde fica o centro?", reference="Na praca da matriz")
    assert items[1] == QuestionItem(text="Tem wifi?", reference=None)


def test_parse_questions_csv_skips_blank_rows():
    content = "pergunta,resposta_referencia\n,ignored\nValid question?,\n"
    items = parse_questions_csv(content)
    assert [i.text for i in items] == ["Valid question?"]


def test_experiment_config_defaults():
    config = ExperimentConfig(
        base="viagem",
        chunkings=["recursive"],
        embeddings=["gemini"],
        rags=["naive"],
        retrievers=["similarity"],
        metrics=["answer_relevancy"],
    )
    assert config.name is None
    assert config.llm == "gemini"
    assert config.eval_embedding == "gemini"
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_experiment_schemas.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'app.experiments'`.

- [ ] **Step 3: Implementar os schemas**

`backend/app/experiments/schemas.py`:

```python
"""Pydantic schemas for experiments."""
from pydantic import BaseModel


class QuestionItem(BaseModel):
    """A question to ask, with an optional reference answer."""

    text: str
    reference: str | None = None


class ExperimentConfig(BaseModel):
    """Configuration for one experiment run."""

    name: str | None = None
    base: str
    chunkings: list[str]
    embeddings: list[str]
    rags: list[str]
    retrievers: list[str]
    metrics: list[str]
    llm: str = "gemini"
    eval_embedding: str = "gemini"
```

- [ ] **Step 4: Implementar o gerador de nome**

`backend/app/experiments/naming.py`:

```python
"""Random, human-readable experiment name generator."""
import random

_ADJECTIVES = [
    "brave", "calm", "clever", "eager", "gentle",
    "happy", "jolly", "kind", "lively", "proud",
]
_NOUNS = [
    "otter", "falcon", "maple", "river", "comet",
    "willow", "ember", "cedar", "pebble", "heron",
]


def generate_experiment_name() -> str:
    """Return a random name like 'brave-otter-42'."""
    adjective = random.choice(_ADJECTIVES)
    noun = random.choice(_NOUNS)
    return f"{adjective}-{noun}-{random.randint(10, 99)}"
```

- [ ] **Step 5: Implementar o parser de CSV**

`backend/app/experiments/csv_loader.py`:

```python
"""Parse a questions CSV into QuestionItem objects."""
import csv
import io

from app.experiments.schemas import QuestionItem


def parse_questions_csv(content: str) -> list[QuestionItem]:
    """Parse a CSV with 'pergunta' and optional 'resposta_referencia' columns."""
    reader = csv.DictReader(io.StringIO(content))
    items = []
    for row in reader:
        text = (row.get("pergunta") or "").strip()
        if not text:
            continue
        reference = (row.get("resposta_referencia") or "").strip() or None
        items.append(QuestionItem(text=text, reference=reference))
    return items
```

- [ ] **Step 6: Implementar o `__init__.py` parcial**

`backend/app/experiments/__init__.py`:

```python
"""Experiments package."""
from app.experiments.csv_loader import parse_questions_csv
from app.experiments.naming import generate_experiment_name
from app.experiments.schemas import ExperimentConfig, QuestionItem

__all__ = [
    "parse_questions_csv",
    "generate_experiment_name",
    "ExperimentConfig",
    "QuestionItem",
]
```

- [ ] **Step 7: Rodar e ver passar**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_experiment_schemas.py -v`
Expected: PASS (5 testes). Suíte inteira verde, zero warnings.

- [ ] **Step 8: Commit**

```bash
git add backend/app/experiments backend/tests/test_experiment_schemas.py
git commit -m "feat: experiment schemas, name generator, and CSV parser"
```

---

### Task 2: Orquestrador `run_experiment`

**Files:**
- Create: `backend/app/experiments/orchestrator.py`
- Modify: `backend/app/experiments/__init__.py` (exportar `ExperimentDeps`, `run_experiment`)
- Create: `backend/tests/test_orchestrator.py`

**Interfaces:**
- Consumes: `itertools`, `time`, `datetime`, `app.core.db.models` (Experiment/ExperimentRun/RunResult), `app.core.vectorstore` (QdrantStore/collection_name), `app.core.embedding.build_embedder`, `app.core.llm.build_llm`, `app.core.retrieval.build_retriever`, `app.core.rag.build_rag`, `app.core.evaluation` (evaluate_sample/EvalSample), `app.experiments.schemas`.
- Produces:
  - `ExperimentDeps` (dataclass): `store: QdrantStore`, `session_factory: Callable[[], Session]`, `llm_factory=build_llm`, `embedder_factory=build_embedder`, `retriever_factory=build_retriever`, `rag_factory=build_rag`.
  - `run_experiment(experiment_id: int, config: ExperimentConfig, questions: list[QuestionItem], deps: ExperimentDeps) -> None` — atualiza o `Experiment` para `running`, percorre o produto cartesiano criando um `ExperimentRun` por combinação e um `RunResult` por pergunta (com `generated_answer`, `retrieved_context`, `scores`, `latency_ms`, `tokens`), e finaliza `done` (ou `failed`, guardando o erro em `config["error"]`).

- [ ] **Step 1: Escrever o teste que falha**

`backend/tests/test_orchestrator.py`:

```python
"""End-to-end test for the experiment orchestrator (no network, no Postgres)."""
import pytest
from qdrant_client import QdrantClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db.base import Base
from app.core.db.models import Experiment
from app.core.vectorstore.qdrant import QdrantStore
from app.experiments.orchestrator import ExperimentDeps, run_experiment
from app.experiments.schemas import ExperimentConfig, QuestionItem
from app.ingestion.pipeline import ingest_documents
from app.ingestion.schemas import Document, IngestConfig


class _FakeEmbedder:
    """Deterministic 3-dim embedder; no network."""

    def embed_documents(self, texts):
        return [self.embed_query(t) for t in texts]

    def embed_query(self, text):
        return [float(len(text) % 5), 1.0, 0.0]

    @property
    def dimension(self) -> int:
        return 3


class _FakeLLM:
    """Returns a fixed answer; no network."""

    def generate(self, prompt: str) -> str:
        return "The center is around the main square."


def _embedder_factory(name, **kwargs):
    return _FakeEmbedder()


def _llm_factory(name, **kwargs):
    return _FakeLLM()


@pytest.fixture
def session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def test_run_experiment_persists_results(session_factory):
    store = QdrantStore(client=QdrantClient(":memory:"))
    ingest_documents(
        [Document(name="a.txt", text="Para one.\n\nPara two here.\n\nPara three.")],
        IngestConfig(base="viagem", chunkings=["recursive"], embeddings=["gemini"]),
        store,
        embedder_factory=_embedder_factory,
    )

    session = session_factory()
    experiment = Experiment(name="brave-otter-42", status="pending", config={})
    session.add(experiment)
    session.commit()
    experiment_id = experiment.id
    session.close()

    config = ExperimentConfig(
        base="viagem",
        chunkings=["recursive"],
        embeddings=["gemini"],
        rags=["naive"],
        retrievers=["similarity"],
        metrics=["answer_relevancy", "faithfulness"],
    )
    deps = ExperimentDeps(
        store=store,
        session_factory=session_factory,
        llm_factory=_llm_factory,
        embedder_factory=_embedder_factory,
    )

    run_experiment(experiment_id, config, [QuestionItem(text="Where is the center?")], deps)

    check = session_factory()
    stored = check.get(Experiment, experiment_id)
    assert stored.status == "done"
    assert len(stored.runs) == 1
    run = stored.runs[0]
    assert (run.chunking, run.embedding, run.rag_technique, run.retriever) == (
        "recursive", "gemini", "naive", "similarity",
    )
    assert len(run.results) == 1
    result = run.results[0]
    assert result.generated_answer == "The center is around the main square."
    assert "answer_relevancy" in result.scores
    assert result.latency_ms >= 0
    assert result.tokens > 0
    check.close()


def test_run_experiment_cartesian_product(session_factory):
    store = QdrantStore(client=QdrantClient(":memory:"))
    ingest_documents(
        [Document(name="a.txt", text="One sentence. Two sentence. Three sentence.")],
        IngestConfig(base="viagem", chunkings=["recursive", "token"], embeddings=["gemini"]),
        store,
        embedder_factory=_embedder_factory,
    )
    session = session_factory()
    experiment = Experiment(name="exp", status="pending", config={})
    session.add(experiment)
    session.commit()
    experiment_id = experiment.id
    session.close()

    config = ExperimentConfig(
        base="viagem",
        chunkings=["recursive", "token"],
        embeddings=["gemini"],
        rags=["naive"],
        retrievers=["similarity"],
        metrics=["answer_relevancy"],
    )
    deps = ExperimentDeps(
        store=store,
        session_factory=session_factory,
        llm_factory=_llm_factory,
        embedder_factory=_embedder_factory,
    )
    run_experiment(experiment_id, config, [QuestionItem(text="q")], deps)

    check = session_factory()
    stored = check.get(Experiment, experiment_id)
    assert {r.chunking for r in stored.runs} == {"recursive", "token"}
    check.close()
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_orchestrator.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'app.experiments.orchestrator'`.

- [ ] **Step 3: Implementar o orquestrador**

`backend/app/experiments/orchestrator.py`:

```python
"""Experiment orchestrator: run the cartesian product and persist results."""
import itertools
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.db.models import Experiment, ExperimentRun, RunResult
from app.core.embedding.base import build_embedder
from app.core.evaluation.base import EvalSample
from app.core.evaluation.runner import evaluate_sample
from app.core.llm.base import build_llm
from app.core.rag.base import build_rag
from app.core.retrieval.base import build_retriever
from app.core.vectorstore.qdrant import QdrantStore, collection_name
from app.experiments.schemas import ExperimentConfig, QuestionItem


@dataclass
class ExperimentDeps:
    """Injectable dependencies for running an experiment (overridable in tests)."""

    store: QdrantStore
    session_factory: Callable[[], Session]
    llm_factory: Callable = build_llm
    embedder_factory: Callable = build_embedder
    retriever_factory: Callable = build_retriever
    rag_factory: Callable = build_rag


def _build_retriever(deps: ExperimentDeps, name: str, collection: str, embedder, llm):
    """Build a retriever, injecting the llm only for retrievers that need it."""
    kwargs = {"store": deps.store, "collection": collection, "embedder": embedder}
    if name == "multi_query":
        kwargs["llm"] = llm
    return deps.retriever_factory(name, **kwargs)


def run_experiment(
    experiment_id: int,
    config: ExperimentConfig,
    questions: list[QuestionItem],
    deps: ExperimentDeps,
) -> None:
    """Run every combination over every question and persist the results."""
    session = deps.session_factory()
    try:
        experiment = session.get(Experiment, experiment_id)
        experiment.status = "running"
        session.commit()

        llm = deps.llm_factory(config.llm)
        eval_embedder = deps.embedder_factory(config.eval_embedding)

        for chunking, embedding, rag_name, retriever_name in itertools.product(
            config.chunkings, config.embeddings, config.rags, config.retrievers
        ):
            run = ExperimentRun(
                experiment_id=experiment_id,
                chunking=chunking,
                embedding=embedding,
                rag_technique=rag_name,
                retriever=retriever_name,
                status="running",
            )
            session.add(run)
            session.commit()

            embedder = deps.embedder_factory(embedding)
            collection = collection_name(config.base, chunking, embedding)
            retriever = _build_retriever(deps, retriever_name, collection, embedder, llm)
            rag = deps.rag_factory(rag_name, retriever=retriever, llm=llm)

            for question in questions:
                start = time.perf_counter()
                answer = rag.answer(question.text)
                latency_ms = int((time.perf_counter() - start) * 1000)
                context_texts = [c.get("text", "") for c in answer.contexts]
                sample = EvalSample(
                    question=question.text,
                    answer=answer.answer,
                    contexts=context_texts,
                    reference_answer=question.reference,
                )
                scores = evaluate_sample(sample, config.metrics, embedder=eval_embedder)
                session.add(
                    RunResult(
                        run_id=run.id,
                        question=question.text,
                        reference_answer=question.reference,
                        generated_answer=answer.answer,
                        retrieved_context=answer.contexts,
                        scores=scores,
                        latency_ms=latency_ms,
                        tokens=len(answer.answer.split()),
                    )
                )
            run.status = "done"
            session.commit()

        experiment.status = "done"
        experiment.finished_at = datetime.utcnow()
        session.commit()
    except Exception as exc:  # noqa: BLE001  background task records failure, never raises
        session.rollback()
        experiment = session.get(Experiment, experiment_id)
        if experiment is not None:
            experiment.status = "failed"
            experiment.config = {**experiment.config, "error": str(exc)}
            session.commit()
    finally:
        session.close()
```

- [ ] **Step 4: Atualizar o `__init__.py`**

Atualize `backend/app/experiments/__init__.py` para exportar `ExperimentDeps` e `run_experiment`:

```python
"""Experiments package."""
from app.experiments.csv_loader import parse_questions_csv
from app.experiments.naming import generate_experiment_name
from app.experiments.orchestrator import ExperimentDeps, run_experiment
from app.experiments.schemas import ExperimentConfig, QuestionItem

__all__ = [
    "parse_questions_csv",
    "generate_experiment_name",
    "ExperimentConfig",
    "QuestionItem",
    "ExperimentDeps",
    "run_experiment",
]
```

- [ ] **Step 5: Rodar e ver passar**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_orchestrator.py -v`
Expected: PASS (2 testes). Suíte inteira verde, zero warnings.

- [ ] **Step 6: Commit**

```bash
git add backend/app/experiments/orchestrator.py backend/app/experiments/__init__.py backend/tests/test_orchestrator.py
git commit -m "feat: experiment orchestrator (cartesian product, evaluate, persist)"
```

---

### Task 3: Endpoints de experimentos (background + polling)

**Files:**
- Create: `backend/app/api/experiments.py`
- Modify: `backend/app/main.py` (incluir o router)
- Create: `backend/tests/test_experiments_api.py`

**Interfaces:**
- Consumes: `app.experiments` (schemas, orchestrator, helpers), `app.core.db.base.SessionLocal`, `app.core.vectorstore.QdrantStore`.
- Produces:
  - `get_experiment_deps() -> ExperimentDeps` — dependência FastAPI com os defaults de produção (`QdrantStore()`, `SessionLocal`, factories reais). Sobrescrita nos testes.
  - `POST /experiments` (multipart): campo `config` (JSON string) + arquivo `questions` (CSV). Valida o JSON em `ExperimentConfig`, gera nome se ausente, parseia o CSV, cria o `Experiment` (`status="pending"`) e agenda `run_experiment` como `BackgroundTask`. Retorna `{id, name, status}`.
  - `GET /experiments` → lista `[{id, name, status}]` (mais recentes primeiro).
  - `GET /experiments/{id}` → `{id, name, status, results: [...]}` onde cada resultado traz a combinação, pergunta, resposta, scores, latency_ms e tokens. 404 se não existir.

- [ ] **Step 1: Escrever o teste que falha**

`backend/tests/test_experiments_api.py`:

```python
"""Tests for the experiments endpoints (background runs synchronously under TestClient)."""
import io
import json

import pytest
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.experiments import get_experiment_deps
from app.core.db.base import Base
from app.core.vectorstore.qdrant import QdrantStore
from app.experiments.orchestrator import ExperimentDeps
from app.ingestion.pipeline import ingest_documents
from app.ingestion.schemas import Document, IngestConfig
from app.main import create_app


class _FakeEmbedder:
    def embed_documents(self, texts):
        return [self.embed_query(t) for t in texts]

    def embed_query(self, text):
        return [float(len(text) % 5), 1.0, 0.0]

    @property
    def dimension(self) -> int:
        return 3


class _FakeLLM:
    def generate(self, prompt: str) -> str:
        return "An answer."


def _embedder_factory(name, **kwargs):
    return _FakeEmbedder()


def _llm_factory(name, **kwargs):
    return _FakeLLM()


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    store = QdrantStore(client=QdrantClient(":memory:"))
    ingest_documents(
        [Document(name="a.txt", text="Para one.\n\nPara two.\n\nPara three.")],
        IngestConfig(base="viagem", chunkings=["recursive"], embeddings=["gemini"]),
        store,
        embedder_factory=_embedder_factory,
    )
    deps = ExperimentDeps(
        store=store,
        session_factory=session_factory,
        llm_factory=_llm_factory,
        embedder_factory=_embedder_factory,
    )
    app = create_app()
    app.dependency_overrides[get_experiment_deps] = lambda: deps
    return TestClient(app)


def _config_payload():
    return json.dumps(
        {
            "base": "viagem",
            "chunkings": ["recursive"],
            "embeddings": ["gemini"],
            "rags": ["naive"],
            "retrievers": ["similarity"],
            "metrics": ["answer_relevancy"],
        }
    )


def test_create_experiment_runs_and_persists(client):
    files = {"questions": ("q.csv", io.BytesIO(b"pergunta,resposta_referencia\nWhere?,\n"), "text/csv")}
    response = client.post("/experiments", data={"config": _config_payload()}, files=files)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"pending", "done"}
    assert body["name"]

    detail = client.get(f"/experiments/{body['id']}").json()
    assert detail["status"] == "done"
    assert len(detail["results"]) == 1
    assert detail["results"][0]["answer"] == "An answer."
    assert "answer_relevancy" in detail["results"][0]["scores"]


def test_list_experiments(client):
    files = {"questions": ("q.csv", io.BytesIO(b"pergunta\nWhere?\n"), "text/csv")}
    client.post("/experiments", data={"config": _config_payload()}, files=files)
    listing = client.get("/experiments").json()
    assert len(listing) >= 1
    assert {"id", "name", "status"} <= set(listing[0])


def test_get_missing_experiment_404(client):
    assert client.get("/experiments/99999").status_code == 404
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_experiments_api.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'app.api.experiments'`.

- [ ] **Step 3: Implementar o router**

`backend/app/api/experiments.py`:

```python
"""Endpoints to create and inspect experiments."""
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile

from app.core.db.base import SessionLocal
from app.core.db.models import Experiment
from app.core.vectorstore.qdrant import QdrantStore
from app.experiments.naming import generate_experiment_name
from app.experiments.orchestrator import ExperimentDeps, run_experiment
from app.experiments.csv_loader import parse_questions_csv
from app.experiments.schemas import ExperimentConfig

router = APIRouter()


def get_experiment_deps() -> ExperimentDeps:
    """FastAPI dependency providing the production experiment dependencies."""
    return ExperimentDeps(store=QdrantStore(), session_factory=SessionLocal)


@router.post("/experiments")
async def create_experiment(
    background_tasks: BackgroundTasks,
    config: str = Form(...),
    questions: UploadFile = File(...),
    deps: ExperimentDeps = Depends(get_experiment_deps),
) -> dict:
    """Create an experiment and run it in the background."""
    parsed = ExperimentConfig.model_validate_json(config)
    if not parsed.name:
        parsed.name = generate_experiment_name()
    csv_text = (await questions.read()).decode("utf-8")
    items = parse_questions_csv(csv_text)

    session = deps.session_factory()
    try:
        experiment = Experiment(name=parsed.name, status="pending", config=parsed.model_dump())
        session.add(experiment)
        session.commit()
        session.refresh(experiment)
        experiment_id = experiment.id
        name = experiment.name
    finally:
        session.close()

    background_tasks.add_task(run_experiment, experiment_id, parsed, items, deps)
    return {"id": experiment_id, "name": name, "status": "pending"}


@router.get("/experiments")
def list_experiments(deps: ExperimentDeps = Depends(get_experiment_deps)) -> list[dict]:
    """List experiments, most recent first."""
    session = deps.session_factory()
    try:
        rows = session.query(Experiment).order_by(Experiment.id.desc()).all()
        return [{"id": e.id, "name": e.name, "status": e.status} for e in rows]
    finally:
        session.close()


@router.get("/experiments/{experiment_id}")
def get_experiment(
    experiment_id: int,
    deps: ExperimentDeps = Depends(get_experiment_deps),
) -> dict:
    """Return an experiment with its per-question results."""
    session = deps.session_factory()
    try:
        experiment = session.get(Experiment, experiment_id)
        if experiment is None:
            raise HTTPException(status_code=404, detail="experiment not found")
        results = []
        for run in experiment.runs:
            for result in run.results:
                results.append(
                    {
                        "chunking": run.chunking,
                        "embedding": run.embedding,
                        "rag": run.rag_technique,
                        "retriever": run.retriever,
                        "question": result.question,
                        "answer": result.generated_answer,
                        "scores": result.scores,
                        "latency_ms": result.latency_ms,
                        "tokens": result.tokens,
                    }
                )
        return {
            "id": experiment.id,
            "name": experiment.name,
            "status": experiment.status,
            "results": results,
        }
    finally:
        session.close()
```

- [ ] **Step 4: Incluir o router no `main.py`**

Em `backend/app/main.py`, importe e inclua o router de experiments (mantendo health/options/ingest):

```python
from app.api import experiments, health, ingest, options
```

e dentro de `create_app`:

```python
    app.include_router(experiments.router)
```

- [ ] **Step 5: Rodar e ver passar**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_experiments_api.py -v`
Expected: PASS (3 testes). Suíte inteira verde, zero warnings.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/experiments.py backend/app/main.py backend/tests/test_experiments_api.py
git commit -m "feat: experiments endpoints (background run + polling)"
```

---

## Self-Review

**Spec coverage (Plano 6 cobre spec §8 — orquestrador de experimentos — e parte de §9):**
- Produto cartesiano `chunking × embedding × rag × retriever` × perguntas, persistido sob o experimento (spec §8) → Task 2. ✅
- Nome aleatório legível quando não informado (spec §4/§8) → Tasks 1, 3. ✅
- CSV `pergunta` + `resposta_referencia` opcional (spec §8) → Task 1; métricas com gabarito puladas quando ausente (via `evaluate_sample`) → reuso do Plano 5. ✅
- Execução em background com polling; `POST /experiments`, `GET /experiments`, `GET /experiments/{id}` (spec §8, §9) → Task 3. ✅
- Operacionais (latência, tokens) registrados sempre (spec §7/§8) → Task 2. ✅
- LLM de geração e embedder de avaliação trocáveis por config (spec §8) → Tasks 1, 2. ✅
- Persistência em Experiment/ExperimentRun/RunResult (spec §4.4) → reuso dos models do Plano 1. ✅

**Placeholder scan:** sem TBD/TODO; todos os passos com código/comando concreto. ✅

**Type consistency:**
- `ExperimentConfig`/`QuestionItem` consistentes entre schemas, csv_loader, orchestrator, API e testes. ✅
- `run_experiment(experiment_id, config, questions, deps)` e `ExperimentDeps` consistentes entre orchestrator, API e testes. ✅
- `_build_retriever` injeta `llm` só no `multi_query` (alinhado ao `build_retriever(name, **kwargs)` do Plano 4). ✅
- `rag.answer(q) -> RAGResult{answer, contexts}` consumido corretamente (contexts → list[str] via `c["text"]`). ✅
- `evaluate_sample(sample, metrics, embedder)` reusado do Plano 5; `EvalSample` montado corretamente. ✅
- Persistência reusa `Experiment/ExperimentRun/RunResult` (campos do Plano 1) sem alteração. ✅
- Toda a DB via `deps.session_factory` (endpoints e background) → testável com SQLite StaticPool. ✅

**Escopo:** orquestração + endpoints. Nada de frontend (Plano 7). Resiliência por-combinação (continuar em erro de uma combinação) fica como melhoria futura — hoje um erro marca o experimento `failed` com a mensagem em `config["error"]`. Sem over-build. ✅
