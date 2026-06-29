# Fatia A — Plano 1: Fundação & Infra — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Subir o esqueleto do monólito modular FastAPI com infraestrutura Docker (API + Qdrant + Postgres), um registry genérico para técnicas plugáveis, e os models do Postgres — tudo testado.

**Architecture:** Monólito modular FastAPI. Um pacote `backend/` com `core/` compartilhado (registry, db, config) e `api/` fino. Infra via docker-compose (api, qdrant, postgres) e Makefile orquestrando os comandos. Este plano entrega a base sobre a qual os planos 2–7 constroem.

**Tech Stack:** Python 3.11, FastAPI, Uvicorn, SQLAlchemy 2.x, psycopg2-binary, qdrant-client, Pydantic v2, pytest, Docker, docker-compose.

## Global Constraints

- PEP-8; docstrings nas funções públicas; comentários só quando agregam.
- **Código em inglês:** identificadores, docstrings e mensagens de erro de runtime em inglês.
  Apenas dados de domínio (conteúdo, perguntas) ficam em PT-BR. Onde os exemplos de código
  deste plano trouxerem docstrings/strings em português, traduza para inglês mantendo a lógica idêntica.
- Sem duplicação: todo acesso a LLM/embedding/vetor passa pelo `core/` (entra nos planos 2+).
- Toda técnica plugável vive atrás de interface + registry.
- Python 3.11; FastAPI; SQLAlchemy 2.x (estilo declarativo novo).
- Configuração sensível via variáveis de ambiente / `.env` (nunca commitar segredos).
- Commits frequentes, um por task.

---

## File Structure

```
backend/
  pyproject.toml          # deps e config de ferramentas
  Dockerfile
  app/
    __init__.py
    main.py               # cria FastAPI app, monta routers, cria tabelas no startup
    core/
      __init__.py
      registry.py         # Registry genérico (register/get/list)
      config/
        __init__.py
        settings.py       # Settings (Pydantic BaseSettings): URLs de Postgres/Qdrant, API keys
      db/
        __init__.py
        base.py           # Declarative Base + engine + SessionLocal + get_session
        models.py         # Experiment, ExperimentRun, RunResult
    api/
      __init__.py
      health.py           # router /health
  tests/
    __init__.py
    conftest.py           # fixtures: client FastAPI, sessão SQLite em memória
    test_health.py
    test_registry.py
    test_models.py
docker-compose.yml        # api + qdrant + postgres
Makefile
.env.example
.gitignore
```

---

### Task 1: Esqueleto do projeto, dependências e API de health

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/app/__init__.py` (vazio)
- Create: `backend/app/main.py`
- Create: `backend/app/api/__init__.py` (vazio)
- Create: `backend/app/api/health.py`
- Create: `backend/tests/__init__.py` (vazio)
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_health.py`
- Create: `.gitignore`

**Interfaces:**
- Consumes: nada.
- Produces: `app.main.create_app() -> FastAPI`; rota `GET /health` → `{"status": "ok"}`; fixture `client` em `conftest.py`.

- [ ] **Step 1: Criar `backend/pyproject.toml` com as dependências**

```toml
[project]
name = "ditto-backend"
version = "0.1.0"
description = "Ditto - nucleo de descoberta (Fatia A)"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.111",
    "uvicorn[standard]>=0.30",
    "sqlalchemy>=2.0",
    "psycopg2-binary>=2.9",
    "qdrant-client>=1.9",
    "pydantic>=2.7",
    "pydantic-settings>=2.3",
    "python-multipart>=0.0.9",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.2",
    "httpx>=0.27",
]

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
```

- [ ] **Step 2: Criar `.gitignore`**

```gitignore
__pycache__/
*.pyc
.venv/
venv/
.env
.pytest_cache/
*.egg-info/
node_modules/
dist/
```

- [ ] **Step 3: Criar os pacotes vazios**

Crie `backend/app/__init__.py`, `backend/app/api/__init__.py`, `backend/tests/__init__.py` vazios.

- [ ] **Step 4: Escrever o teste de health que falha**

`backend/tests/conftest.py`:

```python
"""Fixtures compartilhadas dos testes."""
import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client():
    """Cliente de teste da aplicacao FastAPI."""
    return TestClient(create_app())
```

