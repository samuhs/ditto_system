# Novas técnicas de RAG (HyDE, Rerank, CRAG, Compressão) — Design

**Data:** 2026-07-02
**Autor:** Samuel (samuhs) + Claude

## Contexto

O Ditto compara composições de RAG (chunking × embedding × **rag** × retriever) e as rankeia por métricas. Hoje há duas técnicas de RAG: `naive` e `agentic`. Toda técnica vive atrás de **interface + registry** (`app.core.rag`): implementa `RAG.answer(query) -> RAGResult{answer, contexts}`, recebe um `retriever` + `llm` (+ prompts opcionais) e é registrada em `rag_registry`. O `/options.rags` deriva de `rag_registry.names()`, então uma técnica nova aparece automaticamente na matriz de experimentos, na config de chat e na tela de gestão de prompts.

Esta fatia adiciona **quatro** técnicas que reusam a infraestrutura existente (Qdrant, retrievers, LLM) sem nenhuma mudança de infra, API, banco ou frontend. GraphRAG fica para uma fatia própria (exige ingestão + armazenamento de grafo).

Referências: `backend/app/core/rag/{base,naive,agentic}.py`, `backend/app/core/prompts/loader.py`, `backend/app/experiments/orchestrator.py`.

## Objetivo

Enriquecer a matriz de experimentos com quatro técnicas de RAG plugáveis — **HyDE**, **Rerank (via LLM)**, **CRAG (corretivo)** e **Compressão contextual** — cada uma como uma classe registrada, com prompts editáveis versionados em `.md`, testadas hermeticamente.

## Decisão base

Todas as técnicas recebem o **mesmo** `retriever` (mesmo `top_k`) e `llm`, exatamente como `naive`/`agentic` recebem hoje via `build_rag(name, retriever=..., llm=..., prompts=...)`. Isso mantém a comparação **justa**: todas partem do mesmo pool recuperado; a técnica difere no que faz com esse pool (ou, no HyDE/CRAG, em qual consulta usa para recuperar). Nenhuma técnica exige chunking novo — chunking está fora do escopo desta fatia.

## Arquitetura

### Padrão comum (por técnica)

Cada técnica segue o padrão de `NaiveRAG`:
- Novo arquivo `backend/app/core/rag/<tecnica>.py` com uma classe `RAG` e `rag_registry.register("<tecnica>", Classe)`.
- Construtor `(self, retriever: Retriever, llm: LLM, prompts: dict[str, str] | None = None, ...params)`. Resolve os prompts com `prompts or load_technique("<tecnica>")`.
- Import da classe em `backend/app/core/rag/__init__.py` (o import é o que registra).
- Entrada em `PROMPT_SPECS` e `DEFAULT_PROMPTS` (`backend/app/core/prompts/loader.py`), declarando cada chave de prompt e seus placeholders obrigatórios.
- Arquivos `backend/prompts/<tecnica>/<chave>.md` com o texto default (idêntico ao `DEFAULT_PROMPTS`).

Todos os prompts em **PT-BR** (texto de conteúdo); identificadores/classes/erros em **inglês**.

Como o orquestrador já faz `rag_kwargs["prompts"] = prompt_snapshot.get(rag_name)` quando `rag_name in PROMPT_SPECS`, os prompts de cada técnica entram no snapshot por experimento automaticamente. `format_context(contexts)` (já existente) monta o bloco de contexto para os prompts.

### 1. HyDE — `hyde`

Hypothetical Document Embeddings: recupera usando uma resposta hipotética em vez da pergunta crua.

- **Prompts:** `hypothesis` (placeholders obrigatórios: `{question}`), `answer` (`{context}`, `{question}`).
- **Fluxo de `answer(query)`:**
  1. `hypo = llm.generate(hypothesis.format(question=query)).strip()`
  2. `contexts = retriever.retrieve(hypo)`
  3. `generated = llm.generate(answer.format(context=format_context(contexts), question=query))`
  4. `return RAGResult(answer=generated.strip(), contexts=contexts)`
