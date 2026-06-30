# Fatia A — Plano 7: Frontend — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir o frontend da Fatia A: três telas (inserir documentos, gerar teste de qualidade com polling, visualização de resultados) em React + Vite + TypeScript + Mantine, consumindo a API; servido por Nginx com reverse-proxy para o backend.

**Architecture:** SPA Vite/React/TS. Um cliente de API isolado (`src/api/`) que os componentes consomem; telas em `src/pages/`; navegação via react-router num `AppShell` do Mantine. Testes com vitest + Testing Library, mockando o cliente de API (sem backend). Docker multi-stage: build com Node, runtime Nginx servindo o estático e fazendo proxy de `/api/` para `api:8000`.

**Tech Stack:** Node 22, Vite, React 18, TypeScript, Mantine v7, react-router-dom v6, vitest, @testing-library/react, jsdom, Nginx.

## Global Constraints

- **Código em inglês:** identificadores, comentários e mensagens em inglês. Texto de UI visível ao usuário em **PT-BR** (é um produto para o usuário do doutorado; rótulos como "Inserir documentos" são conteúdo, não código).
- TypeScript estrito; componentes funcionais com hooks.
- O cliente de API vive só em `src/api/`; componentes nunca chamam `fetch` direto.
- Base da API por `import.meta.env.VITE_API_URL ?? "/api"`; em produção o Nginx faz proxy de `/api/` → `api:8000`.
- **Testes sem backend:** componentes mockam `src/api/client` (vi.mock); o cliente em si é testado com `fetch` mockado.
- Rodar testes: `cd frontend && npm run test -- --run`. Saída limpa (sem testes falhando/pendentes inesperados).
- Commits frequentes, um por task.

---

## File Structure

```
frontend/
  package.json
  tsconfig.json
  tsconfig.node.json
  vite.config.ts            # plugin react + proxy /api (dev) + config vitest
  index.html
  Dockerfile                # multi-stage build -> nginx
  nginx.conf                # serve estatico + proxy /api/ -> api:8000
  .dockerignore
  src/
    main.tsx                # MantineProvider + BrowserRouter
    App.tsx                 # AppShell + NavLinks + Routes
    test/setup.ts           # importa @testing-library/jest-dom
    api/
      types.ts              # tipos da API
      client.ts             # getOptions, ingest, createExperiment, getExperiment, listExperiments
      client.test.ts        # testa o cliente com fetch mockado
    pages/
      IngestPage.tsx
      IngestPage.test.tsx
      ExperimentPage.tsx
      ExperimentPage.test.tsx
      ResultsPage.tsx
      ResultsPage.test.tsx
docker-compose.yml          # + servico frontend
Makefile                    # + alvos front (front-install, front-test, front-build)
```

Também: extensão do backend `GET /options` (Task 1) para incluir `rags`, `retrievers`, `metrics`.

---

### Task 1: Backend — estender `GET /options` (rags, retrievers, metrics)

**Files:**
- Modify: `backend/app/api/options.py`
- Modify: `backend/tests/test_ingest_api.py` (asserções das novas chaves)

**Interfaces:**
- Consumes: `chunking_registry`, `embedding_registry`, `llm_registry`, `rag_registry`, `retrieval_registry`, `evaluation_registry`.
- Produces: `GET /options` → `{"chunkings", "embeddings", "llms", "rags", "retrievers", "metrics"}` (todas listas de nomes).

- [ ] **Step 1: Atualizar o teste de options**

Em `backend/tests/test_ingest_api.py`, no teste `test_options_lists_registered_techniques`, acrescente asserções:

```python
    assert {"naive", "agentic"} <= set(body["rags"])
    assert {"similarity", "mmr", "multi_query", "parent_document"} <= set(body["retrievers"])
    assert {"answer_relevancy", "faithfulness", "rouge_l"} <= set(body["metrics"])
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_ingest_api.py::test_options_lists_registered_techniques -v`
Expected: FAIL com `KeyError: 'rags'`.

- [ ] **Step 3: Estender o endpoint**

`backend/app/api/options.py`:

