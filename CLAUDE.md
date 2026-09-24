# Ditto

Sistema de doutorado: ingere documentos, roda experimentos de RAG (chunking × embedding × rag × retriever) sobre perguntas e rankeia por métricas de qualidade.

## ⚠️ Ao iniciar a sessão
**Leia o `HANDOFF.md` na raiz** — ele resume o estado, as decisões e as pendências da última sessão.

## Como iniciar o sistema (Docker)
```bash
make setup       # 1ª vez: checa Docker, cria .env, pede chave Gemini
make up          # sobe tudo: api:8000, frontend:3000, qdrant:6333, postgres:5432
make down        # derruba o stack
make logs        # logs em tempo real
make llm-setup   # prepara Ollama no host (GPU, OLLAMA_NUM_PARALLEL), baixa MODEL=... (o app lista os modelos do servidor ao vivo)
make model-add qwen3:1.7b | make model-rm qwen3:1.7b | make model-list
make bench-llm MODEL=...   # throughput do servidor de LLM por nível de paralelismo
```
- Frontend: http://localhost:3000 · API: http://localhost:8000 (`/health`, `/options`, `/ingest`, `/experiments`)
- Precisa de `GEMINI_API_KEY` no `.env` (já configurado, gitignored). No Docker use embedding `gemini` (a imagem não traz os embedders locais).

## Ambiente de desenvolvimento
```bash
make setup-dev          # venv do backend, npm ci, graphify (grafo + hooks de git), engine do impeccable
LOCAL=1 make setup-dev  # idem + embedders locais (sentence-transformers/torch)
```
Idempotente e funciona atrás de VPN corporativa (reaproveita as CAs do host). Os hooks do Claude chamam o graphify por `scripts/graphify.sh`, que acha a instalação em qualquer máquina.

## Testes
```bash
make test         # backend (pytest) — ou: cd backend && ./.venv/bin/python -m pytest
make front-test   # frontend (vitest)
```
Dev backend usa o venv `backend/.venv` (Python 3.13). Frontend usa Node 22.

## Estrutura
- `backend/app/` — FastAPI monólito modular (`core/`, `ingestion/`, `experiments/`, `api/`)
- `frontend/` — React + Vite + TS + Mantine (nginx faz proxy `/api/` → api)
- `docs/superpowers/{specs,plans}/` — specs e planos de implementação
- `database/` — documento de teste (FAQ de guia de viagem)

## Convenções
- Toda técnica plugável vive atrás de **interface + registry**; adicionar = criar classe + registrar.
- Código (identificadores/docstrings/erros) em **inglês**; dados e textos de UI em **PT-BR**.
- Testes não tocam rede/Postgres (Qdrant `:memory:`, SQLite, fakes injetados).

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
