# Contributing to Ditto

Thanks for wanting to help. Ditto is a PhD research tool, so the most useful contributions are new RAG techniques, metrics and bug reports from people running it on their own documents.

By taking part you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Before you start

- **Bugs:** open an issue with the bug template. Say how you run Ditto (`make up` or `make up-local`), which LLM server (MLX, Ollama, Gemini) and paste the relevant `make logs` lines.
- **Ideas and new techniques:** open an issue with the feature template first, so we can agree on the shape before you write code.
- **Questions:** ask in [Discussions](https://github.com/samuhs/ditto_system/discussions).
- **Security problems:** don't open a public issue. See [SECURITY.md](SECURITY.md).
- **Small fixes** (typos, docs, an obvious bug): go straight to a pull request.

## Setting up

You need Docker with Compose, Python 3.11+ (the dev venv uses 3.13) and Node 22.

```bash
make setup-dev          # backend/.venv, frontend packages, dev tools (LOCAL=1 adds local embedders)
make up-local           # Postgres + Qdrant in Docker, API + frontend on the host
```

The [README](README.md#running-from-source) has the manual steps if you'd rather not use `make`.

## Making a change

1. Branch from `main`.
2. Write a test first when you can. Backend tests use pytest, frontend tests use vitest.
3. Keep both suites green:

   ```bash
   make test         # backend
   make front-test   # frontend
   ```

4. Open a pull request against `main` and fill in the template. CI runs both suites on every PR.

## Conventions

- **Interface + registry.** Every pluggable technique (chunker, embedder, retriever, RAG, metric, LLM provider) implements an interface and registers itself. Adding one means writing a class and calling `<kind>_registry.register("<name>", YourClass)`. See [Adding your own technique](README.md#adding-your-own-technique).
- **Language.** Code is in English: identifiers, docstrings, error messages, commit messages. UI copy, prompts and sample data are in Brazilian Portuguese (PT-BR).
- **Tests stay offline.** No network, no real Postgres. Use Qdrant `:memory:`, SQLite and injected fakes.
- **Domain words.** [CONTEXT.md](CONTEXT.md) defines terms like *Base*, *Índice* and *Grafo de conhecimento*. Use them as defined; architecture decisions live in [docs/adr/](docs/adr/).
- **Commits.** Short imperative subject with a scope, as in the history: `feat(api): ...`, `fix(llm): ...`, `docs: ...`.
- **New datasets** under `database/` follow [database/DIRETRIZES.md](database/DIRETRIZES.md): keep the original and add a `_normalizado` version.

## Licensing

Ditto is [MIT licensed](LICENSE). By submitting a pull request you agree that your contribution is released under the same license.
