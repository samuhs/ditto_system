# Ditto

Ever tried to pick the "best" RAG setup and realized you're just guessing? Which chunker, which embedder, which retriever, which prompt trick, which model? Ditto runs the whole grid for you.

You feed it your documents and a list of questions. It tries every combination of **chunking × embedding × RAG technique × retriever × LLM**, scores each one on quality metrics, and shows you a ranked table. There's also a chat agent (built on LangGraph) with swappable personas that reuses the same pipelines, so you can actually talk to your data once you've found a setup you like.

I built it for my PhD, but it works fine as a general playground for comparing RAG strategies on your own stuff.

> The code is in English. The web UI is in Portuguese (PT-BR), so heads up if that's not your language.

---

## What you get

- **The big grid.** 4 chunkers, 3 embedders, 6 RAG techniques, 4 retrievers, and however many LLMs you want, run over a CSV of questions and ranked by metrics.
- **Everything is a plugin.** Each technique sits behind an interface and a registry. Write a class, register it, and it shows up in the UI on its own. No wiring.
  - Chunking: `fixed`, `recursive`, `token`, `semantic`
  - Embeddings: `gemini`, plus local `e5` and `paraphrase`
  - RAG: `naive`, `agentic`, `hyde`, `rerank`, `crag`, `compression`
  - Retrievers: `similarity`, `mmr`, `multi_query`, `parent_document`
  - LLMs: `gemini`, `ollama` (local, name as many models as you want), `custom` (any OpenAI-compatible endpoint)
  - Metrics: `answer_relevancy`, `faithfulness`, `context_precision`, `context_recall`, `answer_correctness`, `rouge_l`
- **A results table that doesn't fight you.** Sort by any metric, filter by any dimension, paginate.
- **A chat agent.** LangGraph flow (guardrail, triage, RAG, memory, persona) with prompts you can edit and personas you can swap. Save the conversations and rate them 0 to 10.
- **Prompt control.** See and edit the prompts each technique uses. Every experiment saves a snapshot of the prompts it ran with, so old results stay reproducible.
- **Run it fully offline.** Pair a local Ollama model with a local embedder and you never touch a paid API.

---

## How it fits together

```
┌───────────┐     ┌───────────────────────────┐     ┌──────────┐
│ Frontend  │ ──▶ │ API (FastAPI, modular)    │ ──▶ │ Qdrant   │  vectors
│ React+Vite│     │ ingestion / experiments   │     ├──────────┤
│  (nginx)  │     │ chat / prompts / settings │ ──▶ │ Postgres │  runs & results
└───────────┘     └───────────────────────────┘     └──────────┘
                          │
                          ▼  (optional, on your host)
                      Ollama  ·  local LLM generation
```

- `backend/` is a FastAPI modular monolith. The interesting parts live in `backend/app/core/` (`chunking/`, `embedding/`, `retrieval/`, `rag/`, `llm/`, `evaluation/`, `chat/`, `vectorstore/`), each one a registry of pluggable techniques. HTTP routes sit in `backend/app/api/`.
- `frontend/` is React + Vite + TypeScript + Mantine. nginx proxies `/api/` to the backend.
- `database/` has a sample document (a travel-guide FAQ) so you can kick the tires right away.
- `docs/superpowers/` keeps the design specs and plans, if you want to see how it grew.

---

## Get it running (Docker)

You'll need [Docker](https://docs.docker.com/get-docker/) with Compose, and either a [Gemini API key](https://aistudio.google.com/apikey) or a local [Ollama](https://ollama.com). Grabbing a Gemini key is the fastest way in, since it powers the default embeddings.

```bash
git clone https://github.com/samuhs/ditto_system.git
cd ditto_system

cp .env.example .env
# open .env and drop your key in GEMINI_API_KEY=...
# (or leave it blank and set it later in the Settings screen)

make up          # api:8000 · frontend:3000 · qdrant:6333 · postgres:5432
```

Now open **http://localhost:3000** and walk through it:

