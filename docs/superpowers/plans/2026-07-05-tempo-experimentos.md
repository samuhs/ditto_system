# Tempo nos experimentos (início + duração) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mostrar a data de início de cada experimento na listagem (paginada) e o início + duração (ao vivo enquanto roda) na tela do experimento.

**Architecture:** `GET /experiments` vira paginado e inclui `created_at`; `GET /experiments/{id}` inclui `created_at`/`finished_at`. O frontend adapta `listExperiments` para o envelope, mostra a data + paginação na lista, e calcula/exibe a duração no detalhe via um helper `formatDuration` (usando o polling existente para o tempo ao vivo). Sem migração — usa colunas já existentes.

**Tech Stack:** FastAPI (Python 3.11+, venv `backend/.venv`), pytest; React + Vite + TS + Mantine, vitest.

## Global Constraints

- Identificadores/docstrings em **inglês**; UI em **PT-BR**.
- "Início" = `Experiment.created_at` (sem coluna/migração nova); "Duração" = `finished_at − created_at` (concluídos) ou `agora − created_at` (rodando).
- `GET /experiments`: paginado, `page: int = 1` (>=1), `page_size: int = 20` (1–100), envelope `{items, total, page, page_size}` (igual ao `GET /dialogues`); cada item `{id, name, status, created_at}` com `created_at` em ISO; ordem `id desc`.
- `GET /experiments/{id}`: resposta ganha `created_at` e `finished_at` (ISO ou null).
- `listExperiments` no cliente passa a retornar o envelope (`ExperimentList`); todos os consumidores no front são atualizados.
- Testes herméticos (backend: fakes via `ExperimentDeps`, TestClient sem context-manager; frontend: mocks do client).
- Rodar: backend `cd backend && ./.venv/bin/python -m pytest <arquivo> -v`; frontend `cd frontend && npx vitest run <arquivo>`.

---

### Task 1: Backend — lista paginada + created_at, detalhe com timestamps

**Files:**
- Modify: `backend/app/api/experiments.py` (import de `Query`; `list_experiments`; `get_experiment`)
- Test: `backend/tests/test_experiments_api.py`

**Interfaces:**
- Consumes: `Experiment` model (com `created_at`/`finished_at`), `ExperimentDeps`, `get_experiment_deps`.
- Produces: `GET /experiments` → `{items:[{id,name,status,created_at}], total, page, page_size}`; `GET /experiments/{id}` com `created_at`/`finished_at`.

- [ ] **Step 1: Write the failing tests**

Em `backend/tests/test_experiments_api.py`: **substituir** a função existente `test_list_experiments` (que assumia o retorno como lista simples) pelas duas abaixo (usam o `client` e `_config_payload` já existentes no arquivo; `io` já importado):

```python
def test_list_experiments_paginated(client):
    files = {"questions": ("q.csv", io.BytesIO(b"pergunta,resposta_referencia\nWhere?,\n"), "text/csv")}
    client.post("/experiments", data={"config": _config_payload()}, files=files)
    body = client.get("/experiments").json()
    assert set(body.keys()) == {"items", "total", "page", "page_size"}
    assert body["total"] >= 1
    assert body["page"] == 1 and body["page_size"] == 20
    item = body["items"][0]
    assert {"id", "name", "status", "created_at"} <= set(item.keys())
    assert item["created_at"]  # ISO string present


def test_get_experiment_includes_timestamps(client):
    files = {"questions": ("q.csv", io.BytesIO(b"pergunta,resposta_referencia\nWhere?,\n"), "text/csv")}
    exp_id = client.post("/experiments", data={"config": _config_payload()}, files=files).json()["id"]
    detail = client.get(f"/experiments/{exp_id}").json()
    assert detail["created_at"]  # present
    assert detail["finished_at"]  # experiment ran to completion → finished_at set
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_experiments_api.py::test_list_experiments_paginated tests/test_experiments_api.py::test_get_experiment_includes_timestamps -v`
Expected: FAIL — a lista devolve uma lista simples (sem `items`/`total`); o detalhe não tem `created_at`/`finished_at`.

