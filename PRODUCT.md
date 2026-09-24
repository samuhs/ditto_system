# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Researchers who want to find the best RAG setup for their own documents, working without the author at their side. They know what RAG is in general terms but not Ditto's internals. Typical job: upload a document collection and a CSV of questions, run a grid of combinations, read which combination won and why, then talk to the data through the chat agent with the winning setup.

The author (a PhD researcher) is also a daily user, but the UI must not rely on author knowledge.

## Product Purpose

Ditto removes guesswork from choosing a RAG pipeline. It runs every combination of chunking × embedding × RAG technique × retriever × LLM over a question set, scores each on quality metrics, and ranks them. Success: a researcher who has never seen Ditto can go from documents to a trustworthy ranked answer, and understand what the numbers mean, without asking anyone.

## Positioning

A combinatorial experiment bench, not a chat product. The unit of value is the ranked, reproducible comparison (prompt snapshots saved per experiment), with a chat agent that reuses the same pipelines once a setup is chosen.

## Operating Context

- Runs locally via Docker (frontend :3000, API :8000); optional local Ollama on the host, so fully offline use is possible.
- Long-running jobs: experiments and ingestion run for minutes to hours in the background; users leave and come back (tasks toast).
- Inputs: document files (md/txt/pdf) and a CSV with columns `pergunta,resposta_referencia`.
- Outputs: ranked results table (sort/filter/paginate), per-experiment detail, saved and rated dialogues (0–10).
- Main flow: Inserir documentos → Gerar teste → Resultados. Secondary: Prompts, Config. de chat, Conversa, Avaliação de diálogos, Agente, Configurações.

## Capabilities and Constraints

- Chunking: fixed, recursive, token, semantic. Embeddings: gemini, e5, paraphrase. RAG: naive, agentic, hyde, rerank, crag, compression. Retrievers: similarity, mmr, multi_query, parent_document. LLMs: Gemini plus every Ollama model (tagged local/remoto), custom OpenAI-compatible.
- Metrics: answer_relevancy, faithfulness, context_precision, context_recall, answer_correctness, rouge_l (0..1).
- Techniques are plugins (interface + registry); the UI must render whatever options `/options` returns, not a hard-coded list.
- UI text in PT-BR; code in English.
- Stack: React 18 + Vite + TypeScript + Mantine 7, framer-motion, @xyflow/react. Tests with vitest (must keep passing).

## Brand Commitments

- Name: **Ditto**.
- Metaphor: the Pokémon Ditto that takes the shape of what it studies ("absorve, assume a forma, especializa"). Keep it as a light identity thread; it must never cost clarity.
- Palette, fonts and current visuals are not binding (user confirmed "nada é fixo" beyond name and metaphor).
- Design principles adopted from the SBB design system (digital.sbb.ch), principles only, not SBB branding: user-centred, recognisable, inclusive, reduced, holistic, self-explanatory, task-oriented, appropriate. SBB UX-writing rules apply: buttons 1–4 words as actions, descriptive links, sentence case, labels always present (placeholders only as examples), errors that say how to fix, confirm destructive actions, step labels as nouns.

## Evidence on Hand

- Sample document: `database/faq_manus_completa.md` (travel-guide FAQ). Sample questions: `database/perguntas.csv`, `database/perguntas_min.csv`.
- No testimonials, benchmarks or external users to cite; do not invent any.

## Product Principles

1. **Reduced:** show what the current step needs; advanced options (retriever params, prompts, LLM parallelism) sit one level deeper.
2. **Self-explanatory:** every technique, metric and status is explained in the user's terms at the point of use; a new researcher never needs the author.
3. **Task-oriented:** navigation follows the job (prepare data → run → compare → converse), not the backend's module list.
4. **Recognisable:** one pattern per job across all pages (same form layout, same table, same status language, same feedback).
5. **Trust the numbers:** results must be readable, comparable and honest about what was run and with which prompts.

## Accessibility & Inclusion

Target WCAG 2.2 AA: text contrast ≥ 4.5:1, visible focus, full keyboard use, status never conveyed by color alone, respect `prefers-reduced-motion`. Long sessions reading tables: favour legibility over atmosphere.