- **Custo:** 2 chamadas LLM.

### 2. Rerank via LLM — `rerank`

Recupera o pool, o LLM reordena por relevância, responde com os melhores.

- **Prompts:** `rerank` (`{question}`, `{documents}`), `answer` (`{context}`, `{question}`).
- **Param:** `keep_n: int = 3`.
- **Fluxo de `answer(query)`:**
  1. `contexts = retriever.retrieve(query)`. Se vazio, responde direto (sem rerank).
  2. Monta `documents` = lista numerada `[0] <texto>\n[1] <texto>...` a partir de `contexts`.
  3. `ranking_text = llm.generate(rerank.format(question=query, documents=documents))`.
  4. `order = _parse_ranking(ranking_text, n=len(contexts))` — extrai inteiros na ordem em que aparecem; descarta repetidos e fora de `[0, n)`; ao final acrescenta os índices ausentes na ordem original (garante permutação completa). Se nada parseável, `order = list(range(n))`.
  5. `reranked = [contexts[i] for i in order][:keep_n]`.
  6. `generated = llm.generate(answer.format(context=format_context(reranked), question=query))`.
  7. `return RAGResult(answer=generated.strip(), contexts=reranked)`.
- **Custo:** 2 chamadas LLM.
- `_parse_ranking` é uma função de módulo, testável isoladamente.

### 3. CRAG corretivo — `crag`

Avalia o contexto; se insuficiente, reescreve a consulta e recupera de novo antes de responder.

- **Prompts:** `grade` (`{question}`, `{context}`), `rewrite` (`{question}`), `answer` (`{context}`, `{question}`).
- **Param:** `max_corrections: int = 1`.
- **Convenção de `grade`:** o prompt instrui o LLM a responder começando com `SUFICIENTE` ou `INSUFICIENTE`. O código decide via `verdict.strip().upper().startswith("INSUFICIENTE")` → precisa corrigir; qualquer outra coisa (incl. `SUFICIENTE`) → segue para responder.
- **Fluxo de `answer(query)`:**
  1. `current_query = query`; `contexts = retriever.retrieve(current_query)`.
  2. Repete até `max_corrections` vezes: `verdict = llm.generate(grade.format(question=query, context=format_context(contexts)))`. Se **não** for insuficiente → `break`. Senão: `current_query = llm.generate(rewrite.format(question=query)).strip()`; `contexts = retriever.retrieve(current_query)`.
  3. `generated = llm.generate(answer.format(context=format_context(contexts), question=query))`.
  4. `return RAGResult(answer=generated.strip(), contexts=contexts)`.
- A correção **substitui** o pool (usa a última recuperação), não acumula.
- **Custo:** 2–3 chamadas LLM (com `max_corrections=1`: grade + [rewrite] + answer).

### 4. Compressão contextual — `compression`

Condensa o pool recuperado só no que é relevante à pergunta, antes de responder.

- **Prompts:** `compress` (`{question}`, `{context}`), `answer` (`{context}`, `{question}`).
- **Fluxo de `answer(query)`:**
  1. `contexts = retriever.retrieve(query)`. Se vazio, responde direto.
  2. `compressed_text = llm.generate(compress.format(question=query, context=format_context(contexts))).strip()`.
  3. `compressed_contexts = [{"text": compressed_text, "score": 1.0, "source": "compression"}]`.
  4. `generated = llm.generate(answer.format(context=compressed_text, question=query))`.
  5. `return RAGResult(answer=generated.strip(), contexts=compressed_contexts)`.
- Decisão: **uma** chamada de compressão sobre o bloco inteiro (não uma por trecho) para economizar contra os limites de taxa do gemini. O `RAGResult.contexts` passa a ter um único contexto condensado (é o que efetivamente alimentou a resposta; as métricas de contexto avaliam esse extrato).
- **Custo:** 2 chamadas LLM.