1. **Inserir documentos**: upload your files, or use the sample in `database/`.
2. **Gerar teste**: pick the combinations you want and a questions CSV. The columns are `pergunta,resposta_referencia`.
3. **Resultados**: see which combinations won, ranked by metric.

A few more commands when you need them:

```bash
make logs        # tail the logs
make down        # stop everything
make test        # backend tests (pytest)
make front-test  # frontend tests (vitest)
```

---

## Configuring it

Most config comes from `.env` (there's a `.env.example` to copy):

| Variable | What it's for | Docker default |
|---|---|---|
| `DATABASE_URL` | Postgres connection | `postgresql://ditto:ditto@postgres:5432/ditto` |
| `QDRANT_URL` | Qdrant connection | `http://qdrant:6333` |
| `GEMINI_API_KEY` | Gemini key (embeddings + Gemini LLM) | *(empty)* |

You can also set the **Gemini key** and add **named Ollama models** straight from the **Configurações** screen in the app, no restart needed. Those runtime settings land in `backend/config/app_settings.json`. It's git-ignored and stored in plaintext, so keep it on your own machine.

### Going local with Ollama

The Docker container talks to an Ollama server running on your host.

```bash
# grab a model
ollama pull qwen2.5:3b-instruct

# start and stop the server (there are helpers)
make ollama-up      # boots `ollama serve` if it isn't up yet
make ollama-down

# then open the Settings screen and add a model:
# id "qwen"  →  model "qwen2.5:3b-instruct"
# it shows up as an LLM option in experiments and chat.
```

Want to skip Google entirely? The Docker image already bundles the local embedders (`e5`, `paraphrase`). Pick one of those plus a local Ollama model and nothing leaves your machine. The embedder pulls its weights the first time you use it and caches them in the `hf_cache` volume, so it only happens once. That does make the image chunky (PyTorch comes along for the ride). If you only ever use Gemini embeddings, drop the `[local]` extra from `backend/Dockerfile` and the image slims right back down.

---

## Running from source

You'll want Python 3.11+ and Node 22. You still need Qdrant and Postgres around, and the easy move is `make up` for just the datastores while you run the app locally.

```bash
# backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"          # use "[dev,local]" if you want local embedders
python -m pytest
uvicorn app.main:app --reload

# frontend
cd frontend
npm install
npm run dev
npm test                         # add -- --run for a single pass
```

Three things to know before you touch the code:

- Every technique is an interface plus a registry entry. To add one, you write a class and register it.
- Code stays in English (names, docstrings, errors). UI copy and prompts stay in PT-BR.
- Tests never hit the network or Postgres. They use Qdrant `:memory:`, SQLite, and injected fakes.

### Adding your own technique

Say you want a new RAG technique:

1. Drop `backend/app/core/rag/<name>.py` in place, implementing the `RAG` interface (`answer(query) -> RAGResult`).
2. Call `rag_registry.register("<name>", YourClass)` and import it in `backend/app/core/rag/__init__.py`.
3. If it uses prompts, add an entry to `PROMPT_SPECS`/`DEFAULT_PROMPTS` and drop the `.md` files under `backend/prompts/<name>/`.

That's it. It now shows up in `/options`, the experiment grid, the chat config, and the prompt editor. Same recipe for chunkers, embedders, retrievers, metrics, and LLM providers.

---

## One security note

Ditto has no login and assumes it's running somewhere you trust, for one person. Please don't put it on the open internet. Your secrets (the Gemini key) sit in `.env` and `backend/config/app_settings.json` as plaintext. Both are git-ignored, so keep them local. The default Postgres password (`ditto:ditto`) is fine for your laptop and nothing else, so change it if you ever share the setup.

---

## Contributing

Pull requests are welcome. Keep the interface-plus-registry pattern for new techniques, add tests (pytest for backend, vitest for frontend), and keep both suites green with `make test` and `make front-test`. English in the code, PT-BR in the UI. For anything big, open an issue first so we can talk it through.

---

## License

[MIT](LICENSE), © 2026 Samuel Henrique Silva.

This started as a PhD project. If Ditto helps your work, a shout-out goes a long way.
