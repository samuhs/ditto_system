# LLM como dimensão da matriz de experimentos — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tornar o LLM uma dimensão da matriz de experimentos (chunking × embedding × rag × retriever × llm), selecionável no formulário e exibível/filtrável nos resultados.

**Architecture:** `ExperimentConfig.llm` (str) vira `llms` (list); `ExperimentRun` ganha coluna `llm`; o orquestrador inclui `config.llms` no `itertools.product` e constrói o LLM por combinação; a API GET devolve `llm` por linha e conta os LLMs no progresso. O formulário ganha um MultiSelect "LLMs" e a tela de detalhe ganha coluna + filtro de LLM.

**Tech Stack:** Python 3.13 (venv `backend/.venv`), pytest; React + Vite + TS + Mantine, vitest.

## Global Constraints

- Identificadores/classes/docstrings/erros em **inglês**; UI em **PT-BR**.
- `ExperimentConfig.llms: list[str] = ["gemini"]` (default preserva compatibilidade); `eval_embedding` continua singular (fora de escopo).
- `ExperimentRun.llm: Mapped[str | None] = mapped_column(String(60), nullable=True)` (runs antigos ficam NULL).
- Orquestrador: LLM construído **por combinação** (`deps.llm_factory(llm_name)` dentro do loop); `ExperimentRun.llm = llm_name`.
- API GET: linha de resultado `"llm": run.llm or "gemini"` (experimentos antigos rodaram todos em gemini → coalescer NULL para "gemini" é historicamente correto e evita null no front); progresso multiplica por `len(cfg.get("llms", [])) or 1`.
- Testes herméticos (sem rede): fakes via `ExperimentDeps` (backend) e mocks do client (frontend).
- **Post-merge deployment (manual, NÃO é task de código):** `ALTER TABLE experiment_run ADD COLUMN IF NOT EXISTS llm VARCHAR(60);` no Postgres deployado.
- Rodar: backend `cd backend && ./.venv/bin/python -m pytest <arquivo> -v`; frontend `cd frontend && npx vitest run <arquivo>`.

---

### Task 1: Backend — LLM como dimensão (schema, modelo, orquestrador, API)

**Files:**
- Modify: `backend/app/experiments/schemas.py` (`ExperimentConfig`)
- Modify: `backend/app/core/db/models.py` (`ExperimentRun`)
- Modify: `backend/app/experiments/orchestrator.py` (loop + build + run)
- Modify: `backend/app/api/experiments.py` (GET: row + progresso)
- Test: `backend/tests/test_experiment_schemas.py`, `backend/tests/test_orchestrator.py`, `backend/tests/test_experiments_api.py`

**Interfaces:**
- Consumes: `ExperimentDeps` (com `llm_factory`), `run_experiment`, `ExperimentConfig`, `QuestionItem`, `ExperimentRun`, `Experiment` — todos já existentes.
- Produces: `ExperimentConfig.llms: list[str]`; `ExperimentRun.llm`; linha de resultado do GET com chave `"llm"`; progresso contando LLMs.

- [ ] **Step 1: Write the failing tests**

Em `backend/tests/test_experiment_schemas.py`, adicionar:

```python
def test_experiment_config_llms_defaults_to_gemini():
    from app.experiments.schemas import ExperimentConfig

    cfg = ExperimentConfig(
        base="viagem", chunkings=["recursive"], embeddings=["gemini"],
        rags=["naive"], retrievers=["similarity"], metrics=["answer_relevancy"],
    )
    assert cfg.llms == ["gemini"]


def test_experiment_config_parses_llms_list():
    from app.experiments.schemas import ExperimentConfig

    cfg = ExperimentConfig(
        base="viagem", chunkings=["recursive"], embeddings=["gemini"],
        rags=["naive"], retrievers=["similarity"], metrics=["answer_relevancy"],
        llms=["gemini", "ollama"],
    )
    assert cfg.llms == ["gemini", "ollama"]
```

Em `backend/tests/test_orchestrator.py`, adicionar (reusa `_FakeEmbedder`/`_FakeLLM`/`_embedder_factory`/`_llm_factory`/`session_factory` do arquivo):

