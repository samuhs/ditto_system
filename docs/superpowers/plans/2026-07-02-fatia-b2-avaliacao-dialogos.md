# Fatia B2 — Avaliação de diálogos — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Uma tela para listar diálogos salvos (paginada, com filtros e ordenação), abrir um diálogo para ler a conversa, e atribuir/reeditar uma nota humana de 0 a 10.

**Architecture:** Backend adiciona duas colunas (`rating`, `rated_at`) à tabela `dialogue` e três endpoints no router de chat já existente (`GET /dialogues` paginado, `GET /dialogues/{id}`, `PUT /dialogues/{id}/rating`). Frontend adiciona funções de cliente + tipos e duas telas React (lista → detalhe), espelhando o padrão da tela de resultados de experimentos.

**Tech Stack:** FastAPI + SQLAlchemy (backend, Python 3.13, venv `backend/.venv`); React + Vite + TypeScript + Mantine (frontend, Node 22, vitest).

## Global Constraints

- Código (identificadores, docstrings, mensagens de erro) em **inglês**; textos de UI em **PT-BR**.
- Testes não tocam rede/Postgres: SQLite (StaticPool ou `db_session`), Qdrant `:memory:`, deps injetadas.
- `rating` é inteiro **0–10**, nullable (`NULL` = não avaliado); `rated_at` é datetime nullable.
- Na ordenação por nota (`rating_asc`/`rating_desc`), diálogos **não avaliados (`rating IS NULL`) vão sempre por último**, desempate por `created_at` desc.
- `GET /dialogues`: `page` default 1 (≥1), `page_size` default 20 (1–100). `rated ∈ {all, rated, unrated}`, `sort ∈ {recent, oldest, rating_asc, rating_desc}`. Params inválidos → 422.
- Backend dev: rodar pytest com `cd backend && ./.venv/bin/python -m pytest`. Frontend: `cd frontend && npm test`.
- **Post-merge deployment (manual, NÃO é uma task de código):** o schema é criado por `Base.metadata.create_all()`, que não altera tabelas existentes. Após o merge, rodar no Postgres deployado:
  ```sql
  ALTER TABLE dialogue ADD COLUMN IF NOT EXISTS rating INTEGER;
  ALTER TABLE dialogue ADD COLUMN IF NOT EXISTS rated_at TIMESTAMP;
  ```

---

### Task 1: Colunas `rating` e `rated_at` no modelo Dialogue

**Files:**
- Modify: `backend/app/core/db/models.py` (classe `Dialogue`, linhas ~81-92)
- Test: `backend/tests/test_dialogue_models.py` (criar)

**Interfaces:**
- Consumes: `Dialogue` model, `db_session` fixture (de `backend/tests/conftest.py`), `Integer`/`DateTime` (já importados em `models.py`).
- Produces: `Dialogue.rating: int | None`, `Dialogue.rated_at: datetime | None`.

- [ ] **Step 1: Write the failing test**

Criar `backend/tests/test_dialogue_models.py`:

```python
"""Tests for the Dialogue rating columns."""
from datetime import datetime

from app.core.db.models import Dialogue, DialogueMessage


def test_dialogue_rating_defaults_to_none(db_session):
    d = Dialogue(config_snapshot={"name": "c1"})
    d.messages = [DialogueMessage(role="user", content="Oi", position=0)]
    db_session.add(d)
    db_session.commit()
    db_session.refresh(d)
    assert d.rating is None
    assert d.rated_at is None


def test_dialogue_stores_rating_and_rated_at(db_session):
    when = datetime(2026, 7, 2, 10, 0)
    d = Dialogue(config_snapshot={}, rating=7, rated_at=when)
    db_session.add(d)
    db_session.commit()
    db_session.refresh(d)
    assert d.rating == 7
    assert d.rated_at == when
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_dialogue_models.py -v`
Expected: FAIL — `TypeError: 'rating' is an invalid keyword argument for Dialogue` (coluna ainda não existe).

- [ ] **Step 3: Add the columns**

Em `backend/app/core/db/models.py`, dentro da classe `Dialogue`, logo após `created_at` (linha ~88), adicionar:

```python
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
```

