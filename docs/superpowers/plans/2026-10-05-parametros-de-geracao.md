# Parâmetros de geração (temperatura e limite de tokens) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Na tela "Novo experimento", o usuário define a **temperatura** e o **máximo de tokens da resposta** usados por todas as LLMs do Experimento; os valores são gravados na config, aplicados na geração e mostrados no detalhe do Experimento.

**Architecture:** Dois campos opcionais novos em `ExperimentConfig` (`temperature`, `max_tokens`; `None` = padrão do servidor). O orquestrador os repassa ao `llm_factory` (o único ponto onde o Experimento cria LLMs); `GeminiLLM` e `OllamaLLM` os traduzem para os parâmetros do cliente LangChain, só quando não são `None`. A config já é JSON no Postgres: sem migração, e a Retomada herda os valores porque relê a config gravada.

**Tech Stack:** FastAPI + Pydantic v2, LangChain (`langchain_openai.ChatOpenAI`, `langchain_google_genai.ChatGoogleGenerativeAI`), React + Mantine + Vitest.

**Spec:** este plano (pedido do usuário em 2026-10-05: "definir temperatura usada nos modelos; se outra métrica for importante, também; na tela de experimento").

## Por que temperatura + max_tokens (e não mais)

- **Temperatura** — hoje nenhum provedor recebe temperatura no Experimento, então cada servidor usa o próprio padrão (Gemini via LangChain ≈ 0.7, Ollama 0.8, MLX 0.0). Comparar LLMs com amostragens diferentes contamina o resultado; fixar 0 torna as respostas reprodutíveis.
- **Máximo de tokens da resposta** — limita custo e latência, e iguala o teto de tamanho entre modelos (respostas longas mudam faithfulness/relevância). Também evita que um modelo "verborrágico" trave uma Combinação.
- **Fora do escopo (decidido):** `top_p` (mexer junto com temperatura confunde o efeito; temperatura basta), `seed` (o servidor MLX e o Gemini via LangChain não garantem suporte; com temperatura 0 é redundante), temperatura por LLM (um valor por Experimento mantém a comparação justa), aplicar ao Chat e à extração do Grafo (outras telas).

## Global Constraints

- `temperature`: `float | None`, `0.0 <= t <= 2.0` (faixa aceita por Gemini e OpenAI-compatível). `None` = padrão do servidor.
- `max_tokens`: `int | None`, `1 <= n <= 32768`. `None` = sem limite explícito.
- Valor `0` é válido e **diferente** de ausente: todo teste de presença usa `is not None` (Python) / `!= null` (TS), nunca truthiness.
- Na tela, temperatura e max_tokens vêm **vazios** (padrão de cada servidor, decisão do usuário em 2026-10-05). Campo vazio é enviado como `null`.
- Os parâmetros valem para tudo que a LLM do Experimento gera na Combinação: resposta, HyDE, multi-query, reescritas do CRAG/agentic, compressão (todos compartilham a mesma instância).
- Identificadores/docstrings/erros em inglês; textos de UI em PT-BR.
- Testes não tocam rede (clientes LangChain substituídos por fakes via `monkeypatch`).

## Review Focus

1. **Temperatura 0 tratada como ausente** — `if temperature:` ou `{detail.temperature && …}` descarta o 0 (e o JSX renderiza um "0" solto). Esperado: 0 chega ao cliente e aparece como "Temperatura 0". Testado nas Tasks 1, 2 e 4.
2. **Experimento antigo sem as chaves** — `ExperimentConfig(**config)` de um Experimento criado antes desta feature (detalhe, Retomada, contagem). Esperado: carrega com `None`, roda como antes, o detalhe não mostra nada. Testado nas Tasks 2 e 3.
3. **Campo apagado na tela** — o usuário digita e depois limpa a temperatura. Esperado: envia `null` (padrão do servidor), não `0` nem `""`. Testado na Task 4.
4. **Valor fora da faixa via API** — `temperature: 3` ou `max_tokens: 0`. Esperado: 422 sem criar o Experimento. Testado nas Tasks 2 e 3.
5. **Retomada** — o Experimento pausado volta a rodar. Esperado: mesma temperatura/max_tokens da primeira execução (vem da config gravada). Testado na Task 2.

---