- [ ] **Step 3: Add the `Query` import**

Em `backend/app/api/experiments.py`, incluir `Query` no import do FastAPI (a linha atual é `from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile`) →

```python
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
```

- [ ] **Step 4: Paginate the list endpoint**

Em `backend/app/api/experiments.py`, substituir a função `list_experiments` inteira por:

```python
@router.get("/experiments")
def list_experiments(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    deps: ExperimentDeps = Depends(get_experiment_deps),
) -> dict:
    """List experiments (paginated), most recent first."""
    session = deps.session_factory()
    try:
        query = session.query(Experiment).order_by(Experiment.id.desc())
        total = query.count()
        rows = query.offset((page - 1) * page_size).limit(page_size).all()
        items = [
            {
                "id": e.id,
                "name": e.name,
                "status": e.status,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in rows
        ]
        return {"items": items, "total": total, "page": page, "page_size": page_size}
    finally:
        session.close()
```

- [ ] **Step 5: Add timestamps to the detail endpoint**

Em `backend/app/api/experiments.py`, na função `get_experiment`, dentro do dict retornado (que já tem `id`, `name`, `status`, `pause_requested`, `error`, `progress`, ...), adicionar as duas chaves (por exemplo, logo após `"status": experiment.status,`):

```python
            "created_at": experiment.created_at.isoformat() if experiment.created_at else None,
            "finished_at": experiment.finished_at.isoformat() if experiment.finished_at else None,
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_experiments_api.py -v`
Expected: PASS (os dois novos + os demais do arquivo).

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/experiments.py backend/tests/test_experiments_api.py
git commit -m "feat(experiments): paginate list + created_at, expose timestamps on detail"
```

---

### Task 2: Frontend — tipos + cliente `listExperiments` (envelope)

**Files:**
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/api/client.ts`
- Test: `frontend/src/api/client.test.ts`

**Interfaces:**
- Consumes: `GET /experiments` paginado (Task 1).
- Produces: `ExperimentSummary` com `created_at`; `ExperimentList`; `ExperimentDetail` com `created_at?`/`finished_at?`; `listExperiments(page?, pageSize?): Promise<ExperimentList>`.

- [ ] **Step 1: Write the failing test**

Em `frontend/src/api/client.test.ts`, **substituir** o teste existente `"listExperiments returns the summary list"` por:

```typescript
  it("listExperiments returns the paginated envelope", async () => {
    const body = {
      items: [{ id: 1, name: "kind-ember-89", status: "done", created_at: "2026-07-05T10:00:00" }],
      total: 1, page: 1, page_size: 20,
    };
    vi.stubGlobal("fetch", mockFetchOnce(body));
    await expect(listExperiments()).resolves.toEqual(body);
    expect(fetch).toHaveBeenCalledWith("/api/experiments?page=1&page_size=20");
  });
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/api/client.test.ts`
Expected: FAIL — `listExperiments` chama `/api/experiments` (sem query) e devolve a lista simples.

- [ ] **Step 3: Update the types**

Em `frontend/src/api/types.ts`:

Trocar `ExperimentSummary` por (adicionar `created_at`):

```typescript
export interface ExperimentSummary {
  id: number;
  name: string;
  status: string;
  created_at: string;
}

export interface ExperimentList {
  items: ExperimentSummary[];
  total: number;
  page: number;
  page_size: number;
}
```

Em `ExperimentDetail`, adicionar após `status: string;`:

```typescript
  created_at?: string;
  finished_at?: string;
```

- [ ] **Step 4: Update the client function**

Em `frontend/src/api/client.ts`: incluir `ExperimentList` no bloco `import type { ... } from "./types";` e substituir a função `listExperiments`:

```typescript
export async function listExperiments(page = 1, pageSize = 20): Promise<ExperimentList> {
  return asJson<ExperimentList>(await fetch(`${BASE}/experiments?page=${page}&page_size=${pageSize}`));
}
```