(`Integer`, `DateTime` e `datetime` já estão importados no arquivo.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_dialogue_models.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/db/models.py backend/tests/test_dialogue_models.py
git commit -m "feat(b2): add rating and rated_at columns to Dialogue"
```

---

### Task 2: Endpoint `GET /dialogues` (lista paginada, filtros, ordenação)

**Files:**
- Modify: `backend/app/api/chat.py` (imports no topo; novo endpoint + helper após o `save_dialogue` existente, ~linha 208)
- Test: `backend/tests/test_dialogues_api.py` (criar)

**Interfaces:**
- Consumes: `Dialogue`, `DialogueMessage` (de `app.core.db.models`), `ChatDeps`/`get_chat_deps`, `QdrantStore`.
- Produces: `GET /dialogues` → `{"items": [...], "total": int, "page": int, "page_size": int}`. Cada item: `{id, created_at, rating, name, persona, message_count, preview}`. Helper `_dialogue_list_item(d: Dialogue) -> dict`.

- [ ] **Step 1: Write the failing test**

Criar `backend/tests/test_dialogues_api.py`:

```python
"""Tests for the dialogue listing/detail/rating endpoints (hermetic)."""
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.chat import get_chat_deps
from app.core.chat.deps import ChatDeps
from app.core.db.base import Base
from app.core.db.models import Dialogue, DialogueMessage
from app.core.vectorstore.qdrant import QdrantStore
from app.main import create_app


@pytest.fixture
def env():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    deps = ChatDeps(
        store=QdrantStore(client=QdrantClient(":memory:")),
        session_factory=session_factory,
    )
    app = create_app()
    app.dependency_overrides[get_chat_deps] = lambda: deps
    return TestClient(app), session_factory


def _seed(
    session_factory,
    *,
    snapshot=None,
    messages=(("user", "Oi"),),
    rating=None,
    created_at=None,
):
    session = session_factory()
    try:
        d = Dialogue(
            config_snapshot=snapshot or {"name": "c1", "persona": "travel_guide"},
            rating=rating,
        )
        if created_at is not None:
            d.created_at = created_at
        d.messages = [
            DialogueMessage(role=r, content=c, position=i)
            for i, (r, c) in enumerate(messages)
        ]
        session.add(d)
        session.commit()
        session.refresh(d)
        return d.id
    finally:
        session.close()


def test_list_empty(env):
    client, _ = env
    body = client.get("/dialogues").json()
    assert body == {"items": [], "total": 0, "page": 1, "page_size": 20}


def test_list_pagination(env):
    client, sf = env
    for _ in range(3):
        _seed(sf)
    page1 = client.get("/dialogues?page=1&page_size=2").json()
    assert page1["total"] == 3
    assert len(page1["items"]) == 2
    page2 = client.get("/dialogues?page=2&page_size=2").json()
    assert len(page2["items"]) == 1


def test_list_rated_filter(env):
    client, sf = env
    _seed(sf, rating=8)
    _seed(sf, rating=None)
    rated = client.get("/dialogues?rated=rated").json()
    assert len(rated["items"]) == 1 and rated["items"][0]["rating"] == 8
    unrated = client.get("/dialogues?rated=unrated").json()
    assert len(unrated["items"]) == 1 and unrated["items"][0]["rating"] is None


def test_list_date_filter(env):
    client, sf = env
    _seed(sf, created_at=datetime(2026, 3, 10, 9, 0))
    _seed(sf, created_at=datetime(2026, 3, 11, 9, 0))
    body = client.get("/dialogues?date=2026-03-10").json()
    assert body["total"] == 1


def test_list_sort_rating_asc_puts_unrated_last(env):
    client, sf = env
    _seed(sf, rating=5)
    _seed(sf, rating=2)
    _seed(sf, rating=None)
    ratings = [it["rating"] for it in client.get("/dialogues?sort=rating_asc").json()["items"]]
    assert ratings == [2, 5, None]


def test_list_item_fields(env):
    client, sf = env
    long_q = "P" * 100
    _seed(
        sf,
        snapshot={"name": "guia", "persona": "travel_guide"},
        messages=(("user", long_q), ("assistant", "resp")),
    )
    item = client.get("/dialogues").json()["items"][0]
    assert item["name"] == "guia"
    assert item["persona"] == "travel_guide"
    assert item["message_count"] == 2
    assert item["preview"] == "P" * 80  # truncated to 80 chars


def test_list_invalid_params(env):
    client, _ = env
    assert client.get("/dialogues?rated=bogus").status_code == 422
    assert client.get("/dialogues?sort=bogus").status_code == 422
    assert client.get("/dialogues?date=nope").status_code == 422
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_dialogues_api.py -v`
Expected: FAIL — os testes de listagem retornam 404/405 (endpoint inexistente) ou o import falha.

- [ ] **Step 3: Add imports**

No topo de `backend/app/api/chat.py`, ajustar os imports. Trocar a linha `from datetime import ...` (não existe hoje) — adicionar após a linha `from fastapi import APIRouter, Depends, HTTPException`:

```python
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
```

(Substituir a linha de import do `fastapi` existente para incluir `Query`; adicionar a linha do `datetime`.)

- [ ] **Step 4: Add the endpoint + helper**

No fim de `backend/app/api/chat.py` (após `save_dialogue`), adicionar:

```python
_RATED_VALUES = {"all", "rated", "unrated"}
_SORT_VALUES = {"recent", "oldest", "rating_asc", "rating_desc"}


def _dialogue_list_item(d: Dialogue) -> dict:
    """Build a list-row summary for a dialogue."""
    snapshot = d.config_snapshot or {}
    user_msgs = sorted(
        (m for m in d.messages if m.role == "user"), key=lambda m: m.position
    )
    preview = user_msgs[0].content[:80] if user_msgs else None
    return {
        "id": d.id,
        "created_at": d.created_at.isoformat() if d.created_at else None,
        "rating": d.rating,
        "name": snapshot.get("name"),
        "persona": snapshot.get("persona"),
        "message_count": len(d.messages),
        "preview": preview,
    }


@router.get("/dialogues")
def list_dialogues(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    date: str | None = Query(None),
    rated: str = Query("all"),
    sort: str = Query("recent"),
    deps: ChatDeps = Depends(get_chat_deps),
) -> dict:
    """List saved dialogues, paginated, with optional date/rated filters and sorting."""
    if rated not in _RATED_VALUES:
        raise HTTPException(status_code=422, detail=f"invalid rated filter: {rated}")
    if sort not in _SORT_VALUES:
        raise HTTPException(status_code=422, detail=f"invalid sort: {sort}")
    day_start = None
    if date is not None:
        try:
            day_start = datetime.strptime(date, "%Y-%m-%d")
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"invalid date: {date}") from exc

    session = deps.session_factory()
    try:
        query = session.query(Dialogue)
        if day_start is not None:
            query = query.filter(
                Dialogue.created_at >= day_start,
                Dialogue.created_at < day_start + timedelta(days=1),
            )
        if rated == "rated":
            query = query.filter(Dialogue.rating.is_not(None))
        elif rated == "unrated":
            query = query.filter(Dialogue.rating.is_(None))

        total = query.count()

        if sort == "recent":
            query = query.order_by(Dialogue.created_at.desc())
        elif sort == "oldest":
            query = query.order_by(Dialogue.created_at.asc())
        elif sort == "rating_asc":
            query = query.order_by(
                Dialogue.rating.is_(None), Dialogue.rating.asc(), Dialogue.created_at.desc()
            )
        else:  # rating_desc
            query = query.order_by(
                Dialogue.rating.is_(None), Dialogue.rating.desc(), Dialogue.created_at.desc()
            )

        rows = query.offset((page - 1) * page_size).limit(page_size).all()
        return {
            "items": [_dialogue_list_item(d) for d in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    finally:
        session.close()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_dialogues_api.py -v`
Expected: PASS (7 passed).

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/chat.py backend/tests/test_dialogues_api.py
git commit -m "feat(b2): GET /dialogues with pagination, filters and sorting"
```

---

### Task 3: Endpoints `GET /dialogues/{id}` e `PUT /dialogues/{id}/rating`

**Files:**
- Modify: `backend/app/api/chat.py` (import de `Field`; `RatingBody` model; dois endpoints após `list_dialogues`)
- Test: `backend/tests/test_dialogues_api.py` (adicionar casos)

**Interfaces:**
- Consumes: `Dialogue` model, `get_chat_deps`, `env`/`_seed` (do arquivo de teste da Task 2), `datetime` (já importado na Task 2).
- Produces: `GET /dialogues/{dialogue_id}` → `{id, created_at, rating, config_snapshot, messages: [{role, content}]}` (404 se inexistente). `PUT /dialogues/{dialogue_id}/rating` body `{rating: int}` (Field ge=0 le=10) → `{id, rating}` (404 inexistente, 422 fora de 0–10). `RatingBody(BaseModel)`.

- [ ] **Step 1: Write the failing test**

Adicionar ao fim de `backend/tests/test_dialogues_api.py`:

```python
def test_get_detail_returns_messages_in_order(env):
    client, sf = env
    did = _seed(
        sf,
        snapshot={"name": "c1", "persona": "travel_guide", "base": "viagem"},
        messages=(("user", "Pergunta"), ("assistant", "Resposta")),
    )
    body = client.get(f"/dialogues/{did}").json()
    assert body["id"] == did
    assert body["config_snapshot"]["persona"] == "travel_guide"
    assert body["messages"] == [
        {"role": "user", "content": "Pergunta"},
        {"role": "assistant", "content": "Resposta"},
    ]


def test_get_detail_404(env):
    client, _ = env
    assert client.get("/dialogues/9999").status_code == 404


def test_put_rating_persists(env):
    client, sf = env
    did = _seed(sf)
    resp = client.put(f"/dialogues/{did}/rating", json={"rating": 8})
    assert resp.status_code == 200
    assert resp.json() == {"id": did, "rating": 8}
    assert client.get(f"/dialogues/{did}").json()["rating"] == 8
    # rated_at was stamped
    session = sf()
    try:
        assert session.get(Dialogue, did).rated_at is not None
    finally:
        session.close()


def test_put_rating_is_editable(env):
    client, sf = env
    did = _seed(sf)
    client.put(f"/dialogues/{did}/rating", json={"rating": 8})
    client.put(f"/dialogues/{did}/rating", json={"rating": 3})
    assert client.get(f"/dialogues/{did}").json()["rating"] == 3


def test_put_rating_out_of_range(env):
    client, sf = env
    did = _seed(sf)
    assert client.put(f"/dialogues/{did}/rating", json={"rating": 11}).status_code == 422
    assert client.put(f"/dialogues/{did}/rating", json={"rating": -1}).status_code == 422


def test_put_rating_404(env):
    client, _ = env
    assert client.put("/dialogues/9999/rating", json={"rating": 5}).status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_dialogues_api.py -k "detail or rating" -v`
Expected: FAIL — endpoints não existem (404/405).

- [ ] **Step 3: Add the `Field` import**

Em `backend/app/api/chat.py`, alterar `from pydantic import BaseModel` para:

```python
from pydantic import BaseModel, Field
```

- [ ] **Step 4: Add the two endpoints**

Ao fim de `backend/app/api/chat.py`, adicionar:

```python
@router.get("/dialogues/{dialogue_id}")
def get_dialogue(dialogue_id: int, deps: ChatDeps = Depends(get_chat_deps)) -> dict:
    """Return a saved dialogue with its messages in order and config snapshot."""
    session = deps.session_factory()
    try:
        d = session.get(Dialogue, dialogue_id)
        if d is None:
            raise HTTPException(status_code=404, detail="dialogue not found")
        messages = [
            {"role": m.role, "content": m.content}
            for m in sorted(d.messages, key=lambda m: m.position)
        ]
        return {
            "id": d.id,
            "created_at": d.created_at.isoformat() if d.created_at else None,
            "rating": d.rating,
            "config_snapshot": d.config_snapshot or {},
            "messages": messages,
        }
    finally:
        session.close()


class RatingBody(BaseModel):
    rating: int = Field(ge=0, le=10)


@router.put("/dialogues/{dialogue_id}/rating")
def set_dialogue_rating(
    dialogue_id: int, body: RatingBody, deps: ChatDeps = Depends(get_chat_deps)
) -> dict:
    """Set or update the human rating (0-10) for a dialogue."""
    session = deps.session_factory()
    try:
        d = session.get(Dialogue, dialogue_id)
        if d is None:
            raise HTTPException(status_code=404, detail="dialogue not found")
        d.rating = body.rating
        d.rated_at = datetime.utcnow()
        session.commit()
        return {"id": dialogue_id, "rating": body.rating}
    finally:
        session.close()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_dialogues_api.py -v`
Expected: PASS (todos: 7 da Task 2 + 6 novos = 13 passed).

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/chat.py backend/tests/test_dialogues_api.py
git commit -m "feat(b2): GET /dialogues/{id} and PUT /dialogues/{id}/rating"
```

---

### Task 4: Cliente de API + tipos (frontend)

**Files:**
- Modify: `frontend/src/api/types.ts` (novos tipos ao fim)
- Modify: `frontend/src/api/client.ts` (novos imports de tipo + três funções)
- Test: `frontend/src/api/client.test.ts` (adicionar casos + import)

**Interfaces:**
- Consumes: `asJson`, `BASE`, `ChatMessage` (já em `client.ts`/`types.ts`).
- Produces: tipos `DialogueListItem`, `DialogueList`, `DialogueDetail`, `DialogueListParams`; funções `listDialogues(params?: DialogueListParams): Promise<DialogueList>`, `getDialogue(id: number): Promise<DialogueDetail>`, `saveDialogueRating(id: number, rating: number): Promise<{ id: number; rating: number }>`.

- [ ] **Step 1: Write the failing test**

Adicionar ao final do `describe("api client", ...)` em `frontend/src/api/client.test.ts` (e incluir os nomes no bloco de import do topo):

No import do topo (dentro das chaves de `from "./client"`), adicionar `getDialogue,`, `listDialogues,`, `saveDialogueRating,`.

Casos novos (antes do `});` que fecha o describe):

```typescript
  it("listDialogues builds the query string", async () => {
    const body = { items: [], total: 0, page: 1, page_size: 20 };
    vi.stubGlobal("fetch", mockFetchOnce(body));
    await expect(
      listDialogues({ page: 2, page_size: 20, rated: "unrated", sort: "rating_asc", date: "2026-03-10" }),
    ).resolves.toEqual(body);
    expect(fetch).toHaveBeenCalledWith(
      "/api/dialogues?page=2&page_size=20&date=2026-03-10&rated=unrated&sort=rating_asc",
    );
  });

  it("listDialogues with no params hits the bare endpoint", async () => {
    vi.stubGlobal("fetch", mockFetchOnce({ items: [], total: 0, page: 1, page_size: 20 }));
    await listDialogues();
    expect(fetch).toHaveBeenCalledWith("/api/dialogues");
  });

  it("getDialogue fetches the detail", async () => {
    const body = { id: 5, created_at: "x", rating: null, config_snapshot: {}, messages: [] };
    vi.stubGlobal("fetch", mockFetchOnce(body));
    await expect(getDialogue(5)).resolves.toEqual(body);
    expect(fetch).toHaveBeenCalledWith("/api/dialogues/5");
  });

  it("saveDialogueRating PUTs the rating", async () => {
    const fetchMock = mockFetchOnce({ id: 5, rating: 8 });
    vi.stubGlobal("fetch", fetchMock);
    await saveDialogueRating(5, 8);
    expect(fetchMock).toHaveBeenCalledWith("/api/dialogues/5/rating", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rating: 8 }),
    });
  });
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- src/api/client.test.ts`
Expected: FAIL — `listDialogues`/`getDialogue`/`saveDialogueRating` não existem (erro de import/compilação).

- [ ] **Step 3: Add the types**

Ao fim de `frontend/src/api/types.ts`:

```typescript
export interface DialogueListItem {
  id: number;
  created_at: string | null;
  rating: number | null;
  name: string | null;
  persona: string | null;
  message_count: number;
  preview: string | null;
}