```python
def test_run_experiment_includes_llm_dimension(session_factory):
    store = QdrantStore(client=QdrantClient(":memory:"))
    ingest_documents(
        [Document(name="a.txt", text="One. Two. Three sentences here.")],
        IngestConfig(base="viagem", chunkings=["recursive"], embeddings=["gemini"]),
        store,
        embedder_factory=_embedder_factory,
    )
    session = session_factory()
    experiment = Experiment(name="llm-dim", status="pending", config={})
    session.add(experiment)
    session.commit()
    experiment_id = experiment.id
    session.close()

    seen_llm_names = []

    def _recording_llm_factory(name, **kwargs):
        seen_llm_names.append(name)
        return _FakeLLM()

    config = ExperimentConfig(
        base="viagem", chunkings=["recursive"], embeddings=["gemini"],
        rags=["naive"], retrievers=["similarity"], metrics=["answer_relevancy"],
        llms=["gemini", "ollama"],
    )
    deps = ExperimentDeps(
        store=store,
        session_factory=session_factory,
        llm_factory=_recording_llm_factory,
        embedder_factory=_embedder_factory,
    )

    run_experiment(experiment_id, config, [QuestionItem(text="q")], deps)

    check = session_factory()
    stored = check.get(Experiment, experiment_id)
    assert len(stored.runs) == 2  # 1*1*1*1*2 llms
    assert {r.llm for r in stored.runs} == {"gemini", "ollama"}
    check.close()
    assert set(seen_llm_names) == {"gemini", "ollama"}
```

Em `backend/tests/test_experiments_api.py`, adicionar:

```python
def test_experiment_records_llm_dimension(client):
    files = {"questions": ("q.csv", io.BytesIO(b"pergunta,resposta_referencia\nWhere?,\n"), "text/csv")}
    config = json.dumps({
        "base": "viagem", "chunkings": ["recursive"], "embeddings": ["gemini"],
        "rags": ["naive"], "retrievers": ["similarity"], "metrics": ["answer_relevancy"],
        "llms": ["gemini", "custom"],
    })
    resp = client.post("/experiments", data={"config": config}, files=files)
    assert resp.status_code == 200
    detail = client.get(f"/experiments/{resp.json()['id']}").json()
    llms_in_rows = {row["llm"] for row in detail["results"]}
    assert llms_in_rows == {"gemini", "custom"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_experiment_schemas.py tests/test_orchestrator.py::test_run_experiment_includes_llm_dimension tests/test_experiments_api.py::test_experiment_records_llm_dimension -v`
Expected: FAIL — `ExperimentConfig` has no `llms`; `run.llm` attribute missing; result rows lack `"llm"`.

- [ ] **Step 3: Update the schema**

Em `backend/app/experiments/schemas.py`, na classe `ExperimentConfig`, trocar a linha `llm: str = "gemini"` por:

```python
    llms: list[str] = ["gemini"]
```

(Manter `eval_embedding: str = "gemini"` inalterado.)

- [ ] **Step 4: Add the model column**

Em `backend/app/core/db/models.py`, na classe `ExperimentRun`, após a linha `retriever: Mapped[str] = mapped_column(String(60))`, adicionar:

```python
    llm: Mapped[str | None] = mapped_column(String(60), nullable=True)
```

- [ ] **Step 5: Update the orchestrator**

Em `backend/app/experiments/orchestrator.py`, dentro de `run_experiment`:

1. Remover a linha (antes do loop):
```python
        llm = deps.llm_factory(config.llm)
```

2. Trocar o cabeçalho do loop:
```python
        for chunking, embedding, rag_name, retriever_name in itertools.product(
            config.chunkings, config.embeddings, config.rags, config.retrievers
        ):
```
por:
```python
        for chunking, embedding, rag_name, retriever_name, llm_name in itertools.product(
            config.chunkings, config.embeddings, config.rags, config.retrievers, config.llms
        ):
```

