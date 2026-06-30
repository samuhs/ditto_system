# Preencher Tudo + Resultados Agrupados — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adicionar botão "Preencher tudo / Limpar tudo" nas telas de Ingestão e Experimento, e redesenhar a tela de Resultados com lista clicável de experimentos + painel de detalhe fixo no topo.

**Architecture:** Todas as mudanças são frontend-only — o backend já suporta múltiplas seleções e roda o produto cartesiano de combinações. As três páginas são modificadas in-place; nenhum componente novo é extraído. CSS novo é adicionado ao `global.css` existente.

**Tech Stack:** React + TypeScript, Mantine v7 (`Button`, `ActionIcon`, `Loader`, `Collapse`, `Alert`), `@testing-library/react` + `userEvent` + `vitest`.

## Global Constraints

- Identificadores e comentários em inglês; textos de UI em PT-BR.
- Testes não tocam rede — todo acesso à API é mockado via `vi.mock("../api/client")`.
- Seguir padrões existentes: `ditto-glass` para cards, `ditto-chip` para badges de status, `ditto-mono` para textos monospace.
- Rodar testes com: `cd frontend && npm run test -- --run`

---

## Mapa de arquivos

| Arquivo | Ação |
|---------|------|
| `frontend/src/pages/IngestPage.tsx` | Modificar — adicionar lógica e botão "Preencher tudo" |
| `frontend/src/pages/IngestPage.test.tsx` | Modificar — adicionar teste do botão |
| `frontend/src/pages/ExperimentPage.tsx` | Modificar — adicionar lógica e botão "Preencher tudo" (5 campos) |
| `frontend/src/pages/ExperimentPage.test.tsx` | Modificar — adicionar teste do botão |
| `frontend/src/pages/ResultsPage.tsx` | Modificar — substituir Select por lista + painel de detalhe |
| `frontend/src/pages/ResultsPage.test.tsx` | Modificar — reescrever testes para o novo fluxo |
| `frontend/src/styles/global.css` | Modificar — adicionar `.ditto-exp-list` e `.ditto-exp-row`; corrigir variáveis de fonte |

---

## Task 1: Botão "Preencher tudo" no IngestPage

**Files:**
- Modify: `frontend/src/pages/IngestPage.tsx`
- Modify: `frontend/src/pages/IngestPage.test.tsx`
- Modify: `frontend/src/styles/global.css` (corrigir `--font-body` e `--font-display`)

**Interfaces:**
- Produces: botão com `role="button"` e nome acessível `/preencher tudo/i` ou `/limpar tudo/i`, dependendo do estado

- [ ] **Step 1: Escrever o teste que falha**

Em `frontend/src/pages/IngestPage.test.tsx`, adicionar dentro do `describe("IngestPage")`:

```tsx
it("fills all fields when 'Preencher tudo' is clicked and shows 'Limpar tudo'; clears on second click", async () => {
  renderPage();
  const user = userEvent.setup();
  // Button appears disabled until options load, then enabled
  const fillBtn = await screen.findByRole("button", { name: /preencher tudo/i });
  expect(fillBtn).toBeEnabled();
  await user.click(fillBtn);
  // After fill, button label changes
  expect(screen.getByRole("button", { name: /limpar tudo/i })).toBeInTheDocument();
  // Click again to clear
  await user.click(screen.getByRole("button", { name: /limpar tudo/i }));
  expect(screen.getByRole("button", { name: /preencher tudo/i })).toBeInTheDocument();
});
```

- [ ] **Step 2: Verificar que o teste falha**

```bash
cd frontend && npm run test -- --run src/pages/IngestPage.test.tsx
```

Esperado: FAIL — "Unable to find an accessible element with the role 'button' and name /preencher tudo/i"

- [ ] **Step 3: Implementar o botão em IngestPage.tsx**

Adicionar ao bloco de importações do Mantine (já existente) o `Button` que já está importado — não precisa mudar imports.

Adicionar a lógica derivada e a função `toggleAll` após a declaração dos estados (antes do `useEffect`):

