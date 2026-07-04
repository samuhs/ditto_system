# Ditto — RAG Experimentation Platform

Ditto is a self-hosted platform for **experimenting with Retrieval-Augmented Generation (RAG)**. You ingest your documents, then run a full grid of pipeline combinations — **chunking × embedding × RAG technique × retriever × LLM** — over a set of questions, and Ditto ranks each combination by quality metrics. It also ships a **conversational agent** (built on LangGraph) with swappable personas that reuses the same RAG pipelines.

It was built as a PhD research tool, but it works as a general playground for comparing RAG strategies on your own data.

> **Language note:** the code (identifiers, docstrings) is in English; the **web UI is in Portuguese (PT-BR)**.

---

## Features

- **Experiment matrix** — combine 4 chunkers × 3 embedders × 6 RAG techniques × 4 retrievers × N LLMs in one run, over a CSV of questions, and rank by metrics.
- **Pluggable everything** — every technique lives behind an *interface + registry*. Adding one = write a class and register it; it shows up automatically in the UI.
  - **Chunking:** `fixed`, `recursive`, `token`, `semantic`
  - **Embeddings:** `gemini` (+ local `e5`, `paraphrase` via the `local` extra)
  - **RAG techniques:** `naive`, `agentic`, `hyde`, `rerank`, `crag`, `compression`
  - **Retrievers:** `similarity`, `mmr`, `multi_query`, `parent_document`
  - **LLMs:** `gemini`, `ollama` (local, plus any named Ollama models you register), `custom` (any OpenAI-compatible endpoint)
  - **Metrics:** `answer_relevancy`, `faithfulness`, `context_precision`, `context_recall`, `answer_correctness`, `rouge_l`