## File Structure

- Modify `backend/app/core/llm/ollama.py` — aceita `max_tokens` além de `temperature`.
- Modify `backend/app/core/llm/gemini.py` — aceita `temperature` e `max_tokens` (→ `max_output_tokens`).
- Modify `backend/app/experiments/schemas.py` — campos novos em `ExperimentConfig`.
- Modify `backend/app/experiments/orchestrator.py:935` — repassa os campos ao `llm_factory`.
- Modify `backend/app/api/experiments.py:~553` — expõe os campos no detalhe.
- Modify `frontend/src/api/types.ts`, `frontend/src/pages/ExperimentPage.tsx`, `frontend/src/pages/ExperimentDetailPage.tsx`.
- Tests: `backend/tests/test_llm.py`, `backend/tests/test_experiment_schemas.py`, `backend/tests/test_orchestrator.py`, `backend/tests/test_experiments_api.py`, `frontend/src/pages/ExperimentPage.test.tsx`, `frontend/src/pages/ExperimentDetailPage.test.tsx`.

---

### Task 1: Provedores de LLM aceitam temperatura e max_tokens

**Files:**
- Modify: `backend/app/core/llm/ollama.py:12-31`
- Modify: `backend/app/core/llm/gemini.py:11-28`
- Test: `backend/tests/test_llm.py`

**Interfaces:**
- Produces: `OllamaLLM(model=None, base_url=None, api_key="ollama", client=None, temperature: float | None = None, max_tokens: int | None = None, timeout=None)` e `GeminiLLM(model=..., api_key=None, client=None, timeout=None, temperature: float | None = None, max_tokens: int | None = None)`. `resolve_llm(name, **kwargs)` já repassa kwargs aos dois — não muda.

- [ ] **Step 1: Write the failing tests** (acrescentar em `backend/tests/test_llm.py`)

```python
def test_ollama_passes_max_tokens_and_omits_unset_sampling(monkeypatch):
    import langchain_openai

    captured = {}

    class _FakeChatOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(langchain_openai, "ChatOpenAI", _FakeChatOpenAI)
    OllamaLLM(model="m", base_url="http://localhost:11436/v1", max_tokens=256)
    assert captured["max_tokens"] == 256
    assert "temperature" not in captured  # None: the server's default applies


def test_ollama_omits_max_tokens_when_unset(monkeypatch):
    import langchain_openai

    captured = {}

    class _FakeChatOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(langchain_openai, "ChatOpenAI", _FakeChatOpenAI)
    OllamaLLM(model="m", base_url="http://localhost:11436/v1", temperature=0)
    assert captured["temperature"] == 0
    assert "max_tokens" not in captured


def test_gemini_passes_temperature_zero_and_max_output_tokens(monkeypatch):
    import langchain_google_genai

    captured = {}

    class _FakeChat:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(langchain_google_genai, "ChatGoogleGenerativeAI", _FakeChat)
    GeminiLLM(model="gemini-2.5-flash-lite", api_key="k", temperature=0, max_tokens=128)
    assert captured["temperature"] == 0
    assert captured["max_output_tokens"] == 128


def test_gemini_omits_unset_sampling(monkeypatch):
    import langchain_google_genai

    captured = {}

    class _FakeChat:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(langchain_google_genai, "ChatGoogleGenerativeAI", _FakeChat)
    GeminiLLM(model="gemini-2.5-flash-lite", api_key="k")
    assert "temperature" not in captured
    assert "max_output_tokens" not in captured
```

Confira no topo do arquivo se `GeminiLLM` já está importado (`from app.core.llm.gemini import GeminiLLM`); se não, acrescente.

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_llm.py -v`
Expected: FAIL — `TypeError: ... unexpected keyword argument 'max_tokens'` / `'temperature'`.

- [ ] **Step 3: Implement**

`backend/app/core/llm/base.py`, abaixo de `build_llm`, o helper compartilhado:

```python
def sampling_kwargs(**params) -> dict:
    """The given sampling params minus the unset (None) ones; 0 is kept."""
    return {k: v for k, v in params.items() if v is not None}