```tsx
// Derived: true when every available option is selected in both fields
const allFilled =
  options !== null &&
  options.chunkings.length > 0 &&
  options.embeddings.length > 0 &&
  chunkings.length === options.chunkings.length &&
  embeddings.length === options.embeddings.length;

function toggleAll() {
  if (allFilled) {
    setChunkings([]);
    setEmbeddings([]);
  } else {
    setChunkings(options?.chunkings ?? []);
    setEmbeddings(options?.embeddings ?? []);
  }
}
```

No JSX, dentro do `<div className="ditto-glass">`, antes do `<TextInput label="Nome da base">`, adicionar:

```tsx
<Group justify="flex-end">
  <Button
    variant="subtle"
    size="xs"
    disabled={options === null}
    color={allFilled ? "gray" : "violet"}
    onClick={toggleAll}
  >
    {allFilled ? "Limpar tudo" : "Preencher tudo"}
  </Button>
</Group>
```

- [ ] **Step 4: Corrigir variáveis de fonte em global.css**

Em `frontend/src/styles/global.css`, substituir as linhas de variáveis de fonte dentro de `:root`:

```css
/* antes */
--font-display: "Syne", "Hanken Grotesk", system-ui, sans-serif;
--font-body: "Hanken Grotesk", system-ui, sans-serif;

/* depois */
--font-display: "Plus Jakarta Sans", system-ui, sans-serif;
--font-body: "Montserrat", system-ui, sans-serif;
```

- [ ] **Step 5: Verificar que o teste passa**

```bash
cd frontend && npm run test -- --run src/pages/IngestPage.test.tsx
```

Esperado: todos os testes PASS (2 existentes + 1 novo = 3 total)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/IngestPage.tsx frontend/src/pages/IngestPage.test.tsx frontend/src/styles/global.css
git commit -m "feat: botão preencher/limpar tudo na IngestPage"
```

---

## Task 2: Botão "Preencher tudo" no ExperimentPage

**Files:**
- Modify: `frontend/src/pages/ExperimentPage.tsx`
- Modify: `frontend/src/pages/ExperimentPage.test.tsx`

**Interfaces:**
- Produces: botão com `role="button"` e nome `/preencher tudo/i` ou `/limpar tudo/i`
- Consumes: `options.chunkings`, `options.embeddings`, `options.rags`, `options.retrievers`, `options.metrics`

- [ ] **Step 1: Escrever o teste que falha**

Em `frontend/src/pages/ExperimentPage.test.tsx`, adicionar dentro do `describe("ExperimentPage")`:

```tsx
it("fills all 5 fields when 'Preencher tudo' is clicked and clears on 'Limpar tudo'", async () => {
  renderPage();
  const user = userEvent.setup();
  const fillBtn = await screen.findByRole("button", { name: /preencher tudo/i });
  expect(fillBtn).toBeEnabled();
  await user.click(fillBtn);
  expect(screen.getByRole("button", { name: /limpar tudo/i })).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: /limpar tudo/i }));
  expect(screen.getByRole("button", { name: /preencher tudo/i })).toBeInTheDocument();
});
```

- [ ] **Step 2: Verificar que o teste falha**

```bash
cd frontend && npm run test -- --run src/pages/ExperimentPage.test.tsx
```

Esperado: FAIL — "Unable to find an accessible element with the role 'button' and name /preencher tudo/i"

- [ ] **Step 3: Implementar o botão em ExperimentPage.tsx**

Adicionar lógica derivada e `toggleAll` após a declaração dos estados, antes do `useEffect`:

```tsx
const allFilled =
  options !== null &&
  options.chunkings.length > 0 &&
  chunkings.length === options.chunkings.length &&
  embeddings.length === options.embeddings.length &&
  rags.length === options.rags.length &&
  retrievers.length === options.retrievers.length &&
  metrics.length === options.metrics.length;

function toggleAll() {
  if (allFilled) {
    setChunkings([]);
    setEmbeddings([]);
    setRags([]);
    setRetrievers([]);
    setMetrics([]);
  } else {
    setChunkings(options?.chunkings ?? []);
    setEmbeddings(options?.embeddings ?? []);
    setRags(options?.rags ?? []);
    setRetrievers(options?.retrievers ?? []);
    setMetrics(options?.metrics ?? []);
  }
}
```

No JSX, dentro do `<div className="ditto-glass">`, dentro do `<Stack gap="lg">`, como **primeiro filho**:

```tsx
<Group justify="flex-end">
  <Button
    variant="subtle"
    size="xs"
    disabled={options === null}
    color={allFilled ? "gray" : "violet"}
    onClick={toggleAll}
  >
    {allFilled ? "Limpar tudo" : "Preencher tudo"}
  </Button>