(Se `ExperimentSummary` não for mais usado diretamente no import de `client.ts`, mantê-lo se ainda referenciado; caso contrário remover do import para evitar variável não usada.)

- [ ] **Step 5: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/api/client.test.ts`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/types.ts frontend/src/api/client.ts frontend/src/api/client.test.ts
git commit -m "feat(experiments): listExperiments returns paginated envelope with created_at"
```

---

### Task 3: Frontend — Resultados: data de início + paginação

**Files:**
- Modify: `frontend/src/pages/ResultsPage.tsx`
- Test: `frontend/src/pages/ResultsPage.test.tsx`

**Interfaces:**
- Consumes: `listExperiments(page, pageSize): Promise<ExperimentList>` e `ExperimentList` (Task 2).
- Produces: lista com data de início por experimento + `Pagination`.

- [ ] **Step 1: Write the failing test**

Em `frontend/src/pages/ResultsPage.test.tsx`: (1) adicionar `waitFor` ao import de `@testing-library/react`; (2) trocar o mock do `beforeEach` e adicionar dois testes. O `beforeEach` passa a ser:

```typescript
beforeEach(() => {
  vi.mocked(client.listExperiments).mockResolvedValue({
    items: [
      { id: 7, name: "kind-ember-89", status: "done", created_at: "2026-07-05T10:00:00" },
      { id: 8, name: "swift-fox-12", status: "pending", created_at: "2026-07-04T09:00:00" },
    ],
    total: 2,
    page: 1,
    page_size: 20,
  });
});
```

E adicionar, dentro do `describe`:

```typescript
  it("shows the start date of each experiment", async () => {
    renderPage();
    await screen.findByText("kind-ember-89");
    expect(screen.getAllByText(/2026/).length).toBeGreaterThan(0);
  });

  it("paginates via the page control", async () => {
    vi.mocked(client.listExperiments).mockResolvedValue({
      items: [{ id: 7, name: "kind-ember-89", status: "done", created_at: "2026-07-05T10:00:00" }],
      total: 40,
      page: 1,
      page_size: 20,
    });
    renderPage();
    const user = userEvent.setup();
    await screen.findByText("kind-ember-89");
    await user.click(screen.getByRole("button", { name: "2" }));
    await waitFor(() => expect(client.listExperiments).toHaveBeenCalledWith(2, 20));
  });
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/pages/ResultsPage.test.tsx`
Expected: FAIL — a página ainda espera lista simples (quebra no `.map`/tipo) e não tem paginação.

- [ ] **Step 3: Rewrite the page**

Substituir `frontend/src/pages/ResultsPage.tsx` por:

```tsx
import { Alert, Group, Pagination, Text } from "@mantine/core";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { listExperiments } from "../api/client";
import type { ExperimentList } from "../api/types";
import { PageHeader } from "../components/PageHeader";

const PAGE_SIZE = 20;

function statusColor(status: string): string {
  if (status === "done") return "#07f285";
  if (status === "failed") return "#f26dcf";
  if (status === "paused") return "#f2ec91";
  return "#05dbf2";
}

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("pt-BR");
}

export function ResultsPage() {
  const navigate = useNavigate();
  const [data, setData] = useState<ExperimentList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);

  useEffect(() => {
    setError(null);
    listExperiments(page, PAGE_SIZE)
      .then(setData)
      .catch((e) => setError(String(e)));
  }, [page]);

  const items = data?.items ?? [];
  const pageCount = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <div>
      <PageHeader
        eyebrow="Passo 03 · Ranquear"
        title="Resultados"
        subtitle="Clique num experimento para abrir sua página com a tabela completa, ordenável por métrica, com filtros e paginação."
      />

      {error && (
        <Alert color="red" variant="light" title="Erro" mb="lg" radius="lg" maw={760}>
          {error}
        </Alert>
      )}

      <div className="ditto-exp-list" style={{ maxWidth: 900 }}>
        {items.length === 0 && !error && (
          <p className="ditto-empty">Nenhum experimento encontrado.</p>
        )}
        {items.map((exp) => (
          <button
            key={exp.id}
            className="ditto-exp-row"
            onClick={() => navigate(`/results/${exp.id}`)}
          >
            <Text fw={600} fz="sm">
              {exp.name}
            </Text>
            <Text size="xs" c="dimmed" style={{ marginLeft: "auto", marginRight: 12 }}>
              {formatDate(exp.created_at)}
            </Text>
            <span className="ditto-chip" style={{ color: statusColor(exp.status) }}>
              {exp.status}
            </span>
          </button>
        ))}
      </div>

      {data && data.total > data.page_size && (
        <Group justify="center" mt="lg">
          <Pagination total={pageCount} value={page} onChange={setPage} size="sm" color="violet" />
        </Group>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/pages/ResultsPage.test.tsx`