export interface DialogueList {
  items: DialogueListItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface DialogueDetail {
  id: number;
  created_at: string | null;
  rating: number | null;
  config_snapshot: Record<string, string>;
  messages: ChatMessage[];
}

export interface DialogueListParams {
  page?: number;
  page_size?: number;
  date?: string | null;
  rated?: "all" | "rated" | "unrated";
  sort?: "recent" | "oldest" | "rating_asc" | "rating_desc";
}
```

- [ ] **Step 4: Add the client functions**

Em `frontend/src/api/client.ts`, adicionar os tipos ao bloco `import type { ... } from "./types";` (incluir `DialogueDetail,`, `DialogueList,`, `DialogueListParams,`). Depois, ao fim do arquivo:

```typescript
export async function listDialogues(params: DialogueListParams = {}): Promise<DialogueList> {
  const q = new URLSearchParams();
  if (params.page) q.set("page", String(params.page));
  if (params.page_size) q.set("page_size", String(params.page_size));
  if (params.date) q.set("date", params.date);
  if (params.rated) q.set("rated", params.rated);
  if (params.sort) q.set("sort", params.sort);
  const qs = q.toString();
  return asJson<DialogueList>(await fetch(`${BASE}/dialogues${qs ? `?${qs}` : ""}`));
}

export async function getDialogue(id: number): Promise<DialogueDetail> {
  return asJson<DialogueDetail>(await fetch(`${BASE}/dialogues/${id}`));
}

export async function saveDialogueRating(
  id: number,
  rating: number,
): Promise<{ id: number; rating: number }> {
  return asJson(await fetch(`${BASE}/dialogues/${id}/rating`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ rating }),
  }));
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd frontend && npm test -- src/api/client.test.ts`
Expected: PASS (todos os casos, incluindo os 4 novos).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/types.ts frontend/src/api/client.ts frontend/src/api/client.test.ts
git commit -m "feat(b2): dialogue list/detail/rating api client + types"
```