</Group>
```

- [ ] **Step 4: Verificar que o teste passa**

```bash
cd frontend && npm run test -- --run src/pages/ExperimentPage.test.tsx
```

Esperado: todos os testes PASS (1 existente + 1 novo = 2 total)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/ExperimentPage.tsx frontend/src/pages/ExperimentPage.test.tsx
git commit -m "feat: botão preencher/limpar tudo na ExperimentPage"
```

---

## Task 3: ResultsPage — lista clicável + painel de detalhe

**Files:**
- Modify: `frontend/src/pages/ResultsPage.tsx`
- Modify: `frontend/src/pages/ResultsPage.test.tsx`
- Modify: `frontend/src/styles/global.css`

**Interfaces:**
- Consumes: `listExperiments()` → `ExperimentSummary[]`, `getExperiment(id)` → `ExperimentDetail`
- Produces:
  - Lista de experimentos: `button.ditto-exp-row` com `data-selected="true/false"`
  - Painel de detalhe: `aria-label="Fechar painel"` no botão de fechar
  - Tabela de resultados (igual à existente, mas dentro do painel)

- [ ] **Step 1: Adicionar CSS para a lista de experimentos em global.css**

Adicionar ao final de `frontend/src/styles/global.css` (antes do bloco `@media prefers-reduced-motion`):

```css
/* Experiment list */
.ditto-exp-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.ditto-exp-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 20px;
  background: var(--surface);
  border: 1px solid var(--stroke);
  border-left: 3px solid transparent;
  border-radius: var(--radius-md);
  cursor: pointer;
  text-align: left;
  width: 100%;
  color: var(--text-hi);
  font-family: inherit;
  transition: background 0.15s, border-color 0.15s;
}

.ditto-exp-row:hover {
  background: var(--surface-strong);
  border-color: var(--stroke-strong);
}

.ditto-exp-row[data-selected="true"] {
  border-left-color: var(--ditto-purple);
  background: var(--surface-strong);
}
```

- [ ] **Step 2: Escrever os testes que falham**

