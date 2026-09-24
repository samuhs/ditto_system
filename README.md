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
  - LLMs: Gemini (`gemini-2.5-flash-lite`) and every model pulled on your Ollama server, each listed by its real name and tagged `local` or `remoto`. There's also `custom` for any OpenAI-compatible endpoint.
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

make setup       # checks Docker, creates .env, asks for your Gemini key (optional)
make up          # api:8000 · frontend:3000 · qdrant:6333 · postgres:5432
make llm-setup   # optional: serve a local LLM with Ollama on your GPU (see below)
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

Ollama runs on your host, not in Docker, so it can use your GPU (Metal on Apple Silicon, CUDA/ROCm on Linux). One command sets it up:

```bash
make llm-setup                              # default model: qwen2.5:3b-instruct
make llm-setup MODEL=llama3.1:8b            # or pick another one
YES=1 make llm-setup                        # answer yes to every prompt
```

It walks through these steps and tells you what it found at each one:

1. Detects your GPU. With no GPU it warns you and carries on in CPU mode, which is slow.
2. Installs Ollama if it's missing, after asking first. On macOS it uses `brew install ollama`. On Linux it runs the official `install.sh`.
3. Starts the server. On Linux it makes sure Ollama listens beyond `localhost` (`OLLAMA_HOST=0.0.0.0`) so the containers can reach it. That also exposes port 11434 on your network, so firewall it on shared machines.
4. Pulls the model, sends it a test prompt and checks that it loaded 100% on the GPU.
5. The app asks the Ollama server for its models, so every pulled model shows up by its real name in experiments and chat, with no restart needed.
6. If the stack is up, checks that the API container can reach Ollama.

Run it again whenever you like. Steps that are already done get skipped. To start and stop the server by hand, use `make ollama-up` and `make ollama-down`.

`llm-setup` also sets `OLLAMA_NUM_PARALLEL` (default 4, change it with `PARALLEL=...`) so that Ollama answers several requests at once. On macOS that goes through `launchctl setenv`, which doesn't survive a reboot, so run `make llm-setup` again after restarting.

**Behind a corporate VPN (Ollama in Docker):** some VPN/security agents on macOS break outgoing connections to `127.0.0.1` ("can't assign requested address"). Native Ollama talks to its own llama.cpp runner over a fixed `127.0.0.1` port, so generation fails there whatever you set in `OLLAMA_HOST`. `make llm-setup` detects this and offers the alternative, or you can pick it yourself:

```bash
make llm-setup LLM_SERVER=docker   # Ollama in a container: VPN-proof, CPU only on macOS
make llm-setup LLM_SERVER=host     # back to the native Ollama (GPU)
```

Docker mode writes `LLM_SERVER`, `COMPOSE_PROFILES` and `OLLAMA_BASE_URL` to `.env`, so `make up`/`down` bring the `ollama` service along and the API talks to it at `http://ollama:11434/v1`. The container's loopback lives inside the Docker VM, out of the VPN agent's reach. It's slower on a Mac because Docker has no Metal GPU, so prefer small models there. If the container can't download models on your network, run `ollama pull <model>` on the host and repeat the command: it mounts `~/.ollama/models`. `make model-*` commands follow whichever server is active, and the container also answers on the host at `localhost:11435`.

**Managing models:**

```bash
make model-add qwen3:1.7b     # pull into Ollama (it shows up in the app)
make model-rm qwen3:1.7b      # delete it from Ollama (it leaves the app)
make model-list               # what's on the Ollama server
```

**Running experiments faster:** the **Gerar teste** screen has a **Perguntas em paralelo** field (1 to 32). Above 1, Ditto answers that many questions of each combination at the same time. That only speeds things up if the server can serve requests concurrently (`OLLAMA_NUM_PARALLEL`, `llama-server -np`, vLLM). Keep in mind that the per-question latency then also counts the time a request spent waiting in the server's queue.

**Measuring your machine:** `make bench-llm MODEL=qwen2.5:3b-instruct` sends RAG-shaped prompts at 1, 2, 4 and 8 concurrent requests and prints wall time, tokens/s and p50/p95 latency. It takes `LEVELS=1,2,4 N=16 BASE_URL=...` and works against any OpenAI-compatible server. Use it to pick a sensible parallelism. For a comparison of inference servers for small models, see [docs/research/2026-09-23-inferencia-small-llms.md](docs/research/2026-09-23-inferencia-small-llms.md).

Want to skip Google entirely? The Docker image already bundles the local embedders (`e5`, `paraphrase`). Pick one of those plus a local Ollama model and nothing leaves your machine. The embedder pulls its weights the first time you use it and caches them in the `hf_cache` volume, so it only happens once. That does make the image chunky (PyTorch comes along for the ride). If you only ever use Gemini embeddings, drop the `[local]` extra from `backend/Dockerfile` and the image slims right back down.

---

## Running from source

You'll want Python 3.11+ and Node 22. You still need Qdrant and Postgres around, and the easy move is `make up` for just the datastores while you run the app locally.

The quick way is one command. It creates `backend/.venv`, installs the frontend packages, sets up graphify (the code knowledge graph and its git hooks) and fetches the impeccable design engine. It is safe to re-run and works behind corporate VPNs:

```bash
make setup-dev          # add LOCAL=1 for the local embedders (pulls torch)
```

Or by hand:

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