Expected: PASS (todos, incluindo os dois novos).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/ResultsPage.tsx frontend/src/pages/ResultsPage.test.tsx
git commit -m "feat(experiments): show start date + pagination on the results list"
```

---

### Task 4: Frontend — detalhe: início + duração (ao vivo) + `formatDuration`

**Files:**
- Create: `frontend/src/utils/duration.ts`
- Create: `frontend/src/utils/duration.test.ts`
- Modify: `frontend/src/pages/ExperimentDetailPage.tsx`
- Test: `frontend/src/pages/ExperimentDetailPage.test.tsx`

**Interfaces:**
- Consumes: `ExperimentDetail.created_at?`/`finished_at?` (Task 2).
- Produces: `formatDuration(ms: number): string`; linha "Iniciado em … · Duração …" no cabeçalho do detalhe.

- [ ] **Step 1: Write the failing tests**

Criar `frontend/src/utils/duration.test.ts`:

```typescript
import { describe, expect, it } from "vitest";

import { formatDuration } from "./duration";

describe("formatDuration", () => {
  it("formats seconds only", () => expect(formatDuration(45000)).toBe("45s"));
  it("formats minutes and seconds", () => expect(formatDuration(130000)).toBe("2m 10s"));
  it("formats hours, minutes and seconds", () => expect(formatDuration(5025000)).toBe("1h 23m 45s"));
  it("clamps zero and negatives", () => {
    expect(formatDuration(0)).toBe("0s");
    expect(formatDuration(-100)).toBe("0s");
  });
});
```

Em `frontend/src/pages/ExperimentDetailPage.test.tsx`, adicionar (dentro do `describe`):

```typescript
  it("shows start time and computed duration for a finished experiment", async () => {
    vi.mocked(client.getExperiment).mockResolvedValue({
      id: 7,
      name: "timed",
      status: "done",
      created_at: "2026-07-05T10:00:00.000Z",
      finished_at: "2026-07-05T10:02:10.000Z",
      progress: { completed: 1, total: 1 },
      results: [
        {
          chunking: "recursive", embedding: "gemini", rag: "naive", retriever: "similarity",
          llm: "gemini", question: "Q", answer: "A", scores: { faithfulness: 0.8 }, latency_ms: 1, tokens: 1,
        },
      ],
    });
    renderPage();
    expect(await screen.findByText(/Duração 2m 10s/)).toBeInTheDocument();
  });

  it("shows a live duration while running", async () => {
    vi.mocked(client.getExperiment).mockResolvedValue({
      id: 7,
      name: "running",
      status: "running",
      created_at: new Date(Date.now() - 45000).toISOString(),
      progress: { completed: 0, total: 4 },
      results: [],
    });
    renderPage();
    expect(await screen.findByText(/Duração/)).toBeInTheDocument();
  });
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/utils/duration.test.ts src/pages/ExperimentDetailPage.test.tsx`
Expected: FAIL — `duration.ts` não existe; a página não mostra duração.

- [ ] **Step 3: Create the duration helper**

Criar `frontend/src/utils/duration.ts`:

```typescript
/** Human-readable duration ("1h 23m 45s", "2m 10s", "45s"); clamps to "0s". */
export function formatDuration(ms: number): string {
  const totalSec = Math.max(0, Math.floor(ms / 1000));
  const h = Math.floor(totalSec / 3600);
  const m = Math.floor((totalSec % 3600) / 60);
  const s = totalSec % 60;
  const parts: string[] = [];
  if (h > 0) parts.push(`${h}h`);
  if (h > 0 || m > 0) parts.push(`${m}m`);
  parts.push(`${s}s`);
  return parts.join(" ");
}
```

- [ ] **Step 4: Show start + duration on the detail header**

Em `frontend/src/pages/ExperimentDetailPage.tsx`:

1. Adicionar os imports no topo (junto dos existentes):
```tsx
import { formatDuration } from "../utils/duration";
```

2. Adicionar dois helpers de módulo (fora do componente, perto do `statusColor` existente):
```tsx
function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("pt-BR");
}