Substituir o conteúdo inteiro de `frontend/src/pages/ResultsPage.test.tsx` por:

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
    { id: 8, name: "swift-fox-12", status: "pending" },
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
  it("shows experiment list without detail panel on load", async () => {
    renderPage();
    expect(await screen.findByText("kind-ember-89")).toBeInTheDocument();
    expect(screen.getByText("swift-fox-12")).toBeInTheDocument();
    expect(screen.queryByLabelText(/fechar painel/i)).not.toBeInTheDocument();
  });

  it("opens detail panel and loads results when experiment is clicked", async () => {
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByText("kind-ember-89"));
    expect(await screen.findByLabelText(/fechar painel/i)).toBeInTheDocument();
    expect(await screen.findByText(/Onde fica o centro/)).toBeInTheDocument();
  });

  it("closes detail panel when X button is clicked", async () => {
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByText("kind-ember-89"));
    await screen.findByLabelText(/fechar painel/i);
    await user.click(screen.getByLabelText(/fechar painel/i));
    expect(screen.queryByLabelText(/fechar painel/i)).not.toBeInTheDocument();
  });

  it("expands a result row on click inside the detail panel", async () => {
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByText("kind-ember-89"));
    const row = await screen.findByText(/Onde fica o centro/);
    await user.click(row);
    expect(await screen.findByText(/Praça da Matriz/)).toBeInTheDocument();
    expect(screen.getByText(/14000/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 3: Verificar que os testes falham**

```bash
cd frontend && npm run test -- --run src/pages/ResultsPage.test.tsx
```

Esperado: FAIL — testes não encontram o botão "fechar painel" e a lista de experimentos

- [ ] **Step 4: Reescrever ResultsPage.tsx**

Substituir o conteúdo inteiro de `frontend/src/pages/ResultsPage.tsx` por:

```tsx
import { ActionIcon, Alert, Collapse, Group, Loader, Text } from "@mantine/core";
import { Fragment, useEffect, useState } from "react";

import { getExperiment, listExperiments } from "../api/client";
import type { ExperimentDetail, ExperimentSummary } from "../api/types";
import { PageHeader } from "../components/PageHeader";

function statusColor(status: string): string {
  if (status === "done") return "#07f285";
  if (status === "failed") return "#f26dcf";
  return "#05dbf2";
}

function scoreColor(value: number): string {
  if (value >= 0.7) return "#07f285";
  if (value >= 0.45) return "#05dbf2";
  if (value >= 0.25) return "#f2ec91";
  return "#f26dcf";
}

function truncateAnswer(answer: string, max = 60): string {
  return answer.length > max ? `${answer.slice(0, max)}…` : answer;
}

export function ResultsPage() {
  const [experiments, setExperiments] = useState<ExperimentSummary[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<ExperimentDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [openRow, setOpenRow] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listExperiments()
      .then(setExperiments)
      .catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    if (selectedId === null) return;
    setDetailLoading(true);
    setDetail(null);
    setDetailError(null);
    setOpenRow(null);
    getExperiment(selectedId)
      .then(setDetail)
      .catch((e) => setDetailError(String(e)))
      .finally(() => setDetailLoading(false));
  }, [selectedId]);

  function closeDetail() {
    setSelectedId(null);
    setDetail(null);
    setDetailError(null);
    setOpenRow(null);
  }

  return (
    <div>
      <PageHeader
        eyebrow="Passo 03 · Ranquear"
        title="Resultados"
        subtitle="Clique num experimento para ver seus resultados. As barras coloridas mostram a qualidade de cada métrica — verde é bom, rosa pede atenção."
      />

      {error && (
        <Alert color="red" variant="light" title="Erro" mb="lg" radius="lg" maw={760}>
          {error}
        </Alert>
      )}

      {/* Detail panel — appears above list when an experiment is selected */}
      {selectedId !== null && (
        <div
          className="ditto-glass"
          style={{
            padding: "22px 26px",
            maxWidth: 900,
            marginBottom: 24,
            borderColor: detail ? statusColor(detail.status) : "var(--stroke)",
          }}
        >
          <Group justify="space-between" align="center" mb={16}>
            <div>
              <Text className="ditto-mono" size="xs" c="dimmed">
                EXPERIMENTO
              </Text>
              {detail && (
                <Group gap="xs" align="center" mt={4}>
                  <Text fw={700} fz="lg">
                    {detail.name}
                  </Text>
                  <span
                    className="ditto-chip"
                    style={{ color: statusColor(detail.status) }}
                  >
                    {detail.status}
                  </span>
                </Group>
              )}
            </div>
            <ActionIcon
              variant="subtle"
              color="gray"
              size="lg"
              onClick={closeDetail}
              aria-label="Fechar painel"
            >
              ✕
            </ActionIcon>
          </Group>

          {detailLoading && (
            <div style={{ display: "flex", justifyContent: "center", padding: "32px 0" }}>
              <Loader size="md" color="#05dbf2" />
            </div>
          )}

          {detailError && (
            <Alert color="red" variant="light" title="Erro ao carregar" radius="lg">
              {detailError}
            </Alert>
          )}

          {detail && (
            <div className="ditto-table-wrap">
              <table>
                <thead>
                  <tr>
                    <th style={{ width: "26%" }}>Combinação</th>
                    <th style={{ width: "26%" }}>Pergunta</th>
                    <th style={{ width: "26%" }}>Resposta</th>
                    <th style={{ width: "22%" }}>Scores</th>
                  </tr>
                </thead>
                <tbody>
                  {detail.results.length === 0 && (
                    <tr>
                      <td colSpan={4} className="ditto-empty">
                        {detail.status === "done"
                          ? "Nenhum resultado para este experimento."
                          : "Experimento em andamento..."}
                      </td>
                    </tr>
                  )}
                  {detail.results.map((row, index) => {
                    const open = openRow === index;
                    return (
                      <Fragment key={index}>
                        <tr
                          className="ditto-row"
                          data-open={open}
                          onClick={() => setOpenRow(open ? null : index)}
                        >
                          <td>
                            <div className="ditto-combo">
                              <span>{row.chunking}</span>
                              <span>{row.embedding}</span>
                              <span>{row.rag}</span>
                              <span>{row.retriever}</span>
                            </div>
                          </td>
                          <td>{row.question}</td>
                          <td>{open ? null : truncateAnswer(row.answer)}</td>
                          <td>
                            <div className="ditto-scores-mini">
                              {Object.entries(row.scores).map(([key, value]) => (
                                <span key={key} className="ditto-score-pill">
                                  <span
                                    className="ditto-score-dot"
                                    style={{ background: scoreColor(value) }}
                                  />
                                  {value.toFixed(2)}
                                </span>
                              ))}
                            </div>
                          </td>
                        </tr>
                        <tr>
                          <td colSpan={4} style={{ padding: 0, borderBottom: 0 }}>
                            <Collapse in={open}>
                              {open && (
                                <div className="ditto-expand">
                                  <Text className="ditto-eyebrow" mb={6}>
                                    Resposta completa
                                  </Text>
                                  <Text mb="md" style={{ lineHeight: 1.6 }}>
                                    {row.answer}
                                  </Text>
                                  {Object.entries(row.scores).map(([key, value]) => (
                                    <div key={key} className="ditto-score-bar-row">
                                      <span className="ditto-score-bar-label">{key}</span>
                                      <span className="ditto-score-bar-track">
                                        <span
                                          className="ditto-score-bar-fill"
                                          style={{
                                            width: `${Math.max(0, Math.min(1, value)) * 100}%`,
                                            background: scoreColor(value),
                                            boxShadow: `0 0 12px ${scoreColor(value)}`,
                                          }}
                                        />
                                      </span>
                                      <span className="ditto-score-bar-val">
                                        {value.toFixed(2)}
                                      </span>
                                    </div>
                                  ))}
                                  <div className="ditto-meta-chips">
                                    <span className="ditto-chip" style={{ color: "#05dbf2" }}>
                                      {row.latency_ms} ms
                                    </span>
                                    <span className="ditto-chip" style={{ color: "#f2ec91" }}>
                                      {row.tokens} tokens
                                    </span>
                                  </div>
                                </div>
                              )}
                            </Collapse>
                          </td>
                        </tr>
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Experiment list */}
      <div className="ditto-exp-list" style={{ maxWidth: 900 }}>
        {experiments.length === 0 && !error && (
          <p className="ditto-empty">Nenhum experimento encontrado.</p>
        )}
        {experiments.map((exp) => (
          <button
            key={exp.id}
            className="ditto-exp-row"
            data-selected={selectedId === exp.id}
            onClick={() => setSelectedId(exp.id)}
          >
            <Text fw={600} fz="sm">
              {exp.name}
            </Text>
            <span className="ditto-chip" style={{ color: statusColor(exp.status) }}>
              {exp.status}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Verificar que os testes passam**

```bash
cd frontend && npm run test -- --run src/pages/ResultsPage.test.tsx
```

Esperado: 4 testes PASS

- [ ] **Step 6: Rodar toda a suite**

```bash
cd frontend && npm run test -- --run
```

Esperado: todos os testes PASS (sem regressões)

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/ResultsPage.tsx frontend/src/pages/ResultsPage.test.tsx frontend/src/styles/global.css
git commit -m "feat: resultados agrupados com painel de detalhe e lista de experimentos"
```

---

## Verificação final

Após todos os commits, fazer o build e confirmar visualmente:

```bash
make front-build && docker compose up -d --build frontend
```

Checar:
- [ ] IngestPage: botão "Preencher tudo" seleciona corte e embedding; muda para "Limpar tudo"; limpar zera os campos
- [ ] ExperimentPage: mesmo comportamento para 5 campos (cortes, embeddings, RAGs, retrievers, métricas)
- [ ] ResultsPage: lista de experimentos visível sem painel; clicar abre painel no topo com loader → resultados; ✕ fecha o painel; experimento selecionado fica destacado na lista