---

### Task 5: Tela de lista `/dialogues` + rota + item no menu

**Files:**
- Create: `frontend/src/pages/DialoguesPage.tsx`
- Create: `frontend/src/pages/DialoguesPage.test.tsx`
- Modify: `frontend/src/App.tsx` (import + rota `/dialogues`)
- Modify: `frontend/src/components/Sidebar.tsx` (item no `NAV`)

**Interfaces:**
- Consumes: `listDialogues`, tipos `DialogueList`/`DialogueListParams` (Task 4); `PageHeader`; classes CSS existentes (`ditto-filter-bar`, `ditto-table-wrap`, `ditto-table-foot`, `ditto-row`, `ditto-chip`, `ditto-empty`); `ChartIcon` (de `./icons`).
- Produces: componente `DialoguesPage`; rota `/dialogues`; navegação para `/dialogues/:id` ao clicar numa linha.

- [ ] **Step 1: Write the failing test**

Criar `frontend/src/pages/DialoguesPage.test.tsx`:

```tsx
import { MantineProvider } from "@mantine/core";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as client from "../api/client";
import { DialoguesPage } from "./DialoguesPage";

vi.mock("../api/client");

function renderPage() {
  return render(
    <MantineProvider>
      <MemoryRouter>
        <DialoguesPage />
      </MemoryRouter>
    </MantineProvider>,
  );
}

beforeEach(() => {
  vi.mocked(client.listDialogues).mockResolvedValue({
    items: [
      { id: 1, created_at: "2026-07-02T10:00:00", rating: 8, name: "c1", persona: "travel_guide", message_count: 4, preview: "Oi" },
      { id: 2, created_at: "2026-07-01T10:00:00", rating: null, name: "c2", persona: "assistant", message_count: 2, preview: "Olá" },
    ],
    total: 2,
    page: 1,
    page_size: 20,
  });
});

describe("DialoguesPage", () => {
  it("loads with default params and lists dialogues", async () => {
    renderPage();
    expect(await screen.findByText("c1")).toBeInTheDocument();
    expect(screen.getByText("não avaliado")).toBeInTheDocument();
    expect(client.listDialogues).toHaveBeenCalledWith(
      expect.objectContaining({ page: 1, page_size: 20, rated: "all", sort: "recent" }),
    );
  });

  it("refetches with the rated filter and resets to page 1", async () => {
    renderPage();
    const user = userEvent.setup();
    await screen.findByText("c1");
    await user.click(screen.getByLabelText("Avaliação"));
    await user.click(await screen.findByText("Avaliadas"));
    await waitFor(() =>
      expect(client.listDialogues).toHaveBeenCalledWith(
        expect.objectContaining({ rated: "rated", page: 1 }),
      ),
    );
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- src/pages/DialoguesPage.test.tsx`
Expected: FAIL — `DialoguesPage` não existe.