3. No `ExperimentRun(...)` criado dentro do loop, adicionar `llm=llm_name` (após `retriever=retriever_name,`):
```python
            run = ExperimentRun(
                experiment_id=experiment_id,
                chunking=chunking,
                embedding=embedding,
                rag_technique=rag_name,
                retriever=retriever_name,
                llm=llm_name,
                status="running",
            )
```

4. Logo após a linha `embedder = deps.embedder_factory(embedding)` (dentro do loop), adicionar a construção do LLM por combinação:
```python
            llm = deps.llm_factory(llm_name)
```

- [ ] **Step 6: Update the API GET**

Em `backend/app/api/experiments.py`, na função `get_experiment`:

1. Na montagem da linha de resultado, adicionar a chave `"llm"` (após `"retriever": run.retriever,`):
```python
                        "retriever": run.retriever,
                        "llm": run.llm or "gemini",
```

2. No cálculo do total, adicionar o fator de LLMs:
```python
        n_llms = len(cfg.get("llms", [])) or 1
        total_combos = (
            len(cfg.get("chunkings", []))
            * len(cfg.get("embeddings", []))
            * len(cfg.get("rags", []))
            * len(cfg.get("retrievers", []))
            * n_llms
        )
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_experiment_schemas.py tests/test_orchestrator.py tests/test_experiments_api.py -v`
Expected: PASS (novos + todos os existentes de orquestrador/API, que usam o default `["gemini"]` e continuam válidos).

- [ ] **Step 8: Commit**

```bash
git add backend/app/experiments/schemas.py backend/app/core/db/models.py backend/app/experiments/orchestrator.py backend/app/api/experiments.py backend/tests/test_experiment_schemas.py backend/tests/test_orchestrator.py backend/tests/test_experiments_api.py
git commit -m "feat(experiments): add llm as a matrix dimension"
```

---

### Task 2: Frontend — MultiSelect de LLMs no formulário

**Files:**
- Modify: `frontend/src/pages/ExperimentPage.tsx`
- Test: `frontend/src/pages/ExperimentPage.test.tsx`

**Interfaces:**
- Consumes: `Options.llms` (já existe em `types.ts`); `createExperiment` (envia FormData com `config`).
- Produces: o `config` enviado passa a incluir `llms: string[]`; o form tem um MultiSelect "LLMs".

- [ ] **Step 1: Write the failing test**

Em `frontend/src/pages/ExperimentPage.test.tsx`, adicionar um teste que inspeciona o `config` enviado (o mock de `getOptions` já inclui `llms: ["gemini"]`):

```typescript
  it("includes llms in the submitted config", async () => {
    renderPage();
    const user = userEvent.setup();
    const fillBtn = await screen.findByRole("button", { name: /preencher tudo/i });
    await user.click(fillBtn);
    await user.click(screen.getByRole("button", { name: /gerar/i }));
    await waitFor(() => expect(client.createExperiment).toHaveBeenCalled());
    const form = vi.mocked(client.createExperiment).mock.calls[0][0] as FormData;
    const config = JSON.parse(form.get("config") as string);
    expect(config.llms).toEqual(["gemini"]);
  });
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/pages/ExperimentPage.test.tsx`
Expected: FAIL — `config.llms` é `undefined` (o form ainda não envia `llms`).

- [ ] **Step 3: Add the llms state, form field, config, and toggle logic**

Em `frontend/src/pages/ExperimentPage.tsx`:

1. Após `const [retrievers, setRetrievers] = useState<string[]>([]);`, adicionar:
```tsx
  const [llms, setLlms] = useState<string[]>([]);
```

2. Em `allFilled`, adicionar a condição de LLMs (após a linha de `retrievers`):
```tsx
    retrievers.length === options.retrievers.length &&
    llms.length === options.llms.length &&
    metrics.length === options.metrics.length;
```

3. Em `toggleAll`, incluir os LLMs nos dois ramos:
```tsx
    if (allFilled) {
      setChunkings([]);
      setEmbeddings([]);
      setRags([]);
      setRetrievers([]);
      setLlms([]);
      setMetrics([]);
    } else {
      setChunkings(options?.chunkings ?? []);
      setEmbeddings(options?.embeddings ?? []);
      setRags(options?.rags ?? []);
      setRetrievers(options?.retrievers ?? []);
      setLlms(options?.llms ?? []);
      setMetrics(options?.metrics ?? []);
    }
```

