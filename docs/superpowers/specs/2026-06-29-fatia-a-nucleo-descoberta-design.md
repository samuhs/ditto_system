# Fatia A — Núcleo de Descoberta (Spec de Design)

**Data:** 2026-06-29
**Projeto:** Ditto System (sistema de doutorado)
**Escopo deste spec:** Fatia A — pipeline configurável de ingestão → RAG → avaliação → experimentos comparativos.

---

## 1. Contexto e objetivo

O sistema do doutorado visa descobrir, via experimentação, **qual composição de metodologia
(chunking × embedding × técnica de RAG × retriever)** gera as melhores respostas para um conjunto de
documentos, medido por métricas da área. Essa é a fase de *cold-start* da tese: começar com um fluxo
de RAG forte e, no futuro (fatias posteriores), substituir progressivamente por um modelo fine-tunado.

A **Fatia A** entrega o núcleo de descoberta: inserir documentos em um banco vetorial com múltiplas
técnicas de corte/embedding, rodar múltiplas técnicas de RAG/retriever sobre um conjunto de perguntas,
avaliar as respostas e produzir um ranking das composições.

Fatias seguintes (fora deste spec): **B** (agente conversacional + avaliação de diálogo), **C**
(fine-tuning). Graph RAG é um incremento posterior dentro do mesmo arcabouço da Fatia A.

### Idioma
Documentos e perguntas são majoritariamente **PT-BR**. As escolhas de embedding local refletem isso.

---

## 2. Decisões de arquitetura

| Tema | Decisão |
|------|---------|
| Backend | **Monólito modular** em FastAPI (um serviço), com `core/` compartilhado para evitar duplicação |
| Banco vetorial | **Qdrant** (container nativo, múltiplas coleções nomeadas, filtros por metadata) |
| Banco relacional | **Postgres** (experimentos, runs, resultados, scores) |
| Frontend | **React + Vite + Mantine**, container próprio servido por **Nginx** |
| LLM (geração e juiz) | **Gemini `gemini-2.5-flash-lite`** como default; slot **custom** (endpoint OpenAI-compatible: Ollama local ou externo) |
| Orquestração de experimento | Execução em **background task** com *polling* de status (sem Celery — YAGNI) |
| Infra | **Docker + docker-compose**; **Makefile** para os comandos |
| Código | PEP-8, docstrings nas funções, comentários só o necessário |

### Princípio central: interface + registry
Toda "técnica" plugável (chunking, embedding, retriever, técnica de RAG, evaluator, provedor de LLM)
vive atrás de uma **interface** e é registrada em um **registry**. Adicionar uma nova técnica = criar a
classe e registrá-la, sem tocar no orquestrador. É isso que permite **Graph RAG** entrar depois sem
refatoração.

### Regra de ouro
Todo acesso a LLM, embedding e vector store passa pelo `core/`. Nenhum módulo instancia clientes
diretamente.

---

## 3. Estrutura de pastas

```
backend/
  core/
    llm/          # interface LLM + registry (Gemini, custom/OpenAI-compatible)
    embedding/    # interface Embedder + registry (Gemini, e5, paraphrase, custom)
    vectorstore/  # wrapper Qdrant (criar/popular/consultar coleções)
    db/           # Postgres (SQLAlchemy): models e sessão
    config/       # registries centrais + schemas Pydantic de configuração
  ingestion/      # Chunker interface + registry; pipeline de inserção
  rag/            # técnica de RAG (Naive, Agentic) + Retriever interface + registry
  evaluation/     # Evaluator interface + registry (RAGAS + operacional)
  experiments/    # orquestrador: produto cartesiano + execução + persistência
  api/            # routers FastAPI (thin: validam e delegam aos módulos)
frontend/         # React + Vite + Mantine
docker-compose.yml
Makefile
```

Containers no compose: **api**, **qdrant**, **postgres**, **frontend (Nginx)**.

---

## 4. Componentes do `core/`