- [ ] **Step 3: Create the page**

Criar `frontend/src/pages/DialoguesPage.tsx`:

```tsx
import { Alert, Loader, Pagination, Select, Text, TextInput } from "@mantine/core";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { listDialogues } from "../api/client";
import type { DialogueList, DialogueListParams } from "../api/types";
import { PageHeader } from "../components/PageHeader";

const PAGE_SIZE = 20;

const RATED_OPTIONS = [
  { value: "all", label: "Todas" },
  { value: "rated", label: "Avaliadas" },
  { value: "unrated", label: "Não avaliadas" },
];
const SORT_OPTIONS = [
  { value: "recent", label: "Mais recentes" },
  { value: "oldest", label: "Mais antigos" },
  { value: "rating_desc", label: "Nota ↓" },
  { value: "rating_asc", label: "Nota ↑" },
];

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("pt-BR");
}

export function DialoguesPage() {
  const navigate = useNavigate();
  const [data, setData] = useState<DialogueList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [date, setDate] = useState<string>("");
  const [rated, setRated] = useState<string>("all");
  const [sort, setSort] = useState<string>("recent");
  const [page, setPage] = useState(1);

  useEffect(() => {
    setLoading(true);
    const params: DialogueListParams = {
      page,
      page_size: PAGE_SIZE,
      rated: rated as DialogueListParams["rated"],
      sort: sort as DialogueListParams["sort"],
    };
    if (date) params.date = date;
    listDialogues(params)
      .then((d) => {
        setData(d);
        setLoading(false);
      })
      .catch((e) => {
        setError(String(e));
        setLoading(false);
      });
  }, [date, rated, sort, page]);

  const items = data?.items ?? [];
  const pageCount = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <div>
      <PageHeader
        eyebrow="Passo 05 · Avaliar"
        title="Avaliação de diálogos"
        subtitle="Leia os diálogos salvos e dê uma nota de 0 a 10. Filtre por data, por avaliadas/não avaliadas e ordene pela nota."
      />

      <div className="ditto-filter-bar">
        <TextInput
          label="Data"
          type="date"
          value={date}
          onChange={(e) => {
            setDate(e.currentTarget.value);
            setPage(1);
          }}
          size="xs"
        />
        <Select
          label="Avaliação"
          data={RATED_OPTIONS}
          value={rated}
          onChange={(v) => {
            setRated(v ?? "all");
            setPage(1);
          }}
          size="xs"
          allowDeselect={false}
        />
        <Select
          label="Ordenar"
          data={SORT_OPTIONS}
          value={sort}
          onChange={(v) => {
            setSort(v ?? "recent");
            setPage(1);
          }}
          size="xs"
          allowDeselect={false}
        />
      </div>

      {error && (
        <Alert color="red" variant="light" title="Erro" mb="lg" radius="lg" maw={760}>
          {error}
        </Alert>
      )}

      {loading && (
        <div style={{ display: "flex", justifyContent: "center", padding: "48px 0" }}>
          <Loader size="md" color="#05dbf2" />
        </div>
      )}

      {!loading && items.length === 0 && !error && (
        <p className="ditto-empty">Nenhum diálogo encontrado.</p>
      )}

      {!loading && items.length > 0 && (
        <>
          <div className="ditto-table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Data</th>
                  <th>Config</th>
                  <th>Persona</th>
                  <th>Nº msgs</th>
                  <th>Nota</th>
                </tr>
              </thead>
              <tbody>
                {items.map((it) => (
                  <tr
                    key={it.id}
                    className="ditto-row"
                    onClick={() => navigate(`/dialogues/${it.id}`)}
                  >
                    <td>{formatDate(it.created_at)}</td>
                    <td>{it.name ?? "—"}</td>
                    <td>{it.persona ?? "—"}</td>
                    <td>{it.message_count}</td>
                    <td>
                      {it.rating === null ? (
                        <span className="ditto-chip" style={{ color: "#8892b0" }}>
                          não avaliado
                        </span>
                      ) : (
                        <span className="ditto-chip" style={{ color: "#07f285" }}>
                          {it.rating}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="ditto-table-foot">
            <Text size="xs" c="dimmed">
              {data?.total ?? 0} diálogo(s)
            </Text>
            <Pagination
              total={pageCount}
              value={page}
              onChange={setPage}
              size="sm"
              color="violet"
            />
          </div>
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- src/pages/DialoguesPage.test.tsx`
Expected: PASS (2 passed).