`backend/tests/test_health.py`:

```python
def test_health_returns_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 5: Rodar o teste e ver falhar**

Run: `cd backend && python -m pytest tests/test_health.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'app.main'`.

- [ ] **Step 6: Implementar o router de health e o app**

`backend/app/api/health.py`:

```python
"""Endpoint de verificacao de saude."""
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    """Retorna o estado da aplicacao."""
    return {"status": "ok"}
```

`backend/app/main.py`:

```python
"""Ponto de entrada da aplicacao FastAPI."""
from fastapi import FastAPI

from app.api import health


def create_app() -> FastAPI:
    """Cria e configura a instancia FastAPI."""
    app = FastAPI(title="Ditto - Fatia A")
    app.include_router(health.router)
    return app


app = create_app()
```

- [ ] **Step 7: Rodar o teste e ver passar**

Run: `cd backend && python -m pytest tests/test_health.py -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/pyproject.toml backend/app backend/tests .gitignore
git commit -m "feat: esqueleto FastAPI com endpoint de health"
```

---

### Task 2: Registry genérico para técnicas plugáveis

**Files:**
- Create: `backend/app/core/__init__.py` (vazio)
- Create: `backend/app/core/registry.py`
- Create: `backend/tests/test_registry.py`

**Interfaces:**
- Consumes: nada.
- Produces: `Registry[T]` com métodos `register(name: str, item: T) -> None`, `get(name: str) -> T` (levanta `KeyError` com mensagem clara se ausente), `names() -> list[str]`. Usado por todos os módulos de técnica (chunking, embedding, rag, retriever, evaluator, llm) nos planos seguintes.

- [ ] **Step 1: Escrever o teste que falha**

`backend/tests/test_registry.py`:

```python
import pytest

from app.core.registry import Registry


def test_register_and_get():
    reg: Registry[str] = Registry("chunker")
    reg.register("recursive", "impl")
    assert reg.get("recursive") == "impl"


def test_names_lists_registered():
    reg: Registry[int] = Registry("embedder")
    reg.register("a", 1)
    reg.register("b", 2)
    assert sorted(reg.names()) == ["a", "b"]


def test_get_unknown_raises_with_helpful_message():
    reg: Registry[int] = Registry("retriever")
    reg.register("known", 1)
    with pytest.raises(KeyError) as exc:
        reg.get("missing")
    assert "retriever" in str(exc.value)
    assert "known" in str(exc.value)


def test_register_duplicate_raises():
    reg: Registry[int] = Registry("llm")
    reg.register("x", 1)
    with pytest.raises(ValueError):
        reg.register("x", 2)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd backend && python -m pytest tests/test_registry.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'app.core.registry'`.

- [ ] **Step 3: Implementar o registry**

Crie `backend/app/core/__init__.py` vazio.

`backend/app/core/registry.py`:

```python
"""Registry generico para tecnicas plugaveis (chunking, embedding, rag, etc.)."""
from typing import Generic, TypeVar

T = TypeVar("T")


class Registry(Generic[T]):
    """Mapa nomeado de implementacoes de uma categoria de tecnica."""

    def __init__(self, kind: str) -> None:
        self._kind = kind
        self._items: dict[str, T] = {}

    def register(self, name: str, item: T) -> None:
        """Registra uma implementacao sob um nome unico."""
        if name in self._items:
            raise ValueError(f"{self._kind} '{name}' ja registrado")
        self._items[name] = item

    def get(self, name: str) -> T:
        """Retorna a implementacao registrada ou levanta KeyError."""
        if name not in self._items:
            raise KeyError(
                f"{self._kind} '{name}' nao encontrado. "
                f"Disponiveis: {sorted(self._items)}"
            )
        return self._items[name]

    def names(self) -> list[str]:
        """Lista os nomes registrados."""
        return list(self._items)
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd backend && python -m pytest tests/test_registry.py -v`
Expected: PASS (4 testes).

- [ ] **Step 5: Commit**

```bash
git add backend/app/core backend/tests/test_registry.py
git commit -m "feat: registry generico para tecnicas plugaveis"
```

---

### Task 3: Settings de configuração (Pydantic)

**Files:**
- Create: `backend/app/core/config/__init__.py` (vazio)
- Create: `backend/app/core/config/settings.py`
- Create: `backend/tests/test_settings.py`
- Create: `.env.example`

**Interfaces:**
- Consumes: nada.
- Produces: `Settings` (pydantic-settings) com `database_url: str`, `qdrant_url: str`, `gemini_api_key: str | None`; e `get_settings() -> Settings` (cacheado). Consumido por `db/base.py` e pelos providers nos planos 2+.

- [ ] **Step 1: Escrever o teste que falha**

`backend/tests/test_settings.py`:

```python
import importlib