### 4.1 LLM (`core/llm/`)
- Interface `LLM` (ex.: `generate(prompt, **opts) -> str`, mais variante de chat se necessário).
- Provedores: `GeminiLLM` (default `gemini-2.5-flash-lite`, via API key), `CustomLLM`
  (endpoint OpenAI-compatible — Ollama localhost ou externo; para a aplicação é equivalente).
- Registrados por nome no registry. Selecionável por configuração.

### 4.2 Embedding (`core/embedding/`)
- Interface `Embedder` (ex.: `embed_documents(texts) -> list[vector]`, `embed_query(text) -> vector`).
- Modelos:
  - `GeminiEmbedder` — `text-embedding-004` (API).
  - `E5Embedder` — `intfloat/multilingual-e5-small` (local, HuggingFace).
  - `ParaphraseEmbedder` — `paraphrase-multilingual-MiniLM-L12-v2` (local, HuggingFace).
  - Slot `custom`.
- Cada modelo tem dimensão própria → cada combinação vira coleção Qdrant separada (sem conflito).

### 4.3 Vector store (`core/vectorstore/`)
- Wrapper sobre Qdrant: criar coleção nomeada, inserir vetores com metadata, consultar (com filtros).
- Convenção de nome de coleção: `<base>__<chunking>__<embedding>` (ex.: `viagem__recursive__e5`).
- Metadata por vetor: `source_doc`, `chunking_strategy`, `embedding_model`, `chunk_index`.

### 4.4 DB (`core/db/`)
- SQLAlchemy + Postgres. Models:
  - `experiment` — `id`, `name`, `status` (`pending|running|done|failed`), `config` (JSON), `created_at`, `finished_at`.
  - `experiment_run` — `id`, `experiment_id`, combinação (`chunking`, `embedding`, `rag_technique`, `retriever`), `status`.
  - `run_result` — `id`, `run_id`, `question`, `reference_answer` (nullable), `generated_answer`,
    `retrieved_context` (JSON), `scores` (JSON), `latency_ms`, `tokens`.

### 4.5 Config (`core/config/`)
- Registries centrais e schemas Pydantic que validam as configurações vindas da API.

---

## 5. Módulo de ingestão (`ingestion/`)

- Interface `Chunker` (`split(documents) -> chunks`) + registry.
- Estratégias:
  - `FixedSizeChunker` — corte por nº fixo de caracteres com overlap (baseline).
  - `RecursiveChunker` — `RecursiveCharacterTextSplitter` (respeita parágrafos/sentenças).
  - `SemanticChunker` — corta em fronteiras semânticas (usa embeddings).
  - `SentenceTokenChunker` — corte por sentença / contagem de tokens.
- Pipeline de inserção: recebe `.txt`(s) + config (base, lista de chunkings, lista de embeddings).
  Para cada `chunking × embedding`: corta → embeda → cria/popula a coleção Qdrant correspondente.

---

## 6. Módulo de RAG (`rag/`)

### Eixo 1 — Técnica de RAG (fluxo de geração)
- `NaiveRAG` — recupera top-k → injeta no prompt → LLM responde.
- `AgenticRAG` — agente (LangChain/LangGraph) decide se/quando/como buscar; pode reformular a query e
  buscar múltiplas vezes.
- `GraphRAG` — **fora da Fatia A**; entra depois via registry sem refatorar.

### Eixo 2 — Retriever (como recuperar)
- Interface `Retriever` + registry.
- `SimilarityRetriever` — vetorial denso, top-k (baseline).
- `MMRRetriever` — diversifica resultados (menos redundância).
- `MultiQueryRetriever` — LLM gera variações da pergunta e une resultados.
- `ParentDocumentRetriever` — recupera chunk pequeno, devolve o documento-pai maior.
- `HybridRetriever` (dense + BM25) — **opcional**, adicionável depois.

A combinação ranqueada é `chunking × embedding × técnica_RAG × retriever`. O LLM é trocável em todos
os fluxos via `core/llm`.

---

## 7. Módulo de avaliação (`evaluation/`)