```

`backend/app/core/llm/ollama.py` — import `from app.core.llm.base import LLM, llm_registry, sampling_kwargs` e construtor:

```python
    def __init__(
        self, model=None, base_url=None, api_key="ollama", client=None, temperature=None,
        max_tokens: int | None = None, timeout: float | None = None,
    ) -> None:
        if client is None:
            from langchain_openai import ChatOpenAI

            settings = get_settings()
            # Unset sampling (None) falls back to the server's defaults.
            sampling = sampling_kwargs(temperature=temperature, max_tokens=max_tokens)
            client = ChatOpenAI(
                model=model or settings.ollama_model,
                base_url=base_url or settings.ollama_base_url,
                api_key=api_key,
                # Travamento/2 (#20): a hard timeout so a stuck server call fails
                # into the usual retry path instead of hanging the worker thread.
                timeout=timeout,
                **sampling,
            )
        self._client = client
```

`backend/app/core/llm/gemini.py`:

```python
from app.core.llm.base import LLM, llm_registry, sampling_kwargs
...
    def __init__(
        self,
        model: str = DEFAULT_GEMINI_MODEL,
        api_key: str | None = None,
        client=None,
        timeout: float | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> None:
        if client is None:
            from langchain_google_genai import ChatGoogleGenerativeAI

            client = ChatGoogleGenerativeAI(
                model=model,
                google_api_key=api_key or get_gemini_key(),
                # Travamento/2 (#20): a hard timeout so a stuck call fails into the
                # usual retry path instead of hanging the worker thread.
                timeout=timeout,
                # Unset sampling (None) falls back to the client's defaults.
                **sampling_kwargs(temperature=temperature, max_output_tokens=max_tokens),
            )
        self._client = client
```

- [ ] **Step 4: Run to verify they pass**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_llm.py -v`
Expected: PASS (incluindo o `test_ollama_passes_an_explicit_temperature` existente).

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/llm backend/tests/test_llm.py
git commit -m "feat(llm): temperature and max_tokens on Gemini and local providers"
```

---

### Task 2: ExperimentConfig carrega os parâmetros e o orquestrador os aplica

**Files:**
- Modify: `backend/app/experiments/schemas.py` (classe `ExperimentConfig`)
- Modify: `backend/app/experiments/orchestrator.py:935`
- Test: `backend/tests/test_experiment_schemas.py`, `backend/tests/test_orchestrator.py`

**Interfaces:**
- Consumes: `resolve_llm(name, timeout=..., temperature=..., max_tokens=...)` (Task 1).
- Produces: `ExperimentConfig.temperature: float | None`, `ExperimentConfig.max_tokens: int | None`. O `llm_factory` passa a ser chamado com `(llm_name, timeout=..., temperature=..., max_tokens=...)`.

- [ ] **Step 1: Write the failing tests**

Em `backend/tests/test_experiment_schemas.py`:

```python
from pydantic import ValidationError

_MIN = dict(
    base="viagem", chunkings=["recursive"], embeddings=["gemini"], rags=["naive"],
    retrievers=["similarity"], metrics=["faithfulness"], llms=["gemini"],
)


def test_generation_params_default_to_unset():
    config = ExperimentConfig(**_MIN)  # an Experimento saved before this feature
    assert config.temperature is None
    assert config.max_tokens is None


def test_generation_params_keep_zero_temperature():
    assert ExperimentConfig(**_MIN, temperature=0).temperature == 0


@pytest.mark.parametrize("bad", [{"temperature": -0.1}, {"temperature": 2.1},
                                 {"max_tokens": 0}, {"max_tokens": 32769}])
def test_generation_params_out_of_range_are_rejected(bad):
    with pytest.raises(ValidationError):
        ExperimentConfig(**_MIN, **bad)
```

Em `backend/tests/test_orchestrator.py` (reaproveita o fixture `session_factory`, `_FakeLLM`, `_embedder_factory` e o mesmo preparo de `test_run_experiment_persists_results`):

```python
def test_llm_factory_receives_the_generation_params(session_factory):
    store = QdrantStore(client=QdrantClient(":memory:"))
    ingest_documents(
        [Document(name="a.txt", text="Para one.\n\nPara two here.")],
        IngestConfig(base="viagem", chunkings=["recursive"], embeddings=["gemini"]),
        store,
        embedder_factory=_embedder_factory,
    )
    session = session_factory()
    experiment = Experiment(name="temp-zero", status="pending", config={})
    session.add(experiment)
    session.commit()
    experiment_id = experiment.id
    session.close()

    calls = []

    def factory(name, **kwargs):
        calls.append(kwargs)
        return _FakeLLM()

    config = ExperimentConfig(
        llms=["gemini"], base="viagem", chunkings=["recursive"], embeddings=["gemini"],
        rags=["naive"], retrievers=["similarity"], metrics=["faithfulness"],
        temperature=0, max_tokens=256,
    )
    deps = ExperimentDeps(
        store=store, session_factory=session_factory,
        llm_factory=factory, embedder_factory=_embedder_factory,
    )
    run_experiment(experiment_id, config, [QuestionItem(text="Where?")], deps)

    assert calls and all(c["temperature"] == 0 and c["max_tokens"] == 256 for c in calls)
```

Para a Retomada (Review Focus 5): procure em `test_orchestrator.py` (ou `test_experiments_api.py`) o teste existente de Retomada (`grep -n "resume" backend/tests/*.py`) e acrescente ao teste que já pausa/retoma um Experimento a mesma checagem: grave `temperature: 0.3` na config inicial e afirme que todas as chamadas ao `llm_factory` depois da Retomada recebem `temperature == 0.3`. Se nenhum teste de Retomada aceitar um factory customizado, siga o padrão de `deps.llm_factory = ...` usado em `tests/test_experiment_graph.py:73`.

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_experiment_schemas.py tests/test_orchestrator.py -v`
Expected: FAIL — `AttributeError: 'ExperimentConfig' object has no attribute 'temperature'` e `KeyError: 'temperature'`.

- [ ] **Step 3: Implement**

`backend/app/experiments/schemas.py`, em `ExperimentConfig`, depois de `concurrency`:

```python
    # Sampling for every LLM in the experiment (answers and the LLM-assisted steps:
    # HyDE, multi-query, rewrites). None leaves the provider's default, which differs
    # between servers; 0 makes answers reproducible.
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    # Cap on tokens per generation. None: no explicit cap.
    max_tokens: int | None = Field(default=None, ge=1, le=32768)
```

`backend/app/experiments/orchestrator.py:935`:

```python
                    if llm_name != loaded_llm_name:
                        llm = deps.llm_factory(
                            llm_name, timeout=call_timeout_s,
                            temperature=config.temperature, max_tokens=config.max_tokens,
                        )
                        loaded_llm_name = llm_name
```

- [ ] **Step 4: Run to verify they pass**

Run: `cd backend && ./.venv/bin/python -m pytest -q`
Expected: tudo PASS (os fakes existentes aceitam `**kwargs`, então não quebram).

- [ ] **Step 5: Commit**

```bash
git add backend/app/experiments backend/tests/test_experiment_schemas.py backend/tests/test_orchestrator.py
git commit -m "feat(experiments): temperature and max_tokens in the experiment config"
```

---

### Task 3: API expõe os parâmetros no detalhe do Experimento

**Files:**
- Modify: `backend/app/api/experiments.py:~550-556` (dict do detalhe)
- Test: `backend/tests/test_experiments_api.py`

**Interfaces:**
- Consumes: `ExperimentConfig.temperature`, `.max_tokens` (Task 2).
- Produces: `GET /experiments/{id}` devolve `"temperature": float | null` e `"max_tokens": int | null`.

- [ ] **Step 1: Write the failing tests**

```python
def test_detail_reports_the_generation_params(client):
    payload = json.loads(_config_payload()) | {"temperature": 0, "max_tokens": 512}
    files = {"questions": ("q.csv", io.BytesIO(b"pergunta,resposta_referencia\nWhere?,\n"), "text/csv")}
    exp_id = client.post("/experiments", data={"config": json.dumps(payload)}, files=files).json()["id"]
    detail = client.get(f"/experiments/{exp_id}").json()
    assert detail["temperature"] == 0
    assert detail["max_tokens"] == 512


def test_detail_of_an_old_experiment_has_no_generation_params(client):
    deps = client.app.dependency_overrides[get_experiment_deps]()
    session = deps.session_factory()
    experiment = Experiment(
        name="antigo", status="done",
        config={"chunkings": ["recursive"], "embeddings": ["gemini"], "rags": ["naive"],
                "retrievers": ["similarity"], "llms": ["gemini"]},
    )
    session.add(experiment)
    session.commit()
    experiment_id = experiment.id
    session.close()
    detail = client.get(f"/experiments/{experiment_id}").json()
    assert detail["temperature"] is None
    assert detail["max_tokens"] is None


def test_create_experiment_rejects_an_out_of_range_temperature(client):
    payload = json.loads(_config_payload()) | {"temperature": 3}
    files = {"questions": ("q.csv", io.BytesIO(b"pergunta,resposta_referencia\nWhere?,\n"), "text/csv")}
    resp = client.post("/experiments", data={"config": json.dumps(payload)}, files=files)
    assert resp.status_code == 422
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_experiments_api.py -k "generation_params or out_of_range" -v`
Expected: os dois primeiros FAIL com `KeyError: 'temperature'`. O terceiro já deve passar (validação da Task 2) — se falhar, veja como `create_experiment` trata `ValidationError` na linha ~318.

- [ ] **Step 3: Implement** — no dict do detalhe, junto de `"eval_embedding"`/`"graph_extractor"`:

```python
            # Sampling the experiment's LLMs used; None: the provider's default.
            "temperature": cfg.get("temperature"),
            "max_tokens": cfg.get("max_tokens"),
```

- [ ] **Step 4: Run to verify they pass**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_experiments_api.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/experiments.py backend/tests/test_experiments_api.py
git commit -m "feat(api): report temperature and max_tokens on the experiment detail"
```

---

### Task 4: Tela de experimento — campos de temperatura e limite de tokens; detalhe mostra os valores

**Files:**
- Modify: `frontend/src/api/types.ts` (`ExperimentDetail`)
- Modify: `frontend/src/pages/ExperimentPage.tsx` (estado, seção "Execução", `submit`)
- Modify: `frontend/src/pages/ExperimentDetailPage.tsx:~337` (linha de metadados)
- Test: `frontend/src/pages/ExperimentPage.test.tsx`, `frontend/src/pages/ExperimentDetailPage.test.tsx`

**Interfaces:**
- Consumes: campos `temperature`/`max_tokens` da config (Task 2) e do detalhe (Task 3).
- Produces: config enviada com `temperature: number | null` e `max_tokens: number | null`.

- [ ] **Step 1: Write the failing tests**

Em `ExperimentPage.test.tsx` (usa `renderPage`, `fillValidForm`, `submittedConfig` já existentes):

```tsx
  it("submits no temperature and no token cap by default", async () => {
    renderPage();
    const user = userEvent.setup();
    await fillValidForm(user);
    await user.click(screen.getByRole("button", { name: /gerar experimento/i }));
    await waitFor(() => expect(client.createExperiment).toHaveBeenCalled());
    expect(submittedConfig().temperature).toBeNull();
    expect(submittedConfig().max_tokens).toBeNull();
  });

  it("submits the temperature and token cap the user typed", async () => {
    renderPage();
    const user = userEvent.setup();
    await fillValidForm(user);
    await user.type(screen.getByLabelText(/temperatura/i), "0.7");
    await user.type(screen.getByLabelText(/máximo de tokens/i), "512");
    await user.click(screen.getByRole("button", { name: /gerar experimento/i }));
    await waitFor(() => expect(client.createExperiment).toHaveBeenCalled());
    expect(submittedConfig().temperature).toBe(0.7);
    expect(submittedConfig().max_tokens).toBe(512);
  });

  it("sends null when the temperature field is cleared", async () => {
    renderPage();
    const user = userEvent.setup();
    await fillValidForm(user);
    const temp = screen.getByLabelText(/temperatura/i);
    await user.type(temp, "0.5");
    await user.clear(temp);
    await user.click(screen.getByRole("button", { name: /gerar experimento/i }));
    await waitFor(() => expect(client.createExperiment).toHaveBeenCalled());
    expect(submittedConfig().temperature).toBeNull();
  });
```

Em `ExperimentDetailPage.test.tsx`:

```tsx
  it("shows temperature 0 and the token cap", async () => {
    vi.mocked(client.getExperiment).mockResolvedValue({
      id: 11, name: "temp-zero", status: "done", temperature: 0, max_tokens: 512,
      progress: { completed: 1, total: 1, phase: "done" }, results: [],
    });
    renderPage();
    expect(await screen.findByText("Temperatura 0 · até 512 tokens")).toBeInTheDocument();
  });

  it("shows nothing about sampling on an experiment that predates it", async () => {
    vi.mocked(client.getExperiment).mockResolvedValue({
      id: 12, name: "antigo", status: "done",
      progress: { completed: 1, total: 1, phase: "done" }, results: [],
    });
    renderPage();
    await screen.findByText(/antigo/);
    expect(screen.queryByText(/temperatura/i)).not.toBeInTheDocument();
  });
```

- [ ] **Step 2: Run to verify they fail**

Run: `make front-test` (ou `cd frontend && npx vitest run src/pages/ExperimentPage.test.tsx src/pages/ExperimentDetailPage.test.tsx`)
Expected: FAIL — `Unable to find a label with the text of: /temperatura/i` e texto "Temperatura 0 · até 512 tokens" ausente.

- [ ] **Step 3: Implement**

`frontend/src/api/types.ts`, em `ExperimentDetail`:

```ts
  /** Sampling temperature the experiment's LLMs used; null/absent: the provider's default. */
  temperature?: number | null;
  /** Cap on tokens per generation; null/absent: no explicit cap. */
  max_tokens?: number | null;
```

`frontend/src/pages/ExperimentPage.tsx` — estado, junto de `concurrency`:

```tsx
  const [temperature, setTemperature] = useState<number | null>(null);
  const [maxTokens, setMaxTokens] = useState<number | null>(null);
```

No `config` de `submit()`, depois de `concurrency,`:

```tsx
        temperature,
        max_tokens: maxTokens,
```

Na seção "Execução", depois do `NumberInput` de "Perguntas em paralelo":

```tsx
            <NumberInput
              label="Temperatura"
              description="Vale para todas as LLMs. Vazio usa o padrão de cada servidor; 0 dá respostas reprodutíveis."
              placeholder="padrão do servidor"
              min={0}
              max={2}
              step={0.1}
              decimalScale={2}
              value={temperature ?? ""}
              onChange={(v) => setTemperature(typeof v === "number" ? v : null)}
              w={300}
            />
            <NumberInput
              label="Máximo de tokens da resposta"
              description="Vazio: sem limite. Muito baixo corta respostas (e o raciocínio de modelos como o qwen3)."
              min={1}
              max={32768}
              allowDecimal={false}
              placeholder="sem limite"
              value={maxTokens ?? ""}
              onChange={(v) => setMaxTokens(typeof v === "number" && v >= 1 ? v : null)}
              w={300}
            />
```

`frontend/src/pages/ExperimentDetailPage.tsx`, depois da linha do `graph_extractor` (~338) — usar `!= null`, nunca `&&` sobre o número:

```tsx
          {detail.temperature != null && (
            <span>
              Temperatura {detail.temperature}
              {detail.max_tokens != null && ` · até ${detail.max_tokens} tokens`}
            </span>
          )}
          {detail.temperature == null && detail.max_tokens != null && (
            <span>Até {detail.max_tokens} tokens</span>
          )}
```

- [ ] **Step 4: Run to verify they pass**

Run: `make front-test`
Expected: PASS (todos os testes do frontend).

- [ ] **Step 5: Commit**

```bash
git add frontend/src
git commit -m "feat(front): temperature and token cap on the new-experiment screen"
```

---

### Task 5: Verificação ponta a ponta e grafo

- [ ] **Step 1:** `make test && make front-test` — tudo verde.
- [ ] **Step 2:** `make up-local`, abrir http://localhost:3000, criar um Experimento pequeno com temperatura 0 e máx. 256 tokens com uma LLM local; conferir no detalhe "Temperatura 0 · até 256 tokens" e que as respostas não passam do limite.
- [ ] **Step 3:** se `CONTEXT.md` tiver um glossário dos campos do Experimento (ex.: "concorrência"), acrescentar "Temperatura" e "Máximo de tokens da resposta" com uma linha cada.
- [ ] **Step 4:** `graphify update .` e commit:

```bash
git add CONTEXT.md graphify-out
git commit -m "docs: generation params in the glossary; refresh graph"
```