4. Em `submit()`, incluir `llms` no objeto `config`:
```tsx
      const config = {
        name: name || undefined,
        base,
        chunkings,
        embeddings,
        rags,
        retrievers,
        llms,
        metrics,
      };
```

5. Na JSX, substituir o `MultiSelect` de "Métricas" (que hoje é isolado) por um `Group` com "LLMs" + "Métricas":
```tsx
          <Group grow align="flex-start">
            <MultiSelect
              label="LLMs"
              placeholder="Selecione"
              data={options?.llms ?? []}
              value={llms}
              onChange={setLlms}
              searchable
            />
            <MultiSelect
              label="Métricas"
              placeholder="Selecione"
              data={options?.metrics ?? []}
              value={metrics}
              onChange={setMetrics}
              searchable
            />
          </Group>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/pages/ExperimentPage.test.tsx`
Expected: PASS (o novo teste + os existentes; "Preencher tudo" agora preenche 6 campos e `allFilled` fica verdadeiro).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/ExperimentPage.tsx frontend/src/pages/ExperimentPage.test.tsx
git commit -m "feat(experiments): pick LLMs in the create-experiment form"
```

---

### Task 3: Frontend — LLM na tela de resultados (coluna + filtro)

**Files:**
- Modify: `frontend/src/api/types.ts` (`ExperimentResultRow`)
- Modify: `frontend/src/pages/ExperimentDetailPage.tsx`
- Test: `frontend/src/pages/ExperimentDetailPage.test.tsx`

**Interfaces:**
- Consumes: `ExperimentResultRow` (ganha `llm`); `getExperiment` (mock nos testes).
- Produces: coluna de LLM na célula "Combinação" (tabela + modal) e um filtro MultiSelect "LLMs".

- [ ] **Step 1: Write the failing test**

Em `frontend/src/pages/ExperimentDetailPage.test.tsx`:

1. Adicionar `llm` a **todos** os objetos de resultado nos mocks de `getExperiment` (as duas linhas do mock principal e quaisquer outras). Para o mock principal (as duas linhas), usar `llm: "gemini"` na primeira e `llm: "ollama"` na segunda; para os demais mocks de linha única, usar `llm: "gemini"`.

2. Adicionar um teste de filtro por LLM (espelhando o teste "filters rows by retriever"):

```typescript
  it("filters rows by llm (ollama)", async () => {
    renderPage();
    const user = userEvent.setup();
    await screen.findByText(/recursive/);
    await user.click(screen.getAllByLabelText(/llms/i)[0]);
    await user.click(await screen.findByText("ollama"));
    await waitFor(() => {
      expect(screen.queryByText("gemini")).not.toBeNull();
    });
  });
```

(O objetivo do assert é confirmar que o valor de LLM aparece na tabela; o teste principal é o filtro renderizar sem erro e a linha correspondente permanecer.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/pages/ExperimentDetailPage.test.tsx`
Expected: FAIL — não existe filtro/label "LLMs" nem coluna de llm; `getAllByLabelText(/llms/i)` não encontra elemento.

- [ ] **Step 3: Add `llm` to the result row type**

Em `frontend/src/api/types.ts`, na interface `ExperimentResultRow`, adicionar após `retriever: string;`:

```typescript
  llm: string;
```

- [ ] **Step 4: Add the llm filter state, predicate, filter control, and combo display**

Em `frontend/src/pages/ExperimentDetailPage.tsx`:

1. Após `const [fRetrievers, setFRetrievers] = useState<string[]>([]);`, adicionar:
```tsx
  const [fLlms, setFLlms] = useState<string[]>([]);
```