```python
"""Endpoint exposing the available techniques from the registries."""
from fastapi import APIRouter

from app.core.chunking.base import chunking_registry
from app.core.embedding.base import embedding_registry
from app.core.evaluation.base import evaluation_registry
from app.core.llm.base import llm_registry
from app.core.rag.base import rag_registry
from app.core.retrieval.base import retrieval_registry

router = APIRouter()


@router.get("/options")
def options() -> dict[str, list[str]]:
    """List the registered techniques available across the pipeline."""
    return {
        "chunkings": chunking_registry.names(),
        "embeddings": embedding_registry.names(),
        "llms": llm_registry.names(),
        "rags": rag_registry.names(),
        "retrievers": retrieval_registry.names(),
        "metrics": evaluation_registry.names(),
    }
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd backend && ./.venv/bin/python -m pytest -q`
Expected: PASS (todos). Zero warnings.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/options.py backend/tests/test_ingest_api.py
git commit -m "feat: /options also lists rags, retrievers, and metrics"
```

---

### Task 2: Scaffold do frontend + cliente de API + Docker/Nginx

**Files:**
- Create: `frontend/package.json`, `frontend/tsconfig.json`, `frontend/tsconfig.node.json`, `frontend/vite.config.ts`, `frontend/index.html`, `frontend/.dockerignore`
- Create: `frontend/src/main.tsx`, `frontend/src/App.tsx`, `frontend/src/test/setup.ts`
- Create: `frontend/src/api/types.ts`, `frontend/src/api/client.ts`, `frontend/src/api/client.test.ts`
- Create: `frontend/Dockerfile`, `frontend/nginx.conf`
- Modify: `docker-compose.yml` (serviço frontend), `Makefile` (alvos front)

**Interfaces:**
- Produces (cliente de API):
  - `getOptions(): Promise<Options>` → GET `/options`.
  - `ingest(form: FormData): Promise<IngestResult>` → POST `/ingest`.
  - `createExperiment(form: FormData): Promise<ExperimentRef>` → POST `/experiments`.
  - `getExperiment(id: number): Promise<ExperimentDetail>` → GET `/experiments/:id`.
  - `listExperiments(): Promise<ExperimentSummary[]>` → GET `/experiments`.
  - Base = `import.meta.env.VITE_API_URL ?? "/api"`; em erro HTTP, `throw new Error(...)`.

- [ ] **Step 1: Criar `package.json`**

`frontend/package.json`:

```json
{
  "name": "ditto-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "test": "vitest"
  },
  "dependencies": {
    "@mantine/core": "^7.13.0",
    "@mantine/hooks": "^7.13.0",
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.26.0"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "^6.5.0",
    "@testing-library/react": "^16.0.0",
    "@testing-library/user-event": "^14.5.2",
    "@types/react": "^18.3.5",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.1",
    "jsdom": "^25.0.0",
    "typescript": "^5.5.4",
    "vite": "^5.4.0",
    "vitest": "^2.0.5"
  }
}
```

- [ ] **Step 2: Criar configs (`tsconfig`, `vite`, `index.html`, `.dockerignore`)**

`frontend/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "types": ["vitest/globals", "@testing-library/jest-dom"]
  },
  "include": ["src"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

`frontend/tsconfig.node.json`:

```json
{
  "compilerOptions": {
    "composite": true,
    "skipLibCheck": true,
    "module": "ESNext",
    "moduleResolution": "bundler",
    "allowSyntheticDefaultImports": true,
    "strict": true,
    "noEmit": true
  },
  "include": ["vite.config.ts"]
}
```

`frontend/vite.config.ts`:

```ts
/// <reference types="vitest" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/test/setup.ts",
    css: false,
  },
});
```

`frontend/index.html`:

```html
<!doctype html>
<html lang="pt-BR">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Ditto</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

`frontend/.dockerignore`:

```
node_modules
dist
```

- [ ] **Step 3: Criar setup de teste e os tipos**

`frontend/src/test/setup.ts`:

```ts
import "@testing-library/jest-dom";
```

`frontend/src/api/types.ts`:

```ts
export interface Options {
  chunkings: string[];
  embeddings: string[];
  llms: string[];
  rags: string[];
  retrievers: string[];
  metrics: string[];
}

export interface IngestResult {
  collections: string[];
  total_chunks: number;
}

export interface ExperimentRef {
  id: number;
  name: string;
  status: string;
}

export interface ExperimentSummary {
  id: number;
  name: string;
  status: string;
}

export interface ExperimentResultRow {
  chunking: string;
  embedding: string;
  rag: string;
  retriever: string;
  question: string;
  answer: string;
  scores: Record<string, number>;
  latency_ms: number;
  tokens: number;
}

export interface ExperimentDetail {
  id: number;
  name: string;
  status: string;
  results: ExperimentResultRow[];
}
```

- [ ] **Step 4: Escrever o teste do cliente que falha**

`frontend/src/api/client.test.ts`:

```ts
import { afterEach, describe, expect, it, vi } from "vitest";

import { createExperiment, getExperiment, getOptions, ingest } from "./client";

function mockFetchOnce(body: unknown, ok = true, status = 200) {
  return vi.fn().mockResolvedValue({
    ok,
    status,
    json: () => Promise.resolve(body),
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("api client", () => {
  it("getOptions returns parsed options", async () => {
    const options = { chunkings: ["recursive"], embeddings: ["gemini"], llms: ["gemini"], rags: ["naive"], retrievers: ["similarity"], metrics: ["rouge_l"] };
    vi.stubGlobal("fetch", mockFetchOnce(options));
    await expect(getOptions()).resolves.toEqual(options);
    expect(fetch).toHaveBeenCalledWith("/api/options");
  });

  it("ingest posts form data and returns the result", async () => {
    const result = { collections: ["viagem__recursive__gemini"], total_chunks: 10 };
    const fetchMock = mockFetchOnce(result);
    vi.stubGlobal("fetch", fetchMock);
    const form = new FormData();
    await expect(ingest(form)).resolves.toEqual(result);
    expect(fetchMock).toHaveBeenCalledWith("/api/ingest", { method: "POST", body: form });
  });

  it("createExperiment returns the experiment ref", async () => {
    const ref = { id: 1, name: "kind-ember-89", status: "pending" };
    vi.stubGlobal("fetch", mockFetchOnce(ref));
    const form = new FormData();
    await expect(createExperiment(form)).resolves.toEqual(ref);
  });

  it("getExperiment returns the detail", async () => {
    const detail = { id: 1, name: "x", status: "done", results: [] };
    vi.stubGlobal("fetch", mockFetchOnce(detail));
    await expect(getExperiment(1)).resolves.toEqual(detail);
    expect(fetch).toHaveBeenCalledWith("/api/experiments/1");
  });

  it("throws on http error", async () => {
    vi.stubGlobal("fetch", mockFetchOnce({}, false, 500));
    await expect(getOptions()).rejects.toThrow();
  });
});
```

- [ ] **Step 5: Rodar e ver falhar**

Run: `cd frontend && npm install && npm run test -- --run`
Expected: FAIL — `./client` ainda não existe.

- [ ] **Step 6: Implementar o cliente**

`frontend/src/api/client.ts`:

```ts
import type {
  ExperimentDetail,
  ExperimentRef,
  ExperimentSummary,
  IngestResult,
  Options,
} from "./types";

const BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? "/api";

async function asJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw new Error(`request failed with status ${response.status}`);
  }
  return (await response.json()) as T;
}

export async function getOptions(): Promise<Options> {
  return asJson<Options>(await fetch(`${BASE}/options`));
}

export async function ingest(form: FormData): Promise<IngestResult> {
  return asJson<IngestResult>(await fetch(`${BASE}/ingest`, { method: "POST", body: form }));
}

export async function createExperiment(form: FormData): Promise<ExperimentRef> {
  return asJson<ExperimentRef>(
    await fetch(`${BASE}/experiments`, { method: "POST", body: form }),
  );
}

export async function getExperiment(id: number): Promise<ExperimentDetail> {
  return asJson<ExperimentDetail>(await fetch(`${BASE}/experiments/${id}`));
}

export async function listExperiments(): Promise<ExperimentSummary[]> {
  return asJson<ExperimentSummary[]>(await fetch(`${BASE}/experiments`));
}
```

- [ ] **Step 7: Implementar `main.tsx` e um `App.tsx` mínimo (placeholder das rotas)**

`frontend/src/main.tsx`:

```tsx
import { MantineProvider } from "@mantine/core";
import "@mantine/core/styles.css";
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import { App } from "./App";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <MantineProvider>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </MantineProvider>
  </React.StrictMode>,
);
```

`frontend/src/App.tsx` (mínimo agora; as rotas reais entram na Task 5):

```tsx
export function App() {
  return <div>Ditto</div>;
}
```

- [ ] **Step 8: Rodar e ver passar; validar o build**

Run: `cd frontend && npm run test -- --run`
Expected: PASS (5 testes do cliente).
Run: `cd frontend && npm run build`
Expected: build conclui sem erros de tipo.

- [ ] **Step 9: Criar Dockerfile e nginx.conf**

`frontend/Dockerfile`:

```dockerfile
FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build

FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
```

`frontend/nginx.conf`:

```nginx
server {
    listen 80;
    root /usr/share/nginx/html;
    index index.html;

    location /api/ {
        proxy_pass http://api:8000/;
    }

    location / {
        try_files $uri /index.html;
    }
}
```

- [ ] **Step 10: Adicionar o serviço no `docker-compose.yml` e alvos no `Makefile`**

No `docker-compose.yml`, acrescente (no mapa `services`):

```yaml
  frontend:
    build: ./frontend
    ports:
      - "3000:80"
    depends_on:
      - api
```

No `Makefile`, acrescente:

```makefile
front-install:
	cd frontend && npm install

front-test:
	cd frontend && npm run test -- --run

front-build:
	cd frontend && npm run build
```

- [ ] **Step 11: Commit**

```bash
git add frontend docker-compose.yml Makefile
git commit -m "feat: frontend scaffold (vite/react/ts/mantine) + api client + nginx"
```

---

### Task 3: Tela de inserir documentos

**Files:**
- Create: `frontend/src/pages/IngestPage.tsx`
- Create: `frontend/src/pages/IngestPage.test.tsx`

**Interfaces:**
- Consumes: `getOptions`, `ingest` de `../api/client`.
- Produces: `IngestPage` — carrega as opções, mostra `TextInput` (nome da base), `MultiSelect` de chunkings e embeddings, `FileInput` (múltiplos), botão "Inserir"; ao submeter monta `FormData` (`base`, `chunkings` CSV, `embeddings` CSV, `files`) e exibe um `Alert` com o resultado.

- [ ] **Step 1: Escrever o teste que falha**

`frontend/src/pages/IngestPage.test.tsx`:

```tsx
import { MantineProvider } from "@mantine/core";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as client from "../api/client";
import { IngestPage } from "./IngestPage";

vi.mock("../api/client");

function renderPage() {
  return render(
    <MantineProvider>
      <IngestPage />
    </MantineProvider>,
  );
}

beforeEach(() => {
  vi.mocked(client.getOptions).mockResolvedValue({
    chunkings: ["recursive", "fixed"],
    embeddings: ["gemini", "e5"],
    llms: ["gemini"],
    rags: ["naive"],
    retrievers: ["similarity"],
    metrics: ["rouge_l"],
  });
  vi.mocked(client.ingest).mockResolvedValue({
    collections: ["viagem__recursive__gemini"],
    total_chunks: 12,
  });
});

describe("IngestPage", () => {
  it("loads options and shows the base name field", async () => {
    renderPage();
    expect(await screen.findByLabelText(/nome da base/i)).toBeInTheDocument();
  });

  it("submits the ingestion and shows the result", async () => {
    renderPage();
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText(/nome da base/i), "viagem");
    await user.click(screen.getByRole("button", { name: /inserir/i }));
    await waitFor(() => expect(client.ingest).toHaveBeenCalled());
    expect(await screen.findByText(/12/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd frontend && npm run test -- --run src/pages/IngestPage.test.tsx`
Expected: FAIL — `./IngestPage` não existe.

- [ ] **Step 3: Implementar a página**

`frontend/src/pages/IngestPage.tsx`:

```tsx
import {
  Alert,
  Button,
  FileInput,
  MultiSelect,
  Stack,
  TextInput,
  Title,
} from "@mantine/core";
import { useEffect, useState } from "react";

import { getOptions, ingest } from "../api/client";
import type { IngestResult, Options } from "../api/types";

export function IngestPage() {
  const [options, setOptions] = useState<Options | null>(null);
  const [base, setBase] = useState("");
  const [chunkings, setChunkings] = useState<string[]>([]);
  const [embeddings, setEmbeddings] = useState<string[]>([]);
  const [files, setFiles] = useState<File[]>([]);
  const [result, setResult] = useState<IngestResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    getOptions().then(setOptions).catch((e) => setError(String(e)));
  }, []);

  async function submit() {
    setError(null);
    setLoading(true);
    try {
      const form = new FormData();
      form.append("base", base);
      form.append("chunkings", chunkings.join(","));
      form.append("embeddings", embeddings.join(","));
      files.forEach((file) => form.append("files", file));
      setResult(await ingest(form));
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <Stack maw={640}>
      <Title order={2}>Inserir documentos</Title>
      <TextInput
        label="Nome da base"
        value={base}
        onChange={(e) => setBase(e.currentTarget.value)}
      />
      <MultiSelect
        label="Técnicas de corte"
        data={options?.chunkings ?? []}
        value={chunkings}
        onChange={setChunkings}
      />
      <MultiSelect
        label="Modelos de embedding"
        data={options?.embeddings ?? []}
        value={embeddings}
        onChange={setEmbeddings}
      />
      <FileInput
        label="Documentos (.txt / .md)"
        multiple
        value={files}
        onChange={setFiles}
      />
      <Button onClick={submit} loading={loading}>
        Inserir
      </Button>
      {result && (
        <Alert color="green" title="Inserção concluída">
          {result.total_chunks} trechos em {result.collections.length} coleção(ões).
        </Alert>
      )}
      {error && (
        <Alert color="red" title="Erro">
          {error}
        </Alert>
      )}
    </Stack>
  );
}
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd frontend && npm run test -- --run src/pages/IngestPage.test.tsx`
Expected: PASS (2 testes). Suíte inteira do front verde.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/IngestPage.tsx frontend/src/pages/IngestPage.test.tsx
git commit -m "feat: ingest documents screen"
```

---

### Task 4: Tela de gerar teste de qualidade (com polling)

**Files:**
- Create: `frontend/src/pages/ExperimentPage.tsx`
- Create: `frontend/src/pages/ExperimentPage.test.tsx`

**Interfaces:**
- Consumes: `getOptions`, `createExperiment`, `getExperiment` de `../api/client`.
- Produces: `ExperimentPage` — `TextInput` nome (opcional) e base, `MultiSelect` de chunkings/embeddings/rags/retrievers/metrics, `FileInput` do CSV; ao submeter monta `config` (JSON) + arquivo `questions`, chama `createExperiment`, faz polling de `getExperiment` até `done`/`failed` e mostra o status; quando `done`, exibe um link/aviso para ver resultados (a navegação completa entra na Task 5).

- [ ] **Step 1: Escrever o teste que falha**

`frontend/src/pages/ExperimentPage.test.tsx`:

```tsx
import { MantineProvider } from "@mantine/core";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as client from "../api/client";
import { ExperimentPage } from "./ExperimentPage";

vi.mock("../api/client");

function renderPage() {
  return render(
    <MantineProvider>
      <ExperimentPage />
    </MantineProvider>,
  );
}

beforeEach(() => {
  vi.mocked(client.getOptions).mockResolvedValue({
    chunkings: ["recursive"],
    embeddings: ["gemini"],
    llms: ["gemini"],
    rags: ["naive"],
    retrievers: ["similarity"],
    metrics: ["answer_relevancy"],
  });
  vi.mocked(client.createExperiment).mockResolvedValue({ id: 7, name: "kind-ember-89", status: "pending" });
  vi.mocked(client.getExperiment).mockResolvedValue({ id: 7, name: "kind-ember-89", status: "done", results: [] });
});

describe("ExperimentPage", () => {
  it("creates an experiment and polls until done", async () => {
    renderPage();
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText(/base/i), "viagem");
    await user.click(screen.getByRole("button", { name: /gerar/i }));
    await waitFor(() => expect(client.createExperiment).toHaveBeenCalled());
    expect(await screen.findByText(/done/i)).toBeInTheDocument();
    expect(await screen.findByText(/kind-ember-89/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd frontend && npm run test -- --run src/pages/ExperimentPage.test.tsx`
Expected: FAIL — `./ExperimentPage` não existe.

- [ ] **Step 3: Implementar a página**

`frontend/src/pages/ExperimentPage.tsx`:

```tsx
import {
  Alert,
  Button,
  FileInput,
  Group,
  MultiSelect,
  Stack,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { useEffect, useRef, useState } from "react";

import { createExperiment, getExperiment, getOptions } from "../api/client";
import type { ExperimentDetail, Options } from "../api/types";

const POLL_INTERVAL_MS = 2000;

export function ExperimentPage() {
  const [options, setOptions] = useState<Options | null>(null);
  const [name, setName] = useState("");
  const [base, setBase] = useState("");
  const [chunkings, setChunkings] = useState<string[]>([]);
  const [embeddings, setEmbeddings] = useState<string[]>([]);
  const [rags, setRags] = useState<string[]>([]);
  const [retrievers, setRetrievers] = useState<string[]>([]);
  const [metrics, setMetrics] = useState<string[]>([]);
  const [csv, setCsv] = useState<File | null>(null);
  const [experiment, setExperiment] = useState<ExperimentDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<number | null>(null);

  useEffect(() => {
    getOptions().then(setOptions).catch((e) => setError(String(e)));
    return () => {
      if (timer.current) window.clearTimeout(timer.current);
    };
  }, []);

  function poll(id: number) {
    getExperiment(id)
      .then((detail) => {
        setExperiment(detail);
        if (detail.status !== "done" && detail.status !== "failed") {
          timer.current = window.setTimeout(() => poll(id), POLL_INTERVAL_MS);
        }
      })
      .catch((e) => setError(String(e)));
  }

  async function submit() {
    setError(null);
    try {
      const config = {
        name: name || undefined,
        base,
        chunkings,
        embeddings,
        rags,
        retrievers,
        metrics,
      };
      const form = new FormData();
      form.append("config", JSON.stringify(config));
      if (csv) form.append("questions", csv);
      const ref = await createExperiment(form);
      setExperiment({ id: ref.id, name: ref.name, status: ref.status, results: [] });
      poll(ref.id);
    } catch (e) {
      setError(String(e));
    }
  }

  return (
    <Stack maw={720}>
      <Title order={2}>Gerar teste de qualidade</Title>
      <TextInput label="Nome do experimento (opcional)" value={name} onChange={(e) => setName(e.currentTarget.value)} />
      <TextInput label="Base" value={base} onChange={(e) => setBase(e.currentTarget.value)} />
      <Group grow>
        <MultiSelect label="Cortes" data={options?.chunkings ?? []} value={chunkings} onChange={setChunkings} />
        <MultiSelect label="Embeddings" data={options?.embeddings ?? []} value={embeddings} onChange={setEmbeddings} />
      </Group>
      <Group grow>
        <MultiSelect label="RAGs" data={options?.rags ?? []} value={rags} onChange={setRags} />
        <MultiSelect label="Retrievers" data={options?.retrievers ?? []} value={retrievers} onChange={setRetrievers} />
      </Group>
      <MultiSelect label="Métricas" data={options?.metrics ?? []} value={metrics} onChange={setMetrics} />
      <FileInput label="Perguntas (CSV)" value={csv} onChange={setCsv} />
      <Button onClick={submit}>Gerar</Button>
      {experiment && (
        <Alert color={experiment.status === "done" ? "green" : "blue"} title={experiment.name}>
          <Text>Status: {experiment.status}</Text>
        </Alert>
      )}
      {error && (
        <Alert color="red" title="Erro">
          {error}
        </Alert>
      )}
    </Stack>
  );
}
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd frontend && npm run test -- --run src/pages/ExperimentPage.test.tsx`
Expected: PASS (1 teste — o mock de `getExperiment` retorna `done` na primeira chamada, encerrando o polling). Suíte inteira do front verde.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/ExperimentPage.tsx frontend/src/pages/ExperimentPage.test.tsx
git commit -m "feat: quality test screen with polling"
```

---

### Task 5: Tela de resultados + navegação

**Files:**
- Create: `frontend/src/pages/ResultsPage.tsx`
- Create: `frontend/src/pages/ResultsPage.test.tsx`
- Modify: `frontend/src/App.tsx` (AppShell + NavLinks + Routes)

**Interfaces:**
- Consumes: `listExperiments`, `getExperiment` de `../api/client`.
- Produces:
  - `ResultsPage` — lista experimentos num `Select`, ao escolher carrega o detalhe e mostra uma `Table` limpa (combinação, pergunta, resposta resumida, scores resumidos); clicar numa linha alterna um painel/`Collapse` com a resposta completa, todos os scores, latência e tokens.
  - `App` — `AppShell` com `NavLink`s ("Inserir documentos", "Gerar teste", "Resultados") e `Routes` para `/`, `/experiment`, `/results`.

- [ ] **Step 1: Escrever o teste que falha**

`frontend/src/pages/ResultsPage.test.tsx`:

```tsx
import { MantineProvider } from "@mantine/core";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as client from "../api/client";
import { ResultsPage } from "./ResultsPage";

vi.mock("../api/client");

function renderPage() {
  return render(
    <MantineProvider>
      <ResultsPage />
    </MantineProvider>,
  );
}

beforeEach(() => {
  vi.mocked(client.listExperiments).mockResolvedValue([
    { id: 7, name: "kind-ember-89", status: "done" },
  ]);
  vi.mocked(client.getExperiment).mockResolvedValue({
    id: 7,
    name: "kind-ember-89",
    status: "done",
    results: [
      {
        chunking: "recursive",
        embedding: "gemini",
        rag: "naive",
        retriever: "similarity",
        question: "Onde fica o centro?",
        answer: "Na Praça da Matriz, segundo o guia da cidade.",
        scores: { answer_relevancy: 0.66, faithfulness: 0.75 },
        latency_ms: 14000,
        tokens: 25,
      },
    ],
  });
});

describe("ResultsPage", () => {
  it("loads an experiment and shows its results, expanding a row on click", async () => {
    renderPage();
    const user = userEvent.setup();
    // first experiment auto-selected or chosen
    const row = await screen.findByText(/Onde fica o centro/);
    await user.click(row);
    expect(await screen.findByText(/Praça da Matriz/)).toBeInTheDocument();
    expect(screen.getByText(/14000/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd frontend && npm run test -- --run src/pages/ResultsPage.test.tsx`
Expected: FAIL — `./ResultsPage` não existe.

- [ ] **Step 3: Implementar a página de resultados**

`frontend/src/pages/ResultsPage.tsx`:

```tsx
import { Collapse, Select, Stack, Table, Text, Title } from "@mantine/core";
import { Fragment, useEffect, useState } from "react";

import { getExperiment, listExperiments } from "../api/client";
import type { ExperimentDetail, ExperimentSummary } from "../api/types";

function summarizeScores(scores: Record<string, number>): string {
  return Object.entries(scores)
    .map(([key, value]) => `${key}: ${value.toFixed(2)}`)
    .join(" · ");
}

export function ResultsPage() {
  const [experiments, setExperiments] = useState<ExperimentSummary[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<ExperimentDetail | null>(null);
  const [openRow, setOpenRow] = useState<number | null>(null);

  useEffect(() => {
    listExperiments().then((rows) => {
      setExperiments(rows);
      if (rows.length > 0) setSelected(String(rows[0].id));
    });
  }, []);

  useEffect(() => {
    if (selected) getExperiment(Number(selected)).then(setDetail);
  }, [selected]);

  return (
    <Stack>
      <Title order={2}>Resultados</Title>
      <Select
        label="Experimento"
        data={experiments.map((e) => ({ value: String(e.id), label: `${e.name} (${e.status})` }))}
        value={selected}
        onChange={setSelected}
        maw={360}
      />
      {detail && (
        <Table highlightOnHover withTableBorder>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Combinação</Table.Th>
              <Table.Th>Pergunta</Table.Th>
              <Table.Th>Resposta</Table.Th>
              <Table.Th>Scores</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {detail.results.map((row, index) => (
              <Fragment key={index}>
                <Table.Tr
                  onClick={() => setOpenRow(openRow === index ? null : index)}
                  style={{ cursor: "pointer" }}
                >
                  <Table.Td>{`${row.chunking}/${row.embedding}/${row.rag}/${row.retriever}`}</Table.Td>
                  <Table.Td>{row.question}</Table.Td>
                  <Table.Td>{row.answer.slice(0, 60)}…</Table.Td>
                  <Table.Td>{summarizeScores(row.scores)}</Table.Td>
                </Table.Tr>
                <Table.Tr>
                  <Table.Td colSpan={4} p={0} style={{ border: 0 }}>
                    <Collapse in={openRow === index}>
                      <Stack p="md" gap="xs">
                        <Text fw={600}>Resposta completa</Text>
                        <Text>{row.answer}</Text>
                        <Text size="sm" c="dimmed">
                          {summarizeScores(row.scores)} · latência: {row.latency_ms} ms · tokens: {row.tokens}
                        </Text>
                      </Stack>
                    </Collapse>
                  </Table.Td>
                </Table.Tr>
              </Fragment>
            ))}
          </Table.Tbody>
        </Table>
      )}
    </Stack>
  );
}
```

- [ ] **Step 4: Implementar a navegação no `App.tsx`**

`frontend/src/App.tsx`:

```tsx
import { AppShell, NavLink, Title } from "@mantine/core";
import { Link, Route, Routes, useLocation } from "react-router-dom";

import { ExperimentPage } from "./pages/ExperimentPage";
import { IngestPage } from "./pages/IngestPage";
import { ResultsPage } from "./pages/ResultsPage";

const NAV = [
  { to: "/", label: "Inserir documentos" },
  { to: "/experiment", label: "Gerar teste" },
  { to: "/results", label: "Resultados" },
];

export function App() {
  const location = useLocation();
  return (
    <AppShell navbar={{ width: 220, breakpoint: "sm" }} padding="md">
      <AppShell.Navbar p="md">
        <Title order={4} mb="md">
          Ditto
        </Title>
        {NAV.map((item) => (
          <NavLink
            key={item.to}
            component={Link}
            to={item.to}
            label={item.label}
            active={location.pathname === item.to}
          />
        ))}
      </AppShell.Navbar>
      <AppShell.Main>
        <Routes>
          <Route path="/" element={<IngestPage />} />
          <Route path="/experiment" element={<ExperimentPage />} />
          <Route path="/results" element={<ResultsPage />} />
        </Routes>
      </AppShell.Main>
    </AppShell>
  );
}
```

- [ ] **Step 5: Rodar e ver passar; validar o build**

Run: `cd frontend && npm run test -- --run`
Expected: PASS (todos os testes do front: cliente + 3 páginas).
Run: `cd frontend && npm run build`
Expected: build conclui sem erros de tipo.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/ResultsPage.tsx frontend/src/pages/ResultsPage.test.tsx frontend/src/App.tsx
git commit -m "feat: results screen with expandable rows and app navigation"
```

---

## Self-Review

**Spec coverage (Plano 7 cobre spec §10 — frontend, 3 telas):**
- Tela de inserir documentos (upload + base + chunkings + embeddings → /ingest) (spec §10) → Task 3. ✅
- Tela de gerar teste (seleção de combinações + métricas + CSV + nome opcional → /experiments, com polling) (spec §10) → Task 4. ✅
- Tela de visualização de resultados (tabela limpa + expandir linha com dados completos) (spec §10) → Task 5. ✅
- React + Vite + Mantine, leve; container Nginx no compose (spec §10, §11) → Task 2. ✅
- `/options` estendido para alimentar os seletores de rags/retrievers/metrics (pré-requisito) → Task 1. ✅
- Sem CORS: Nginx faz proxy de `/api/` → `api:8000` → Task 2. ✅

**Placeholder scan:** sem TBD/TODO; todos os passos com código/comando concreto. ✅

**Type consistency:**
- Tipos da API (`Options`, `IngestResult`, `ExperimentRef`, `ExperimentDetail`, `ExperimentResultRow`, `ExperimentSummary`) consistentes entre `types.ts`, `client.ts` e as páginas. ✅
- `getOptions/ingest/createExperiment/getExperiment/listExperiments` consistentes entre cliente, testes e páginas. ✅
- Campos de `ExperimentResultRow` (chunking/embedding/rag/retriever/question/answer/scores/latency_ms/tokens) batem com o JSON do `GET /experiments/{id}` do Plano 6. ✅
- `config` enviado pelo ExperimentPage (base, chunkings, embeddings, rags, retrievers, metrics, name?) bate com `ExperimentConfig` do Plano 6. ✅
- Testes mockam `../api/client` (componentes) e `fetch` (cliente) → sem backend. ✅

**Escopo:** só as 3 telas + navegação + cliente + infra. Sem chat (Fatia B), sem autenticação, sem gráficos avançados. Mantine cobre a UI sem CSS custom. Sem over-build. ✅