function experimentDurationMs(createdAt?: string, finishedAt?: string): number | null {
  if (!createdAt) return null;
  const start = new Date(createdAt).getTime();
  const end = finishedAt ? new Date(finishedAt).getTime() : Date.now();
  return end - start;
}
```

3. No bloco de cabeçalho `{detail && (<Group ...>...)}`, logo após o `<Text size="sm" c="dimmed">{results.length} resultado(s) · {metricKeys.length} métrica(s)</Text>`, inserir a linha de tempo:
```tsx
          {detail.created_at && (
            <Text size="sm" c="dimmed">
              Iniciado em {formatDate(detail.created_at)} · Duração{" "}
              {formatDuration(experimentDurationMs(detail.created_at, detail.finished_at) ?? 0)}
            </Text>
          )}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/utils/duration.test.ts src/pages/ExperimentDetailPage.test.tsx`
Expected: PASS.

- [ ] **Step 6: Run the full frontend suite + build**

Run: `cd frontend && npx vitest run`
Expected: PASS (todas as suítes).
Run: `cd frontend && npm run build`
Expected: build sem erros de tipo.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/utils/duration.ts frontend/src/utils/duration.test.ts frontend/src/pages/ExperimentDetailPage.tsx frontend/src/pages/ExperimentDetailPage.test.tsx
git commit -m "feat(experiments): show start time and live duration on the experiment page"
```

---

## Self-Review

**Spec coverage:**
- Lista paginada + `created_at` → Task 1 (backend) + Task 3 (front). ✓
- Detalhe com `created_at`/`finished_at` → Task 1. ✓
- `listExperiments` envelope + tipos → Task 2. ✓
- Data de início na lista + paginação → Task 3. ✓
- "Iniciado em" + "Duração" (ao vivo via polling) + `formatDuration` → Task 4. ✓
- Testes backend (lista/detalhe) e frontend (client, ResultsPage, formatDuration, detalhe) → todas as tasks. ✓

**Placeholder scan:** sem TBD/TODO; código completo em cada passo; comandos com saída esperada.

**Type consistency:** `ExperimentList {items,total,page,page_size}` idêntico entre Task 2 (def), o retorno do backend (Task 1) e o consumo em ResultsPage (Task 3). `ExperimentSummary.created_at` (Task 2) ↔ item do backend (Task 1) ↔ `formatDate(exp.created_at)` (Task 3). `ExperimentDetail.created_at?/finished_at?` (Task 2) ↔ resposta do GET (Task 1) ↔ `experimentDurationMs(detail.created_at, detail.finished_at)` (Task 4). `listExperiments(page?, pageSize?)` (Task 2) ↔ chamada `listExperiments(2, 20)` no teste e `listExperiments(page, PAGE_SIZE)` na página (Task 3). `formatDuration(ms)` (Task 4 util) ↔ uso no detalhe (Task 4).