2. No `filtered` (useMemo), adicionar o predicado de LLM e incluir `fLlms` no array de dependências:
```tsx
  const filtered = useMemo(() => {
    return results.filter(
      (r) =>
        (fChunkings.length === 0 || fChunkings.includes(r.chunking)) &&
        (fEmbeddings.length === 0 || fEmbeddings.includes(r.embedding)) &&
        (fRags.length === 0 || fRags.includes(r.rag)) &&
        (fRetrievers.length === 0 || fRetrievers.includes(r.retriever)) &&
        (fLlms.length === 0 || fLlms.includes(r.llm)),
    );
  }, [results, fChunkings, fEmbeddings, fRags, fRetrievers, fLlms]);
```

3. No `useEffect` que reseta a página, adicionar `fLlms` ao array de dependências:
```tsx
  }, [fChunkings, fEmbeddings, fRags, fRetrievers, fLlms, sortKey, sortDir, pageSize]);
```

4. Em `hasFilters`, adicionar `fLlms`:
```tsx
  const hasFilters =
    fChunkings.length > 0 ||
    fEmbeddings.length > 0 ||
    fRags.length > 0 ||
    fRetrievers.length > 0 ||
    fLlms.length > 0;
```

5. No botão "Limpar filtros" (`onClick`), adicionar `setFLlms([]);` junto dos outros `set...([])`.

6. Na barra de filtros, após o `MultiSelect` de "Retrievers", adicionar:
```tsx
            <MultiSelect
              label="LLMs"
              placeholder="Todos"
              data={distinct((r) => r.llm)}
              value={fLlms}
              onChange={setFLlms}
              clearable
              size="xs"
            />
```

7. Na célula "Combinação" da tabela (bloco `<div className="ditto-combo">` dentro de `pageRows.map`), adicionar `<span>{row.llm}</span>` após `<span>{row.retriever}</span>`.

8. Na célula "Combinação" do modal (`modalRow`), adicionar `<span>{modalRow.llm}</span>` após `<span>{modalRow.retriever}</span>`.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/pages/ExperimentDetailPage.test.tsx`
Expected: PASS.

- [ ] **Step 6: Run the full frontend suite + build**

Run: `cd frontend && npx vitest run`
Expected: PASS (todas as suítes).
Run: `cd frontend && npm run build`
Expected: build sem erros de tipo.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api/types.ts frontend/src/pages/ExperimentDetailPage.tsx frontend/src/pages/ExperimentDetailPage.test.tsx
git commit -m "feat(experiments): show and filter results by LLM"
```

---

## Self-Review

**Spec coverage:**
- Schema `llms` (default `["gemini"]`) → Task 1 Step 3. ✓
- `ExperimentRun.llm` (nullable) + migração → Task 1 Step 4 + Global Constraints. ✓
- Orquestrador: product de 5 dims, LLM por combinação, grava `run.llm` → Task 1 Step 5. ✓
- API GET: `"llm"` na linha (coalesce "gemini") + progresso × llms → Task 1 Step 6. ✓
- Form: MultiSelect LLMs + config.llms + toggleAll/allFilled → Task 2. ✓
- Resultados: type `llm`, filtro LLMs, coluna na combinação (tabela+modal) → Task 3. ✓
- Testes backend (schema, orquestrador, API) e frontend (form envia llms, resultados filtram/exibem) → Tasks 1–3. ✓
- Compatibilidade (config sem llms → progresso fallback 1; run.llm NULL → "gemini") → Task 1 Steps 4/6. ✓

**Placeholder scan:** nenhum TBD/TODO; passos de código com conteúdo completo e comando + saída esperada.

**Type consistency:** `ExperimentConfig.llms: list[str]` (Task 1) ↔ `config.llms` enviado (Task 2) ↔ `cfg.get("llms")` (Task 1 GET). `ExperimentRun.llm` ↔ `run.llm` (GET). `ExperimentResultRow.llm: string` (Task 3 types) ↔ `row.llm`/`modalRow.llm`/`distinct((r) => r.llm)` (Task 3 componente) ↔ `"llm"` na resposta do GET (Task 1). Fake `_llm_factory(name, **kwargs)` aceita qualquer nome (usado nos testes de orquestrador/API com 2 LLMs).
