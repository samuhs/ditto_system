# Ditto

Sistema de doutorado: ingere documentos, roda experimentos de RAG (chunking × embedding × rag × retriever) sobre perguntas e rankeia por métricas de qualidade.

## Como iniciar o sistema (Docker)
```bash
make setup       # 1ª vez: checa Docker, cria .env, pede chave Gemini
make up          # sobe tudo: api:8000, frontend:3000, qdrant:6333, postgres:5432 (portas mudam via .env: API_PORT etc.)
make down        # derruba o stack
make logs        # logs em tempo real
make llm-setup   # servidor de LLM local: MLX no Apple Silicon (GPU, padrão), senão Ollama nativo; baixa MODEL=...
make llm-setup LLM_SERVER=host|docker|mlx  # troca: Ollama nativo | Ollama num container (atrás de VPN que quebra 127.0.0.1; sem GPU no Mac) | MLX
make llm-up | llm-down | llm-status        # sobe/para/checa o servidor escolhido (make up também sobe)
make up-local | down-local | status-local  # alternativa ao make up: API e front no host (venv + Vite), só Postgres/Qdrant no Docker, tudo via [::1] (para VPN que bloqueia 127.0.0.1)
make doctor                                # testa cada conexão de rede e recomenda make up ou make up-local
make model-add <modelo> | model-rm <modelo> | model-list   # MLX: Qwen2.5-7B-Instruct-4bit (mlx-community) ou org/repo; Ollama: qwen3:1.7b
make bench-llm MODEL=...   # throughput do servidor de LLM por nível de paralelismo
make memory-profile                        # perfil de memória ativo (low ≤ 8 GB, standard) e o que ele muda
make memory-profile PROFILE=low|standard   # troca o perfil (reinicia o servidor de LLM; depois make up/up-local)
make mem-watch                             # memória livre, swap, memória da API/MLX (footprint no macOS) e modelos carregados, a cada 2s
```
- Frontend: http://localhost:3000 · API: http://localhost:8000 (`/health`, `/options`, `/ingest`, `/experiments`)
- `GEMINI_API_KEY` no `.env` é opcional (gitignored): sem ela o Gemini some das opções e tudo roda com LLM local (MLX/Ollama) e embedders locais. A imagem Docker já traz os embedders locais (`e5`, `paraphrase`, torch CPU).

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
- `backend/app/core/memory/` — `leases.py`: cache de vetores das perguntas e troca de reserva para experimentos em etapas; perfis de memória, `ModelManager` (todo embedder passa por ele: cache com limite de modelos locais) e política de device (embedder nunca divide a GPU com LLM local)
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
