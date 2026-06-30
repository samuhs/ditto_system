# Ditto — Handoff de Sessão

> Conceito: como o Pokémon Ditto, o sistema **se adapta a um conjunto de documentos e vira especialista nele**.

## Estado atual
- **Fatia A COMPLETA na `main`** (backend + frontend), até commit `1f37d66`.
- **88 testes backend + 11 frontend**, todos passando. Validado ao vivo com Gemini real.

## O que é a Fatia A (núcleo de descoberta)
Pipeline configurável: **ingerir docs → rodar experimento (produto cartesiano chunking × embedding × rag × retriever × perguntas) → resultados rankeados por métrica.**
Backend Python/FastAPI monólito modular (`backend/app/`):
- `core/` (registry genérico, settings, db, **llm**, **embedding**, **vectorstore/qdrant**, **chunking**, **retrieval**, **rag**, **evaluation**, **vector_math**)
- `ingestion/`, `experiments/` (orquestrador + ExperimentDeps injetável), `api/` (`/health /options /ingest /experiments`)
Frontend React+Vite+TS+Mantine (`frontend/`), 3 telas + cliente de API isolado, nginx proxy `/api`→api.

## Decisões-chave
- Tudo atrás de **interface + registry** → nova técnica = criar classe + registrar (Graph RAG/Hybrid entram sem refatorar).
- **Injeção de dependências** em tudo → suíte roda sem rede/Postgres (Qdrant `:memory:`, SQLite StaticPool, fakes).
- **Código (docstrings/erros) em inglês**; dados/UI em PT-BR.
- **Avaliação: métricas próprias, SEM lib RAGAS** (cosseno por embedding + rouge_l). Operacionais (latência/tokens) medidos no orquestrador.
- **AgenticRAG = loop compacto `SEARCH:`/`ANSWER:` (sem LangGraph)**; LangGraph fica para a Fatia B.
- LLM default `gemini-2.5-flash-lite`; embedding `gemini-embedding-001`.
- Execução em **background task + polling**.

## Pendência IMPORTANTE
- **Branch `frontend-redesign` NÃO mergeada.** Contém o redesign visual (tema escuro roxo, home page, blob morphing, nav fluida com framer-motion, telas reestilizadas). API intacta, testes/build OK. **Aguarda revisão visual do usuário → mergear se aprovado.**

## Gotchas
- API key do Gemini está em `.env` e `backend/.env` (gitignored, NÃO commitar).
- A imagem Docker da API **não instala o grupo `[local]`** (sentence-transformers) → embedders `e5`/`paraphrase` falham no container; **use `gemini` no docker**. Localmente (venv com `[local]`) funcionam.
- venv de dev: `backend/.venv` (Homebrew Python 3.13). Testes: `cd backend && ./.venv/bin/python -m pytest`.
- Coleções precisam ser pré-ingeridas antes de um experimento (config inexistente → experimento `failed`).

## Próximos passos sugeridos
1. Revisar/mergear `frontend-redesign`.
2. **Fatia B**: agente conversacional (persona trocável, LangGraph, memória curta) + salvar e avaliar diálogos.
3. **Fatia C**: fine-tuning (notebook desacoplado).
4. Specs/planos em `docs/superpowers/specs/` e `docs/superpowers/plans/`.