- [ ] **Step 5: Wire the route and nav item**

Em `frontend/src/App.tsx`: adicionar o import (junto aos outros imports de página) `import { DialoguesPage } from "./pages/DialoguesPage";` e adicionar a rota após a rota `/chat` (antes de `/agente`):

```tsx
                <Route
                  path="/dialogues"
                  element={
                    <PageTransition>
                      <DialoguesPage />
                    </PageTransition>
                  }
                />
```

Em `frontend/src/components/Sidebar.tsx`, no array `NAV`, adicionar após o item `/chat`:

```tsx
  { to: "/dialogues", label: "Avaliação de diálogos", icon: <ChartIcon /> },
```

(`ChartIcon` já está importado no arquivo.)

- [ ] **Step 6: Run the full frontend suite + build**

Run: `cd frontend && npm test`
Expected: PASS (todas as suítes).
Run: `cd frontend && npm run build`
Expected: build sem erros de tipo.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/DialoguesPage.tsx frontend/src/pages/DialoguesPage.test.tsx frontend/src/App.tsx frontend/src/components/Sidebar.tsx
git commit -m "feat(b2): dialogues list page with filters, sort and pagination"
```

---

### Task 6: Tela de detalhe `/dialogues/:id` + avaliação

**Files:**
- Create: `frontend/src/pages/DialoguePage.tsx`
- Create: `frontend/src/pages/DialoguePage.test.tsx`
- Modify: `frontend/src/App.tsx` (import + rota `/dialogues/:id`)

**Interfaces:**
- Consumes: `getDialogue`, `saveDialogueRating`, tipo `DialogueDetail` (Task 4); `PageHeader`; classes CSS `ditto-glass ditto-chat-window`, `ditto-chat-msg`, `ditto-chat-bubble`, `ditto-chip`; `useParams`/`useNavigate`.
- Produces: componente `DialoguePage`; rota `/dialogues/:id`.

- [ ] **Step 1: Write the failing test**

Criar `frontend/src/pages/DialoguePage.test.tsx`:

```tsx
import { MantineProvider } from "@mantine/core";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as client from "../api/client";
import { DialoguePage } from "./DialoguePage";

