# LLM como dimensão da matriz de experimentos — Design

**Data:** 2026-07-03
**Autor:** Samuel (samuhs) + Claude

## Contexto

O Ditto compara composições de RAG numa matriz **chunking × embedding × rag × retriever** e rankeia por métricas. O LLM de geração, porém, é fixo: `ExperimentConfig.llm: str = "gemini"` e o formulário de "Gerar teste" nem expõe a escolha — todo experimento roda com gemini. Com o provider `ollama` recém-adicionado (qwen2.5:3b-instruct), faz sentido comparar LLMs na mesma rodada.

O orquestrador hoje constrói o LLM uma vez antes do loop (`llm = deps.llm_factory(config.llm)`) e itera `itertools.product(config.chunkings, config.embeddings, config.rags, config.retrievers)`. Cada `ExperimentRun` registra `chunking`, `embedding`, `rag_technique`, `retriever` — não o LLM. A API GET monta as linhas de resultado a partir desses campos, e a tela de detalhe (`ExperimentDetailPage`) exibe/filtra por essas quatro dimensões.

Referências: `backend/app/experiments/{schemas,orchestrator}.py`, `backend/app/api/experiments.py`, `backend/app/core/db/models.py`, `frontend/src/pages/{ExperimentPage,ExperimentDetailPage}.tsx`.

## Objetivo

Tornar o **LLM uma dimensão da matriz**: o usuário escolhe vários LLMs em "Gerar teste", o experimento roda `chunking × embedding × rag × retriever × llm`, e os resultados exibem/filtram por LLM — permitindo comparar (ex.) gemini vs ollama numa única rodada.

## Arquitetura

### 1. Schema (`backend/app/experiments/schemas.py`)

`ExperimentConfig`: trocar `llm: str = "gemini"` por:

```python
    llms: list[str] = ["gemini"]
```

`eval_embedding: str = "gemini"` permanece singular (fora de escopo). O default `["gemini"]` preserva o comportamento anterior quando `llms` é omitido.

### 2. Modelo (`backend/app/core/db/models.py`)

`ExperimentRun` ganha uma coluna:

```python
    llm: Mapped[str] = mapped_column(String(60))
```

O schema é criado por `Base.metadata.create_all()`, que **não** altera tabelas existentes. Bancos já deployados precisam de ALTER manual:

```sql
ALTER TABLE experiment_run ADD COLUMN IF NOT EXISTS llm VARCHAR(60);
```

Runs de experimentos antigos ficam com `llm` NULL.

### 3. Orquestrador (`backend/app/experiments/orchestrator.py`)

- Remover a construção única `llm = deps.llm_factory(config.llm)` de antes do loop.
- Incluir `config.llms` no produto cartesiano:
  ```python
  for chunking, embedding, rag_name, retriever_name, llm_name in itertools.product(
      config.chunkings, config.embeddings, config.rags, config.retrievers, config.llms
  ):
  ```
- Construir o LLM **por combinação**: `llm = deps.llm_factory(llm_name)` dentro do loop (usado pelo retriever `multi_query` e pelo rag, como hoje).
- Gravar `llm=llm_name` no `ExperimentRun` criado.
- O `eval_embedder` continua construído uma única vez.
- O checkpoint de pausa e o retry por questão permanecem inalterados.

### 4. API GET (`backend/app/api/experiments.py`)

- Na montagem de cada linha de resultado, adicionar `"llm": run.llm`.
- No cálculo do total de progresso, multiplicar também pelo número de LLMs, com fallback para experimentos antigos sem a chave `llms`:
  ```python
  n_llms = len(cfg.get("llms", [])) or 1
  total = (
      len(cfg.get("chunkings", []))
      * len(cfg.get("embeddings", []))
      * len(cfg.get("rags", []))
      * len(cfg.get("retrievers", []))
      * n_llms
  )
  ```

### 5. Frontend — formulário (`frontend/src/pages/ExperimentPage.tsx`)

- Novo estado `llms: string[]` e um `MultiSelect` "LLMs" com `data={options?.llms ?? []}`.
- Incluir `llms` no objeto `config` enviado em `submit()`.
- Incluir `llms` em `allFilled` (comparando com `options.llms.length`) e em `toggleAll` (preencher/limpar).

### 6. Frontend — resultados (`frontend/src/pages/ExperimentDetailPage.tsx` + `types.ts`)

- `ExperimentResultRow` ganha `llm: string` (`types.ts`).
- Novo estado de filtro `fLlms: string[]` + `MultiSelect` "LLMs" (`data={distinct((r) => r.llm)}`) na barra de filtros.
- `llm` entra no predicado de `filtered`, no `useEffect` que reseta a página quando filtros mudam, e em `hasFilters`/"Limpar filtros".
- `llm` é exibido na célula "Combinação" (`ditto-combo`) tanto na linha da tabela quanto no modal de detalhe, junto de corte/embedding/rag/retriever.

## Tratamento de erros / compatibilidade

- **Experimentos antigos** (config sem `llms`): o total de progresso usa `n_llms = ... or 1`; as linhas de resultado têm `run.llm` NULL → o front renderiza como valor vazio/"—". Não quebram.
- LLM desconhecido em `config.llms`: `deps.llm_factory(llm_name)` levanta `KeyError` no início da combinação; o retry por questão e o registro de falha do experimento já cobrem (comportamento existente).
- Métricas e evaluation não mudam (o `eval_embedder` continua único).

## Testes

**Backend (herméticos, sem rede — fakes injetados via `ExperimentDeps`):**
- `test_experiment_schemas.py`: `ExperimentConfig` parseia `llms` como lista; default `["gemini"]` quando omitido.
- `test_orchestrator.py`: com 2 LLMs (fakes) e as demais dimensões, o número de `ExperimentRun` criados = produto das **cinco** dimensões; cada run grava o `llm` correto; `llm_factory` é chamado por combinação (uma vez por LLM da matriz).
- `test_experiments_api.py`: GET devolve `llm` em cada linha de resultado; o total de progresso reflete `len(llms)`; experimento antigo (config sem `llms`) usa fallback 1 sem erro.

**Frontend (vitest, mocks do client):**
- `ExperimentPage`: carrega `options.llms`; selecionar LLMs e submeter envia `config.llms` no FormData; "Preencher tudo" inclui os LLMs.
- `ExperimentDetailPage`: linhas exibem o `llm`; o filtro "LLMs" restringe as linhas e reseta a página.

## Decisões e trade-offs

- **LLM como dimensão da matriz** (multi-select), não um único por experimento: permite comparar LLMs numa rodada — o caso de uso central agora que há gemini + ollama. Custo: coluna nova + migração + loop + exibição.
- **Default `["gemini"]`**: preserva o comportamento anterior e a compatibilidade de chamadas que omitam `llms`.
- **`ExperimentRun.llm` como coluna** (não só no JSON de config): as linhas de resultado precisam do LLM por combinação para exibir/filtrar/ordenar, no mesmo padrão das outras quatro dimensões.
- **`eval_embedding` continua singular**: o pedido é só sobre o LLM de geração; o embedder de avaliação como dimensão fica para outra fatia (YAGNI).
- **Matriz multiplica**: incluir N LLMs multiplica as combinações e as chamadas de API/modelo. É uma escolha consciente do usuário ao montar o experimento.

## Fora de escopo

- Expor `eval_embedding` no formulário / embedder de avaliação por combinação.
- Recomputar/backfill do `llm` para experimentos antigos (ficam NULL/"—").
- Qualquer mudança nas métricas ou na avaliação.