from app.core.config import settings as settings_module


def test_settings_read_from_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db:5432/ditto")
    monkeypatch.setenv("QDRANT_URL", "http://qdrant:6333")
    monkeypatch.setenv("GEMINI_API_KEY", "secret")
    settings_module.get_settings.cache_clear()
    cfg = settings_module.get_settings()
    assert cfg.database_url == "postgresql://u:p@db:5432/ditto"
    assert cfg.qdrant_url == "http://qdrant:6333"
    assert cfg.gemini_api_key == "secret"


def test_gemini_key_optional(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    settings_module.get_settings.cache_clear()
    cfg = settings_module.get_settings()
    assert cfg.gemini_api_key is None
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd backend && python -m pytest tests/test_settings.py -v`
Expected: FAIL com `ModuleNotFoundError`.

- [ ] **Step 3: Implementar settings**

Crie `backend/app/core/config/__init__.py` vazio.

`backend/app/core/config/settings.py`:

```python
"""Configuracoes da aplicacao lidas do ambiente."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Variaveis de ambiente da aplicacao."""

    database_url: str = "postgresql://ditto:ditto@localhost:5432/ditto"
    qdrant_url: str = "http://localhost:6333"
    gemini_api_key: str | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    """Retorna as configuracoes (cacheadas)."""
    return Settings()
```

`.env.example`:

```dotenv
DATABASE_URL=postgresql://ditto:ditto@postgres:5432/ditto
QDRANT_URL=http://qdrant:6333
GEMINI_API_KEY=
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd backend && python -m pytest tests/test_settings.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/config backend/tests/test_settings.py .env.example
git commit -m "feat: settings via pydantic-settings"
```

---

### Task 4: Camada de banco (Base, engine, sessão) e models do Postgres

**Files:**
- Create: `backend/app/core/db/__init__.py` (vazio)
- Create: `backend/app/core/db/base.py`
- Create: `backend/app/core/db/models.py`
- Create: `backend/tests/test_models.py`
- Modify: `backend/tests/conftest.py` (adicionar fixture `db_session` com SQLite em memória)

**Interfaces:**
- Consumes: `app.core.config.settings.get_settings`.
- Produces:
  - `app.core.db.base.Base` (DeclarativeBase), `engine`, `SessionLocal`, `get_session()` (gerador para dependência FastAPI), `create_all()`.
  - Models: `Experiment(id, name, status, config(JSON), created_at, finished_at)`, `ExperimentRun(id, experiment_id, chunking, embedding, rag_technique, retriever, status)`, `RunResult(id, run_id, question, reference_answer, generated_answer, retrieved_context(JSON), scores(JSON), latency_ms, tokens)`.
  - `ExperimentStatus` valores: `"pending" | "running" | "done" | "failed"`.

- [ ] **Step 1: Escrever o teste que falha**

`backend/tests/test_models.py`:

```python
from app.core.db.base import Base
from app.core.db.models import Experiment, ExperimentRun, RunResult


def test_experiment_run_result_relationship(db_session):
    exp = Experiment(name="brave-otter-42", status="pending", config={"k": 5})
    run = ExperimentRun(
        chunking="recursive",
        embedding="e5",
        rag_technique="naive",
        retriever="similarity",
        status="pending",
    )
    exp.runs.append(run)
    result = RunResult(
        question="Qual a capital?",
        reference_answer=None,
        generated_answer="Brasilia",
        retrieved_context=[{"text": "..."}],
        scores={"faithfulness": 0.9},
        latency_ms=120,
        tokens=42,
    )
    run.results.append(result)

    db_session.add(exp)
    db_session.commit()

    stored = db_session.query(Experiment).filter_by(name="brave-otter-42").one()
    assert stored.runs[0].results[0].generated_answer == "Brasilia"
    assert stored.runs[0].results[0].scores["faithfulness"] == 0.9
```

- [ ] **Step 2: Adicionar a fixture `db_session` ao `conftest.py`**

Acrescente ao `backend/tests/conftest.py`:

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.db.base import Base


@pytest.fixture
def db_session():
    """Sessao SQLAlchemy isolada em SQLite na memoria."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
```

- [ ] **Step 3: Rodar e ver falhar**

Run: `cd backend && python -m pytest tests/test_models.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'app.core.db.base'`.

- [ ] **Step 4: Implementar `base.py`**

Crie `backend/app/core/db/__init__.py` vazio.

`backend/app/core/db/base.py`:

```python
"""Configuracao do SQLAlchemy: engine, sessao e base declarativa."""
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config.settings import get_settings


class Base(DeclarativeBase):
    """Base declarativa de todos os models."""


engine = create_engine(get_settings().database_url, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, future=True)


def get_session() -> Iterator[Session]:
    """Dependencia FastAPI que fornece uma sessao por requisicao."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def create_all() -> None:
    """Cria todas as tabelas registradas na Base."""
    Base.metadata.create_all(engine)
```

- [ ] **Step 5: Implementar `models.py`**

`backend/app/core/db/models.py`:

```python
"""Models relacionais de experimentos, execucoes e resultados."""
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db.base import Base


class Experiment(Base):
    """Um experimento de comparacao de composicoes."""

    __tablename__ = "experiment"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    runs: Mapped[list["ExperimentRun"]] = relationship(
        back_populates="experiment", cascade="all, delete-orphan"
    )


class ExperimentRun(Base):
    """Uma combinacao chunking x embedding x rag x retriever de um experimento."""

    __tablename__ = "experiment_run"

    id: Mapped[int] = mapped_column(primary_key=True)
    experiment_id: Mapped[int] = mapped_column(ForeignKey("experiment.id"))
    chunking: Mapped[str] = mapped_column(String(60))
    embedding: Mapped[str] = mapped_column(String(60))
    rag_technique: Mapped[str] = mapped_column(String(60))
    retriever: Mapped[str] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(20), default="pending")

    experiment: Mapped["Experiment"] = relationship(back_populates="runs")
    results: Mapped[list["RunResult"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class RunResult(Base):
    """Resultado de uma pergunta dentro de uma combinacao."""

    __tablename__ = "run_result"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("experiment_run.id"))
    question: Mapped[str] = mapped_column(String)
    reference_answer: Mapped[str | None] = mapped_column(String, nullable=True)
    generated_answer: Mapped[str] = mapped_column(String)
    retrieved_context: Mapped[list] = mapped_column(JSON, default=list)
    scores: Mapped[dict] = mapped_column(JSON, default=dict)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    tokens: Mapped[int] = mapped_column(Integer, default=0)

    run: Mapped["ExperimentRun"] = relationship(back_populates="results")
```

- [ ] **Step 6: Rodar e ver passar**

Run: `cd backend && python -m pytest tests/test_models.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/core/db backend/tests/test_models.py backend/tests/conftest.py
git commit -m "feat: camada de banco e models de experimento"
```

---

### Task 5: Criar tabelas no startup e expor opções de registries

**Files:**
- Modify: `backend/app/main.py` (chamar `create_all()` no startup)
- Create: `backend/tests/test_startup.py`

**Interfaces:**
- Consumes: `app.core.db.base.create_all`.
- Produces: app que cria as tabelas ao iniciar (idempotente).

- [ ] **Step 1: Escrever o teste que falha**

`backend/tests/test_startup.py`:

```python
from unittest.mock import patch


def test_create_all_called_on_startup():
    with patch("app.main.create_all") as mock_create:
        from fastapi.testclient import TestClient

        from app.main import create_app

        with TestClient(create_app()):
            pass
        mock_create.assert_called_once()
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd backend && python -m pytest tests/test_startup.py -v`
Expected: FAIL (`create_all` não importado/chamado em `main`).

- [ ] **Step 3: Ligar `create_all` ao startup**

Substitua `backend/app/main.py` por:

```python
"""Ponto de entrada da aplicacao FastAPI."""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import health
from app.core.db.base import create_all


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Cria as tabelas ao iniciar a aplicacao."""
    create_all()
    yield


def create_app() -> FastAPI:
    """Cria e configura a instancia FastAPI."""
    app = FastAPI(title="Ditto - Fatia A", lifespan=lifespan)
    app.include_router(health.router)
    return app


app = create_app()
```

- [ ] **Step 4: Rodar a suíte inteira e ver passar**

Run: `cd backend && python -m pytest -v`
Expected: PASS (todos os testes).

- [ ] **Step 5: Commit**

```bash
git add backend/app/main.py backend/tests/test_startup.py
git commit -m "feat: criar tabelas no startup da aplicacao"
```

---

### Task 6: Dockerfile, docker-compose e Makefile

**Files:**
- Create: `backend/Dockerfile`
- Create: `docker-compose.yml`
- Create: `Makefile`

**Interfaces:**
- Consumes: a aplicação dos tasks anteriores.
- Produces: `make up` sobe api+qdrant+postgres; `make test` roda a suíte; `make down`/`make logs` operam o stack.

- [ ] **Step 1: Criar o Dockerfile do backend**

`backend/Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir .

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Criar o docker-compose**

`docker-compose.yml`:

```yaml
services:
  api:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql://ditto:ditto@postgres:5432/ditto
      QDRANT_URL: http://qdrant:6333
      GEMINI_API_KEY: ${GEMINI_API_KEY:-}
    depends_on:
      postgres:
        condition: service_healthy
      qdrant:
        condition: service_started

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: ditto
      POSTGRES_PASSWORD: ditto
      POSTGRES_DB: ditto
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ditto"]
      interval: 5s
      timeout: 3s
      retries: 5

  qdrant:
    image: qdrant/qdrant:latest
    ports:
      - "6333:6333"
    volumes:
      - qdrantdata:/qdrant/storage

volumes:
  pgdata:
  qdrantdata:
```

- [ ] **Step 3: Criar o Makefile**

`Makefile`:

```makefile
.PHONY: up down logs test build install

build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

install:
	cd backend && pip install -e ".[dev]"

test:
	cd backend && python -m pytest -v
```

- [ ] **Step 4: Verificar o stack subindo**

Run: `make build && make up`
Expected: três containers de pé. `curl http://localhost:8000/health` retorna `{"status":"ok"}`.

- [ ] **Step 5: Verificar as tabelas criadas no Postgres**

Run: `docker compose exec postgres psql -U ditto -d ditto -c "\dt"`
Expected: lista contendo `experiment`, `experiment_run`, `run_result`.

- [ ] **Step 6: Derrubar o stack**

Run: `make down`
Expected: containers removidos.

- [ ] **Step 7: Commit**

```bash
git add backend/Dockerfile docker-compose.yml Makefile
git commit -m "feat: docker-compose (api+qdrant+postgres) e Makefile"
```

---

## Self-Review

**Spec coverage (Plano 1 cobre a fundação do spec §2, §3, §4.4, §11):**
- Monólito modular FastAPI → Tasks 1, 5. ✅
- `core/` compartilhado (registry, config, db) → Tasks 2, 3, 4. ✅
- Models Postgres (experiment/run/result) → Task 4, conforme spec §4.4. ✅
- docker-compose (api+qdrant+postgres) + Makefile → Task 6, conforme spec §11. ✅
- Interface+registry para extensibilidade → Task 2 (a base; as interfaces concretas de cada técnica entram nos planos 2–5). ✅
- Frontend (spec §10) → fora deste plano, é o Plano 7. ✅ (intencional)
- LLM/Embedder/Vectorstore providers (spec §4.1–4.3) → fora deste plano, é o Plano 2. ✅ (intencional)

**Placeholder scan:** sem TBD/TODO; todo passo tem código ou comando concreto. ✅

**Type consistency:** nomes de status (`pending/running/done/failed`) consistentes entre `models.py` e o teste; `Registry.get/register/names` consistentes entre teste e implementação; `create_all` referenciado igual em `base.py`, `main.py` e `test_startup.py`. ✅