- Interface `Evaluator` + registry. Entrada: `(pergunta, resposta_gerada, contexto_recuperado, resposta_referencia?)`.
- **RAGAS (núcleo, sem gabarito):** Faithfulness, Answer Relevancy, Context Precision, Context Recall.
- **Operacional (sempre):** latência (ms), tokens, nº de chamadas de LLM.
- **Com gabarito (quando há `resposta_referencia`):** Answer Correctness (RAGAS) + ROUGE-L.
- Juiz LLM das métricas RAGAS = Gemini (trocável via `core/llm`).

---

## 8. Orquestrador de experimentos (`experiments/`)

1. Recebe da API: nome do experimento (se vazio, gera um aleatório legível, ex.: `brave-otter-42`),
   combinações selecionadas, métricas escolhidas e o **CSV de perguntas**.
2. CSV: colunas `pergunta` e `resposta_referencia` (opcional). Com referência → ativa métricas com
   gabarito; sem referência → roda só RAGAS-núcleo + operacional.
3. Cria o `experiment` (`status=pending`) e executa como **background task** (`status=running`).
4. Produto cartesiano: para cada combinação selecionada (`experiment_run`), para cada pergunta do CSV:
   recupera → gera (Gemini) → avalia → persiste `run_result`.
5. Ao concluir, `status=done` (ou `failed` com erro registrado).
6. A tela de geração faz *polling* do status e vira a tela de resultados ao concluir.

---

## 9. API (`api/`)

Routers finos que validam (Pydantic) e delegam. Esboço de endpoints:

- `POST /ingest` — upload de `.txt`(s) + config de ingestão; dispara o pipeline.
- `GET /collections` — lista coleções/bases disponíveis (para a tela de experimento).
- `POST /experiments` — cria e dispara um experimento (multipart: CSV + config JSON).
- `GET /experiments/{id}` — status + (quando pronto) resultados.
- `GET /experiments` — lista experimentos.
- `GET /options` — lista técnicas disponíveis nos registries (chunking, embedding, rag, retriever, métricas, llm) para popular os formulários.

---

## 10. Frontend (`frontend/`)

React + Vite + Mantine, servido por Nginx; consome a API.

- **Inserir documentos:** upload de `.txt`(s) + form (nome da base, seleção de chunkings, seleção de embeddings).
- **Gerar teste de qualidade:** seleção de base, das combinações (técnicas/retrievers), das métricas,
  upload do CSV de perguntas, nome do experimento (opcional). Após disparar, faz *polling* e transita
  para resultados.
- **Visualização de resultados:** tabela limpa (pergunta, resposta, score-resumo). Clicar na linha abre
  um card com a configuração completa da combinação, resposta, contexto recuperado e todos os scores.

---

## 11. Infra e padrões

- `Dockerfile` por componente (api, frontend); `docker-compose.yml` com api + qdrant + postgres + frontend.
- `Makefile` com alvos: `make up`, `make down`, `make test`, `make ingest`, `make logs`, etc.
- PEP-8; docstrings nas funções; comentários apenas quando agregam.
- Configuração sensível (API keys) via variáveis de ambiente / `.env`.

---

## 12. Fora de escopo (Fatia A)

- Graph RAG (incremento posterior, mesmo registry).
- Hybrid/BM25 retriever (opcional, posterior).
- Agente conversacional, persona, memória, salvamento e avaliação de diálogo (Fatia B).
- Fine-tuning (Fatia C).
- Filas robustas (Celery), autenticação/multiusuário, deploy em nuvem.

---

## 13. Critérios de sucesso

1. Inserir 1+ `.txt` gera coleções Qdrant para cada `chunking × embedding` selecionado, com metadata correta.
2. Um experimento roda o produto cartesiano das combinações × perguntas do CSV e persiste todos os
   `run_result` com scores RAGAS + operacionais.
3. A tela de resultados permite comparar composições e identificar a melhor por métrica.
4. Adicionar uma nova técnica (ex.: um chunker) exige apenas criar a classe e registrá-la, sem alterar
   o orquestrador.
5. Trocar o LLM de Gemini para um endpoint custom é uma mudança de configuração, não de código.
6. `make up` sobe todos os serviços; `make test` roda a suíte.