## Prompts (conteúdo default, PT-BR)

Cada `DEFAULT_PROMPTS[<tecnica>][<chave>]` recebe um texto PT-BR com os placeholders exigidos e é espelhado em `backend/prompts/<tecnica>/<chave>.md`. Os textos exatos ficam no plano de implementação. Requisitos de placeholder (validados por `validate_placeholders`):
- `hyde`: `hypothesis`→{question}; `answer`→{context,question}.
- `rerank`: `rerank`→{question,documents}; `answer`→{context,question}.
- `crag`: `grade`→{question,context}; `rewrite`→{question}; `answer`→{context,question}.
- `compression`: `compress`→{question,context}; `answer`→{context,question}.

## Tratamento de erros

- Pool vazio (coleção sem hits): `hyde`/`rerank`/`compression`/`crag` ainda respondem — `rerank`/`compression` pulam a etapa e vão direto ao `answer` com contexto vazio; `format_context([])` devolve string vazia.
- Parsing do `rerank`: entrada não-numérica ou parcial → completa com a ordem original; nunca levanta.
- Falha de LLM (rede/gemini 503): propaga como hoje — o orquestrador já tem retry progressivo (3× com espera) por questão. Nenhum tratamento novo aqui.
- Prompt editado com placeholder inválido: já barrado por `validate_placeholders` no `save_prompt` (comportamento existente da gestão de prompts).

## Testes

Herméticos, sem rede, no padrão de `backend/tests/test_rag_naive.py` e `test_rag_agentic.py`: um **LLM fake** com respostas roteirizadas (fila ou por-substring, evitando colisões de substring como na lição das fatias B1.1) e um **retriever stub** que devolve contextos fixos.

Por técnica:
- `hyde`: a hipótese gerada é usada como query da recuperação (stub registra a query recebida); resposta final retornada.
- `rerank`: LLM devolve uma ordem (ex.: `"2,0,1"`); asserta que `contexts` saem reordenados e truncados em `keep_n`; teste dedicado de `_parse_ranking` (ordem válida, repetidos, fora de range, lixo → fallback, completa faltantes).
- `crag`: ramo "INSUFICIENTE" → asserta que `rewrite` foi chamado e a segunda recuperação usou a query reescrita; ramo "SUFICIENTE" → asserta que não houve reescrita.
- `compression`: asserta que `contexts` colapsa para um único contexto com o texto comprimido e que a resposta usa esse extrato.
- Registro: um teste garante que `rag_registry.names()` inclui as quatro novas técnicas (e, por consequência, `/options.rags`).
- `load_technique("<tecnica>")` devolve todas as chaves esperadas (cobre `PROMPT_SPECS`/`DEFAULT_PROMPTS`).

## Decisões e trade-offs

- **Mesmo retriever para todas** (não alargar o pool por técnica): comparação justa entre técnicas; `top_k` continua sendo um knob do retriever, não da técnica. Rerank/compressão operam sobre o pool configurado.
- **Rerank e grade via LLM, não cross-encoder:** a imagem Docker só traz o gemini (sem embedders/modelos locais). LLM-reranker é portável e não adiciona dependências.
- **Compressão em 1 chamada:** mais barato contra limites de taxa; custo previsível (2 chamadas). Granularidade por-trecho fica como melhoria futura.
- **CRAG substitui o pool na correção:** mais simples e evita inflar o contexto; `max_corrections=1` limita custo.
- **Zero mudança em API/DB/frontend:** tudo flui do registry + PROMPT_SPECS já existentes; as telas (options, config de chat, gestão de prompts, snapshot por experimento) já leem dessas fontes.

## Fora de escopo

- Chunking novo (as quatro técnicas não precisam; pode ser fatia à parte).
- Rerank por cross-encoder / modelos locais.
- Compressão por-trecho (multi-chamada).
- GraphRAG (ingestão + armazenamento de grafo — fatia própria).
- Qualquer mudança de UI além do que já aparece automaticamente pelo registry.
