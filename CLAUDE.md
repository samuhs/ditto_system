# Ditto

Sistema de doutorado: ingere documentos, roda experimentos de RAG (chunking × embedding × rag × retriever) sobre perguntas e rankeia por métricas de qualidade.

## ⚠️ Ao iniciar a sessão
**Leia o `HANDOFF.md` na raiz** — ele resume o estado, as decisões e as pendências da última sessão.

## Como iniciar o sistema (Docker)
```bash
make up          # sobe tudo: api:8000, frontend:3000, qdrant:6333, postgres:5432
make down        # derruba o stack
make logs        # logs em tempo real
```
- Frontend: http://localhost:3000 · API: http://localhost:8000 (`/health`, `/options`, `/ingest`, `/experiments`)
- Precisa de `GEMINI_API_KEY` no `.env` (já configurado, gitignored). No Docker use embedding `gemini` (a imagem não traz os embedders locais).

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