vi.mock("../api/client");

function renderPage() {
  return render(
    <MantineProvider>
      <MemoryRouter initialEntries={["/dialogues/5"]}>
        <Routes>
          <Route path="/dialogues/:id" element={<DialoguePage />} />
        </Routes>
      </MemoryRouter>
    </MantineProvider>,
  );
}

beforeEach(() => {
  vi.mocked(client.getDialogue).mockResolvedValue({
    id: 5,
    created_at: "2026-07-02T10:00:00",
    rating: null,
    config_snapshot: { name: "c1", persona: "travel_guide", base: "viagem", rag: "naive", llm: "gemini" },
    messages: [
      { role: "user", content: "Quais praias?" },
      { role: "assistant", content: "Praia X e Y." },
    ],
  });
  vi.mocked(client.saveDialogueRating).mockResolvedValue({ id: 5, rating: 8 });
});

describe("DialoguePage", () => {
  it("shows the conversation and config summary", async () => {
    renderPage();
    expect(await screen.findByText("Quais praias?")).toBeInTheDocument();
    expect(screen.getByText("Praia X e Y.")).toBeInTheDocument();
    expect(screen.getByText("travel_guide")).toBeInTheDocument();
  });

  it("saves a rating", async () => {
    renderPage();
    const user = userEvent.setup();
    await screen.findByText("Quais praias?");
    await user.type(screen.getByLabelText("Nota (0–10)"), "8");
    await user.click(screen.getByRole("button", { name: /salvar nota/i }));
    await waitFor(() => expect(client.saveDialogueRating).toHaveBeenCalledWith(5, 8));
    expect(await screen.findByText("Nota salva")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- src/pages/DialoguePage.test.tsx`
Expected: FAIL — `DialoguePage` não existe.

- [ ] **Step 3: Create the page**

Criar `frontend/src/pages/DialoguePage.tsx`:

```tsx
import { Alert, Button, Group, Loader, NumberInput, Text } from "@mantine/core";
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { getDialogue, saveDialogueRating } from "../api/client";
import type { DialogueDetail } from "../api/types";
import { PageHeader } from "../components/PageHeader";

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("pt-BR");
}

export function DialoguePage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [detail, setDetail] = useState<DialogueDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [rating, setRating] = useState<number | "">("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    getDialogue(Number(id))
      .then((d) => {
        setDetail(d);
        setRating(d.rating ?? "");
        setLoading(false);
      })
      .catch((e) => {
        setError(String(e));
        setLoading(false);
      });
  }, [id]);

  async function save() {
    if (!id || rating === "") return;
    setSaving(true);
    setSaved(false);
    try {
      await saveDialogueRating(Number(id), Number(rating));
      setSaved(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }

  const snap = detail?.config_snapshot ?? {};

  return (
    <div>
      <Button
        variant="subtle"
        color="gray"
        size="xs"
        mb="md"
        onClick={() => navigate("/dialogues")}
      >
        ← Voltar aos diálogos
      </Button>

      <PageHeader
        eyebrow="Passo 05 · Avaliar"
        title="Diálogo"
        subtitle="Leia a conversa e atribua uma nota de 0 a 10."
      />

      {loading && (
        <div style={{ display: "flex", justifyContent: "center", padding: "48px 0" }}>
          <Loader size="md" color="#05dbf2" />
        </div>
      )}

      {error && (
        <Alert color="red" variant="light" title="Erro" radius="lg" maw={760}>
          {error}
        </Alert>
      )}

      {detail && !loading && (
        <>
          <Group gap="xs" mb="lg">
            <span className="ditto-chip" style={{ color: "#05dbf2" }}>
              {snap.persona ?? "—"}
            </span>
            <span className="ditto-chip" style={{ color: "#f2ec91" }}>
              {snap.base ?? "—"}
            </span>
            <span className="ditto-chip" style={{ color: "#07f285" }}>
              {snap.rag ?? "—"} · {snap.llm ?? "—"}
            </span>
            <Text size="sm" c="dimmed">
              {formatDate(detail.created_at)}
            </Text>
          </Group>

          <div className="ditto-glass ditto-chat-window">
            {detail.messages.map((m, i) => (
              <div key={i} className="ditto-chat-msg" data-role={m.role}>
                <span className="ditto-chat-bubble">{m.content}</span>
              </div>
            ))}
          </div>

          <Group mt="lg" align="flex-end" gap="sm">
            <NumberInput
              label="Nota (0–10)"
              min={0}
              max={10}
              value={rating}
              onChange={(v) => setRating(typeof v === "number" ? v : "")}
              w={140}
            />
            <Button color="violet" loading={saving} disabled={rating === ""} onClick={save}>
              Salvar nota
            </Button>
            {saved && (
              <Text size="sm" c="#07f285">
                Nota salva
              </Text>
            )}
          </Group>
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- src/pages/DialoguePage.test.tsx`
Expected: PASS (2 passed).

- [ ] **Step 5: Wire the route**

Em `frontend/src/App.tsx`: adicionar o import `import { DialoguePage } from "./pages/DialoguePage";` e a rota logo após a rota `/dialogues` criada na Task 5:

```tsx
                <Route
                  path="/dialogues/:id"
                  element={
                    <PageTransition>
                      <DialoguePage />
                    </PageTransition>
                  }
                />
```

- [ ] **Step 6: Run the full frontend suite + build**

Run: `cd frontend && npm test`
Expected: PASS (todas as suítes).
Run: `cd frontend && npm run build`
Expected: build sem erros.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/DialoguePage.tsx frontend/src/pages/DialoguePage.test.tsx frontend/src/App.tsx
git commit -m "feat(b2): dialogue detail page with 0-10 rating"
```

---

## Self-Review

**Spec coverage:**
- Colunas `rating` + `rated_at` → Task 1. ✓
- `GET /dialogues` paginado + filtros `date`/`rated` + `sort` (unrated por último) + `total` + campos do item (name, persona, message_count, preview) → Task 2. ✓
- `GET /dialogues/{id}` (mensagens ordenadas + snapshot) e `PUT /dialogues/{id}/rating` (0–10, rated_at, editável, 404/422) → Task 3. ✓
- Cliente + tipos → Task 4. ✓
- Tela lista `/dialogues` (tabela, filtros, ordenação, paginação) + Sidebar → Task 5. ✓
- Tela detalhe `/dialogues/:id` (conversa + resumo config + nota editável) → Task 6. ✓
- ALTER manual pós-deploy → Global Constraints. ✓

**Placeholder scan:** nenhum TBD/TODO; todo passo com código completo e comando + saída esperada.

**Type consistency:** `listDialogues`/`getDialogue`/`saveDialogueRating` e os tipos `DialogueList`/`DialogueListParams`/`DialogueDetail`/`DialogueListItem` idênticos entre Task 4 (definição) e Tasks 5–6 (uso). Item do backend (`_dialogue_list_item`, Task 2) tem exatamente os campos de `DialogueListItem` (Task 4). Endpoint de rating retorna `{id, rating}` (Task 3) casando com o tipo de retorno de `saveDialogueRating` (Task 4). Label "Nota (0–10)" com en-dash idêntico entre componente e teste (Task 6).