- **Results explorer** — sortable/filterable table per experiment, per-metric columns, pagination.
- **Conversational agent** — LangGraph flow (guardrail → triage → RAG → memory → persona) with editable prompts and swappable personas; save dialogues and score them 0–10.
- **Prompt management** — view/edit the prompts each technique uses; each experiment snapshots the prompts it ran with.
- **Local or cloud LLMs** — use Google Gemini, or run fully local generation with [Ollama](https://ollama.com) (register your models with friendly names in the Settings screen).
- **Settings screen** — manage the Gemini API key and named Ollama models at runtime.

---

## Architecture

```
┌───────────┐     ┌──────────────────────────┐     ┌──────────┐
│ Frontend  │ ──▶ │ API (FastAPI, modular)   │ ──▶ │ Qdrant   │  vectors
│ React+Vite│     │ ingestion / experiments  │     ├──────────┤
│  (nginx)  │     │ chat / prompts / settings │ ──▶ │ Postgres │  runs & results
└───────────┘     └──────────────────────────┘     └──────────┘
                          │
                          ▼  (optional, on the host)
                      Ollama  — local LLM generation
```

- **`backend/`** — FastAPI modular monolith. Core lives in `backend/app/core/` (`chunking/`, `embedding/`, `retrieval/`, `rag/`, `llm/`, `evaluation/`, `chat/`, `vectorstore/`), each a registry of pluggable techniques. HTTP routers in `backend/app/api/`.
- **`frontend/`** — React + Vite + TypeScript + Mantine; nginx proxies `/api/` to the backend.
- **`database/`** — a sample document (a travel-guide FAQ) to try things out.
- **`docs/superpowers/`** — design specs and implementation plans (development history).

---

## Quickstart (Docker)

**Prerequisites:** [Docker](https://docs.docker.com/get-docker/) + Docker Compose, and **either** a [Google Gemini API key](https://aistudio.google.com/apikey) **or** a local [Ollama](https://ollama.com) install. A Gemini key is the simplest way to get running (it powers the default embeddings).

```bash
git clone https://github.com/samuhs/ditto_system.git
cd ditto_system

cp .env.example .env
#  → open .env and set GEMINI_API_KEY=...   (or leave blank and use the Settings screen later)

make up          # api:8000 · frontend:3000 · qdrant:6333 · postgres:5432
```

Open **http://localhost:3000** and follow the flow:

1. **Inserir documentos** — ingest your files (or the sample in `database/`).
2. **Gerar teste** — pick the combinations and a questions CSV (columns: `pergunta,resposta_referencia`).
3. **Resultados** — compare combinations, ranked by metric.

Useful commands:

```bash
make logs        # follow logs
make down        # stop the stack
make test        # backend tests (pytest)
make front-test  # frontend tests (vitest)
```

---

## Configuration

Runtime config comes from `.env` (see `.env.example`):

| Variable | Purpose | Default (Docker) |
|---|---|---|
| `DATABASE_URL` | Postgres connection | `postgresql://ditto:ditto@postgres:5432/ditto` |
| `QDRANT_URL` | Qdrant connection | `http://qdrant:6333` |
| `GEMINI_API_KEY` | Google Gemini key (embeddings + Gemini LLM) | *(empty)* |

The **Gemini API key** and **named Ollama models** can also be managed at runtime in the **Configurações** (Settings) screen — no restart needed. Runtime settings are stored in `backend/config/app_settings.json` (git-ignored; **plaintext**, so keep it local).

### Local LLMs with Ollama

The Docker image reaches an Ollama server running on your **host**.

```bash
# 1. install Ollama (https://ollama.com) and pull a model
ollama pull qwen2.5:3b-instruct

# 2. start/stop the Ollama server (helpers)
make ollama-up      # starts `ollama serve` if not already running
make ollama-down

# 3. in the Settings screen, register a named model, e.g. id "qwen" → model "qwen2.5:3b-instruct"
#    it then appears as an LLM option in experiments and chat.
```

> **Note:** local generation still uses **Gemini for embeddings** in the default Docker image. To run embeddings locally too, install the local extra (`sentence-transformers`) and run the backend from source (see below) — the `e5` / `paraphrase` embedders download model weights on first use.

---

## Development (from source)

**Prerequisites:** Python 3.11+ and Node 22. You still need Qdrant and Postgres — the simplest way is `make up` for the datastores and running the app locally against them.

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"          # add "[dev,local]" for local embedders
python -m pytest                 # run tests
uvicorn app.main:app --reload

# Frontend
cd frontend
npm install
npm run dev                      # Vite dev server
npm test                         # vitest (add -- --run for a single pass)
```

Conventions:
- Every pluggable technique = **interface + registry**; adding one = create a class and register it.
- Code (identifiers, docstrings, errors) in **English**; UI copy and prompt content in **PT-BR**.
- Tests never touch the network or Postgres (Qdrant `:memory:`, SQLite, injected fakes).

### Extending Ditto

To add, say, a new RAG technique:

1. Create `backend/app/core/rag/<name>.py` implementing the `RAG` interface (`answer(query) -> RAGResult`).
2. Call `rag_registry.register("<name>", YourClass)` and import it in `backend/app/core/rag/__init__.py`.
3. (If it uses prompts) add its entry to `PROMPT_SPECS`/`DEFAULT_PROMPTS` and drop `.md` files under `backend/prompts/<name>/`.

It now appears automatically in `/options`, the experiment matrix, chat config, and the prompt-management screen. The same pattern applies to chunkers, embedders, retrievers, metrics, and LLM providers.

---

## Security

Ditto is a **local research tool**. It has **no authentication** and assumes a trusted, single-user environment. Do **not** expose it to the public internet. Secrets (the Gemini key) live in `.env` and `backend/config/app_settings.json` in plaintext — both are git-ignored; keep them on your machine. The default Postgres credentials (`ditto:ditto`) are for local use only — change them for any shared deployment.

---

## Contributing

Contributions are welcome. Please:

- Keep the interface + registry pattern for new techniques.
- Add tests (backend: pytest, hermetic; frontend: vitest) and keep the suites green (`make test`, `make front-test`).
- Match the surrounding code style; English in code, PT-BR in UI copy.

Open an issue to discuss larger changes before a PR.

---

## License

[MIT](LICENSE) © 2026 Samuel Henrique Silva.

Built as part of a PhD research project. If Ditto helps your work, a mention is appreciated.
