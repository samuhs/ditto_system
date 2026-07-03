# Novas técnicas de RAG (HyDE, Rerank, CRAG, Compressão) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adicionar quatro técnicas de RAG plugáveis (HyDE, Rerank via LLM, CRAG corretivo, Compressão contextual), cada uma como classe registrada com prompts editáveis, sem mudança de infra/API/DB/frontend.

**Architecture:** Cada técnica é uma classe em `backend/app/core/rag/<tecnica>.py` implementando `RAG.answer(query) -> RAGResult{answer, contexts}`, recebendo `retriever` + `llm` (+ prompts opcionais), registrada em `rag_registry`. Prompts vivem em `PROMPT_SPECS`/`DEFAULT_PROMPTS` (`prompts/loader.py`) e em `backend/prompts/<tecnica>/*.md`. Como `/options.rags` deriva de `rag_registry.names()` e o orquestrador injeta `prompts=snapshot.get(rag_name) if rag_name in PROMPT_SPECS`, cada técnica aparece automaticamente na matriz de experimentos, na config de chat e na gestão de prompts.

**Tech Stack:** Python 3.13 (venv `backend/.venv`), pytest. Sem novas dependências.

## Global Constraints

- Toda técnica plugável = classe + `rag_registry.register("<nome>", Classe)`; import em `rag/__init__.py` (o import é o que registra).
- Identificadores/classes/docstrings/erros em **inglês**; conteúdo de prompt em **PT-BR**.
- Todas as técnicas recebem o **mesmo** `retriever` (mesmo `top_k`) e `llm` via `build_rag(name, retriever=..., llm=..., prompts=...)`. Nenhuma alarga o pool nem exige chunking novo.
- Cada técnica declara seus prompts em `PROMPT_SPECS` + `DEFAULT_PROMPTS` e cria `backend/prompts/<tecnica>/<chave>.md` com texto idêntico ao default.
- **Prompt de resposta compartilhado (texto PT-BR literal, chave `answer` de todas as 4 técnicas):**
  `Use o contexto abaixo para responder à pergunta. Se o contexto não for suficiente, diga o que for possível.\n\nContexto:\n{context}\n\nPergunta: {question}\n\nResposta:`
  (cada técnica tem sua própria cópia editável dessa chave `answer` — duplicação intencional, são prompts independentes).
- Testes herméticos, sem rede: stub retriever + fake LLM (fila de respostas). Padrão em `backend/tests/test_rag_naive.py`.
- Rodar testes: `cd backend && ./.venv/bin/python -m pytest tests/<arquivo> -v`.
- `load_technique(name)` só funciona se `name` estiver em `PROMPT_SPECS`; `build_rag(name, ...)` só se registrado.

---

### Task 1: HyDE (`hyde`)

**Files:**
- Create: `backend/app/core/rag/hyde.py`
- Create: `backend/prompts/hyde/hypothesis.md`, `backend/prompts/hyde/answer.md`
- Modify: `backend/app/core/rag/__init__.py`
- Modify: `backend/app/core/prompts/loader.py` (`PROMPT_SPECS`, `DEFAULT_PROMPTS`)
- Test: `backend/tests/test_rag_hyde.py`

**Interfaces:**
- Consumes: `RAG`, `RAGResult`, `format_context`, `rag_registry` (de `app.core.rag.base`); `Retriever` (`app.core.retrieval.base`); `LLM` (`app.core.llm.base`); `load_technique` (`app.core.prompts`).
- Produces: `HydeRAG(retriever, llm, prompts=None)` registrada como `"hyde"`; prompts `hyde/hypothesis` (`{question}`) e `hyde/answer` (`{context}`, `{question}`).

- [ ] **Step 1: Write the failing test**

Criar `backend/tests/test_rag_hyde.py`:

```python
"""Tests for HydeRAG."""
from app.core.prompts import load_technique
from app.core.rag.base import RAG, build_rag, rag_registry
from app.core.rag.hyde import HydeRAG


class _RecordingRetriever:
    def __init__(self, docs):
        self._docs = docs
        self.queries = []

    def retrieve(self, query):
        self.queries.append(query)
        return list(self._docs)


class _QueueLLM:
    def __init__(self, responses):
        self._responses = list(responses)
        self.prompts = []

    def generate(self, prompt):
        self.prompts.append(prompt)
        return self._responses.pop(0)


_DOCS = [{"text": "A praça central fica no centro.", "score": 0.9}]


def test_hyde_retrieves_with_hypothesis_not_raw_query():
    retriever = _RecordingRetriever(_DOCS)
    llm = _QueueLLM(["Hipotese: a praca central e o coracao da cidade.", "Resposta final."])
    rag = HydeRAG(retriever, llm)
    result = rag.answer("Onde fica o centro?")
    assert retriever.queries == ["Hipotese: a praca central e o coracao da cidade."]
    assert result.answer == "Resposta final."
    assert len(result.contexts) == 1


def test_hyde_registered_and_built():
    assert "hyde" in rag_registry.names()
    rag = build_rag("hyde", retriever=_RecordingRetriever(_DOCS), llm=_QueueLLM(["h", "a"]))
    assert isinstance(rag, RAG)


def test_hyde_prompts_have_expected_keys():
    assert set(load_technique("hyde").keys()) == {"hypothesis", "answer"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_rag_hyde.py -v`
Expected: FAIL — `ModuleNotFoundError: app.core.rag.hyde` (module não existe).

- [ ] **Step 3: Create the technique class**

Criar `backend/app/core/rag/hyde.py`:

```python
"""HyDE RAG: retrieve using a hypothetical document, then answer."""
from app.core.llm.base import LLM
from app.core.prompts import load_technique
from app.core.rag.base import RAG, RAGResult, format_context, rag_registry
from app.core.retrieval.base import Retriever


class HydeRAG(RAG):
    """Generate a hypothetical passage, retrieve with it, then answer."""

    def __init__(
        self, retriever: Retriever, llm: LLM, prompts: dict[str, str] | None = None
    ) -> None:
        self._retriever = retriever
        self._llm = llm
        resolved = prompts or load_technique("hyde")
        self._hypothesis_prompt = resolved["hypothesis"]
        self._answer_prompt = resolved["answer"]

    def answer(self, query: str) -> RAGResult:
        """Retrieve with a hypothetical document, then generate a grounded answer."""
        hypo = self._llm.generate(
            self._hypothesis_prompt.format(question=query)
        ).strip()
        contexts = self._retriever.retrieve(hypo)
        generated = self._llm.generate(
            self._answer_prompt.format(
                context=format_context(contexts), question=query
            )
        )
        return RAGResult(answer=generated.strip(), contexts=contexts)


rag_registry.register("hyde", HydeRAG)
```

- [ ] **Step 4: Register in the package `__init__`**

Em `backend/app/core/rag/__init__.py`: adicionar `from app.core.rag.hyde import HydeRAG` junto aos outros imports, e `"HydeRAG",` ao `__all__`.

- [ ] **Step 5: Add prompt specs and defaults**

Em `backend/app/core/prompts/loader.py`, adicionar ao dict `PROMPT_SPECS` (após a entrada `multi_query`):

```python
    "hyde": {"hypothesis": {"question"}, "answer": {"context", "question"}},
```

E ao dict `DEFAULT_PROMPTS` (após a entrada `multi_query`):

```python
    "hyde": {
        "hypothesis": (
            "Escreva um paragrafo hipotetico, como se fosse um trecho de documento, "
            "que responderia a pergunta abaixo. Escreva como um texto informativo "
            "direto, sem dizer que e hipotetico.\n\nPergunta: {question}\n\nParagrafo:"
        ),
        "answer": (
            "Use o contexto abaixo para responder a pergunta. Se o contexto nao for "
            "suficiente, diga o que for possivel.\n\nContexto:\n{context}\n\n"
            "Pergunta: {question}\n\nResposta:"
        ),
    },
```

- [ ] **Step 6: Create the .md prompt files**

Criar `backend/prompts/hyde/hypothesis.md` com exatamente o texto default de `hypothesis`:

```
Escreva um paragrafo hipotetico, como se fosse um trecho de documento, que responderia a pergunta abaixo. Escreva como um texto informativo direto, sem dizer que e hipotetico.

Pergunta: {question}

Paragrafo:
```

Criar `backend/prompts/hyde/answer.md` com o texto default de `answer`:

```
Use o contexto abaixo para responder a pergunta. Se o contexto nao for suficiente, diga o que for possivel.

Contexto:
{context}

Pergunta: {question}

Resposta:
```

- [ ] **Step 7: Run test to verify it passes**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_rag_hyde.py -v`
Expected: PASS (3 passed).

- [ ] **Step 8: Commit**

```bash
git add backend/app/core/rag/hyde.py backend/app/core/rag/__init__.py backend/app/core/prompts/loader.py backend/prompts/hyde backend/tests/test_rag_hyde.py
git commit -m "feat(rag): add HyDE technique"
```

---

### Task 2: Rerank via LLM (`rerank`)

**Files:**
- Create: `backend/app/core/rag/rerank.py`
- Create: `backend/prompts/rerank/rerank.md`, `backend/prompts/rerank/answer.md`
- Modify: `backend/app/core/rag/__init__.py`
- Modify: `backend/app/core/prompts/loader.py`
- Test: `backend/tests/test_rag_rerank.py`

**Interfaces:**
- Consumes: mesmos de Task 1.
- Produces: `RerankRAG(retriever, llm, prompts=None, keep_n=3)` registrada como `"rerank"`; função de módulo `_parse_ranking(text: str, n: int) -> list[int]`; prompts `rerank/rerank` (`{question}`, `{documents}`) e `rerank/answer` (`{context}`, `{question}`).

- [ ] **Step 1: Write the failing test**

Criar `backend/tests/test_rag_rerank.py`:

```python
"""Tests for RerankRAG and _parse_ranking."""
import pytest

from app.core.prompts import load_technique
from app.core.rag.base import RAG, build_rag, rag_registry
from app.core.rag.rerank import RerankRAG, _parse_ranking


class _StubRetriever:
    def __init__(self, docs):
        self._docs = docs

    def retrieve(self, query):
        return list(self._docs)


class _QueueLLM:
    def __init__(self, responses):
        self._responses = list(responses)
        self.prompts = []

    def generate(self, prompt):
        self.prompts.append(prompt)
        return self._responses.pop(0)


def _docs(n):
    return [{"text": f"doc{i}", "score": 1.0 - i * 0.1} for i in range(n)]


@pytest.mark.parametrize("text,n,expected", [
    ("2,0,1", 3, [2, 0, 1]),
    ("1", 3, [1, 0, 2]),
    ("5,9", 2, [0, 1]),
    ("abc", 2, [0, 1]),
    ("1,1,0", 2, [1, 0]),
])
def test_parse_ranking(text, n, expected):
    assert _parse_ranking(text, n) == expected


def test_rerank_reorders_and_truncates():
    retriever = _StubRetriever(_docs(3))
    llm = _QueueLLM(["2,0,1", "Resposta."])
    rag = RerankRAG(retriever, llm, keep_n=2)
    result = rag.answer("pergunta?")
    assert [c["text"] for c in result.contexts] == ["doc2", "doc0"]
    assert result.answer == "Resposta."


def test_rerank_empty_pool_skips_rerank():
    retriever = _StubRetriever([])
    llm = _QueueLLM(["Resposta sem contexto."])
    rag = RerankRAG(retriever, llm)
    result = rag.answer("pergunta?")
    assert result.contexts == []
    assert result.answer == "Resposta sem contexto."


def test_rerank_registered_and_prompts():
    assert "rerank" in rag_registry.names()
    rag = build_rag("rerank", retriever=_StubRetriever(_docs(1)), llm=_QueueLLM(["0", "a"]))
    assert isinstance(rag, RAG)
    assert set(load_technique("rerank").keys()) == {"rerank", "answer"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_rag_rerank.py -v`
Expected: FAIL — `ModuleNotFoundError: app.core.rag.rerank`.

- [ ] **Step 3: Create the technique class**

Criar `backend/app/core/rag/rerank.py`:

```python
"""Rerank RAG: retrieve, let the LLM reorder, answer with the top ones."""
import re

from app.core.llm.base import LLM
from app.core.prompts import load_technique
from app.core.rag.base import RAG, RAGResult, format_context, rag_registry
from app.core.retrieval.base import Retriever


def _parse_ranking(text: str, n: int) -> list[int]:
    """Parse a ranking string into a full permutation of range(n).

    Extract integers in order, drop duplicates and out-of-range values,
    then append any missing indices in natural order.
    """
    order: list[int] = []
    for token in re.findall(r"\d+", text):
        i = int(token)
        if 0 <= i < n and i not in order:
            order.append(i)
    for i in range(n):
        if i not in order:
            order.append(i)
    return order


class RerankRAG(RAG):
    """Retrieve a pool, rerank it with the LLM, answer with the top keep_n."""

    def __init__(
        self,
        retriever: Retriever,
        llm: LLM,
        prompts: dict[str, str] | None = None,
        keep_n: int = 3,
    ) -> None:
        self._retriever = retriever
        self._llm = llm
        self._keep_n = keep_n
        resolved = prompts or load_technique("rerank")
        self._rerank_prompt = resolved["rerank"]
        self._answer_prompt = resolved["answer"]

    def answer(self, query: str) -> RAGResult:
        """Retrieve, rerank via the LLM, and answer with the top contexts."""
        contexts = self._retriever.retrieve(query)
        if contexts:
            documents = "\n".join(
                f"[{i}] {c.get('text', '')}" for i, c in enumerate(contexts)
            )
            ranking = self._llm.generate(
                self._rerank_prompt.format(question=query, documents=documents)
            )
            order = _parse_ranking(ranking, len(contexts))
            contexts = [contexts[i] for i in order][: self._keep_n]
        generated = self._llm.generate(
            self._answer_prompt.format(
                context=format_context(contexts), question=query
            )
        )
        return RAGResult(answer=generated.strip(), contexts=contexts)


rag_registry.register("rerank", RerankRAG)
```

- [ ] **Step 4: Register in the package `__init__`**

Em `backend/app/core/rag/__init__.py`: adicionar `from app.core.rag.rerank import RerankRAG` e `"RerankRAG",` ao `__all__`.

- [ ] **Step 5: Add prompt specs and defaults**

Em `backend/app/core/prompts/loader.py`, adicionar ao `PROMPT_SPECS`:

```python
    "rerank": {"rerank": {"question", "documents"}, "answer": {"context", "question"}},
```

E ao `DEFAULT_PROMPTS`:

```python
    "rerank": {
        "rerank": (
            "Abaixo ha documentos numerados. Ordene-os do mais relevante ao menos "
            "relevante para responder a pergunta. Responda apenas com os numeros "
            "separados por virgula, do mais para o menos relevante (ex.: 2,0,1)."
            "\n\nPergunta: {question}\n\nDocumentos:\n{documents}\n\nOrdem:"
        ),
        "answer": (
            "Use o contexto abaixo para responder a pergunta. Se o contexto nao for "
            "suficiente, diga o que for possivel.\n\nContexto:\n{context}\n\n"
            "Pergunta: {question}\n\nResposta:"
        ),
    },
```

- [ ] **Step 6: Create the .md prompt files**

Criar `backend/prompts/rerank/rerank.md`:

```
Abaixo ha documentos numerados. Ordene-os do mais relevante ao menos relevante para responder a pergunta. Responda apenas com os numeros separados por virgula, do mais para o menos relevante (ex.: 2,0,1).

Pergunta: {question}

Documentos:
{documents}

Ordem:
```

Criar `backend/prompts/rerank/answer.md`:

```
Use o contexto abaixo para responder a pergunta. Se o contexto nao for suficiente, diga o que for possivel.

Contexto:
{context}

Pergunta: {question}

Resposta:
```

- [ ] **Step 7: Run test to verify it passes**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_rag_rerank.py -v`
Expected: PASS (9 passed — 5 parametrizados + 4).

- [ ] **Step 8: Commit**

```bash
git add backend/app/core/rag/rerank.py backend/app/core/rag/__init__.py backend/app/core/prompts/loader.py backend/prompts/rerank backend/tests/test_rag_rerank.py
git commit -m "feat(rag): add LLM rerank technique"
```

---

### Task 3: CRAG corretivo (`crag`)

**Files:**
- Create: `backend/app/core/rag/crag.py`
- Create: `backend/prompts/crag/grade.md`, `backend/prompts/crag/rewrite.md`, `backend/prompts/crag/answer.md`
- Modify: `backend/app/core/rag/__init__.py`
- Modify: `backend/app/core/prompts/loader.py`
- Test: `backend/tests/test_rag_crag.py`

**Interfaces:**
- Consumes: mesmos de Task 1.
- Produces: `CragRAG(retriever, llm, prompts=None, max_corrections=1)` registrada como `"crag"`; prompts `crag/grade` (`{question}`, `{context}`), `crag/rewrite` (`{question}`), `crag/answer` (`{context}`, `{question}`). Convenção: o grade começa com `SUFICIENTE`/`INSUFICIENTE`; o código corrige quando `verdict.strip().upper().startswith("INSUFICIENTE")`.

- [ ] **Step 1: Write the failing test**

Criar `backend/tests/test_rag_crag.py`:

```python
"""Tests for CragRAG."""
from app.core.prompts import load_technique
from app.core.rag.base import RAG, build_rag, rag_registry
from app.core.rag.crag import CragRAG


class _RecordingRetriever:
    def __init__(self, docs):
        self._docs = docs
        self.queries = []

    def retrieve(self, query):
        self.queries.append(query)
        return list(self._docs)


class _QueueLLM:
    def __init__(self, responses):
        self._responses = list(responses)

    def generate(self, prompt):
        return self._responses.pop(0)


_DOCS = [{"text": "contexto", "score": 0.9}]


def test_crag_sufficient_does_not_rewrite():
    retriever = _RecordingRetriever(_DOCS)
    llm = _QueueLLM(["SUFICIENTE, o contexto responde.", "Resposta final."])
    rag = CragRAG(retriever, llm)
    result = rag.answer("pergunta original?")
    assert retriever.queries == ["pergunta original?"]
    assert result.answer == "Resposta final."


def test_crag_insufficient_rewrites_and_reretrieves():
    retriever = _RecordingRetriever(_DOCS)
    llm = _QueueLLM(["INSUFICIENTE, falta detalhe.", "consulta reescrita", "Resposta final."])
    rag = CragRAG(retriever, llm, max_corrections=1)
    result = rag.answer("pergunta original?")
    assert retriever.queries == ["pergunta original?", "consulta reescrita"]
    assert result.answer == "Resposta final."


def test_crag_registered_and_prompts():
    assert "crag" in rag_registry.names()
    rag = build_rag("crag", retriever=_RecordingRetriever(_DOCS), llm=_QueueLLM(["SUFICIENTE", "a"]))
    assert isinstance(rag, RAG)
    assert set(load_technique("crag").keys()) == {"grade", "rewrite", "answer"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_rag_crag.py -v`
Expected: FAIL — `ModuleNotFoundError: app.core.rag.crag`.

- [ ] **Step 3: Create the technique class**

Criar `backend/app/core/rag/crag.py`:

```python
"""Corrective RAG: grade the context, rewrite and re-retrieve if insufficient."""
from app.core.llm.base import LLM
from app.core.prompts import load_technique
from app.core.rag.base import RAG, RAGResult, format_context, rag_registry
from app.core.retrieval.base import Retriever

_INSUFFICIENT = "INSUFICIENTE"


class CragRAG(RAG):
    """Retrieve, grade; if insufficient, rewrite the query and retry, then answer."""

    def __init__(
        self,
        retriever: Retriever,
        llm: LLM,
        prompts: dict[str, str] | None = None,
        max_corrections: int = 1,
    ) -> None:
        self._retriever = retriever
        self._llm = llm
        self._max_corrections = max_corrections
        resolved = prompts or load_technique("crag")
        self._grade_prompt = resolved["grade"]
        self._rewrite_prompt = resolved["rewrite"]
        self._answer_prompt = resolved["answer"]

    def answer(self, query: str) -> RAGResult:
        """Grade the retrieved context and correct the query if it is insufficient."""
        contexts = self._retriever.retrieve(query)
        for _ in range(self._max_corrections):
            verdict = self._llm.generate(
                self._grade_prompt.format(
                    question=query, context=format_context(contexts)
                )
            )
            if not verdict.strip().upper().startswith(_INSUFFICIENT):
                break
            new_query = self._llm.generate(
                self._rewrite_prompt.format(question=query)
            ).strip()
            contexts = self._retriever.retrieve(new_query)
        generated = self._llm.generate(
            self._answer_prompt.format(
                context=format_context(contexts), question=query
            )
        )
        return RAGResult(answer=generated.strip(), contexts=contexts)


rag_registry.register("crag", CragRAG)
```

- [ ] **Step 4: Register in the package `__init__`**

Em `backend/app/core/rag/__init__.py`: adicionar `from app.core.rag.crag import CragRAG` e `"CragRAG",` ao `__all__`.

- [ ] **Step 5: Add prompt specs and defaults**

Em `backend/app/core/prompts/loader.py`, adicionar ao `PROMPT_SPECS`:

```python
    "crag": {
        "grade": {"question", "context"},
        "rewrite": {"question"},
        "answer": {"context", "question"},
    },
```

E ao `DEFAULT_PROMPTS`:

```python
    "crag": {
        "grade": (
            "Avalie se o contexto abaixo e suficiente para responder a pergunta. "
            "Responda comecando exatamente com 'SUFICIENTE' ou 'INSUFICIENTE', "
            "seguido de uma breve justificativa.\n\nPergunta: {question}\n\n"
            "Contexto:\n{context}\n\nAvaliacao:"
        ),
        "rewrite": (
            "A busca anterior nao trouxe contexto suficiente. Reescreva a pergunta "
            "como uma consulta de busca melhor e mais especifica. Responda apenas "
            "com a nova consulta.\n\nPergunta: {question}\n\nNova consulta:"
        ),
        "answer": (
            "Use o contexto abaixo para responder a pergunta. Se o contexto nao for "
            "suficiente, diga o que for possivel.\n\nContexto:\n{context}\n\n"
            "Pergunta: {question}\n\nResposta:"
        ),
    },
```

- [ ] **Step 6: Create the .md prompt files**

Criar `backend/prompts/crag/grade.md`:

```
Avalie se o contexto abaixo e suficiente para responder a pergunta. Responda comecando exatamente com 'SUFICIENTE' ou 'INSUFICIENTE', seguido de uma breve justificativa.

Pergunta: {question}

Contexto:
{context}

Avaliacao:
```

Criar `backend/prompts/crag/rewrite.md`:

```
A busca anterior nao trouxe contexto suficiente. Reescreva a pergunta como uma consulta de busca melhor e mais especifica. Responda apenas com a nova consulta.

Pergunta: {question}

Nova consulta:
```

Criar `backend/prompts/crag/answer.md`:

```
Use o contexto abaixo para responder a pergunta. Se o contexto nao for suficiente, diga o que for possivel.

Contexto:
{context}

Pergunta: {question}

Resposta:
```

- [ ] **Step 7: Run test to verify it passes**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_rag_crag.py -v`
Expected: PASS (3 passed).

- [ ] **Step 8: Commit**

```bash
git add backend/app/core/rag/crag.py backend/app/core/rag/__init__.py backend/app/core/prompts/loader.py backend/prompts/crag backend/tests/test_rag_crag.py
git commit -m "feat(rag): add corrective RAG (CRAG) technique"
```

---

### Task 4: Compressão contextual (`compression`)

**Files:**
- Create: `backend/app/core/rag/compression.py`
- Create: `backend/prompts/compression/compress.md`, `backend/prompts/compression/answer.md`
- Modify: `backend/app/core/rag/__init__.py`
- Modify: `backend/app/core/prompts/loader.py`
- Test: `backend/tests/test_rag_compression.py`

**Interfaces:**
- Consumes: mesmos de Task 1.
- Produces: `CompressionRAG(retriever, llm, prompts=None)` registrada como `"compression"`; prompts `compression/compress` (`{question}`, `{context}`), `compression/answer` (`{context}`, `{question}`). `RAGResult.contexts` colapsa em um único contexto `{"text": <extrato>, "score": 1.0, "source": "compression"}`.

- [ ] **Step 1: Write the failing test**

Criar `backend/tests/test_rag_compression.py`:

```python
"""Tests for CompressionRAG."""
from app.core.prompts import load_technique
from app.core.rag.base import RAG, build_rag, rag_registry
from app.core.rag.compression import CompressionRAG


class _StubRetriever:
    def __init__(self, docs):
        self._docs = docs

    def retrieve(self, query):
        return list(self._docs)


class _QueueLLM:
    def __init__(self, responses):
        self._responses = list(responses)
        self.prompts = []

    def generate(self, prompt):
        self.prompts.append(prompt)
        return self._responses.pop(0)


_DOCS = [
    {"text": "Trecho relevante A.", "score": 0.9},
    {"text": "Ruido irrelevante B.", "score": 0.5},
]


def test_compression_collapses_to_single_context():
    retriever = _StubRetriever(_DOCS)
    llm = _QueueLLM(["Extrato: apenas A.", "Resposta final."])
    rag = CompressionRAG(retriever, llm)
    result = rag.answer("pergunta?")
    assert len(result.contexts) == 1
    assert result.contexts[0]["text"] == "Extrato: apenas A."
    assert "Extrato: apenas A." in llm.prompts[1]
    assert result.answer == "Resposta final."


def test_compression_empty_pool_answers_without_compress():
    retriever = _StubRetriever([])
    llm = _QueueLLM(["Resposta sem contexto."])
    rag = CompressionRAG(retriever, llm)
    result = rag.answer("pergunta?")
    assert result.contexts == []
    assert result.answer == "Resposta sem contexto."


def test_compression_registered_and_prompts():
    assert "compression" in rag_registry.names()
    rag = build_rag("compression", retriever=_StubRetriever(_DOCS), llm=_QueueLLM(["c", "a"]))
    assert isinstance(rag, RAG)
    assert set(load_technique("compression").keys()) == {"compress", "answer"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_rag_compression.py -v`
Expected: FAIL — `ModuleNotFoundError: app.core.rag.compression`.

- [ ] **Step 3: Create the technique class**

Criar `backend/app/core/rag/compression.py`:

```python
"""Contextual compression RAG: condense the retrieved context, then answer."""
from app.core.llm.base import LLM
from app.core.prompts import load_technique
from app.core.rag.base import RAG, RAGResult, format_context, rag_registry
from app.core.retrieval.base import Retriever


class CompressionRAG(RAG):
    """Compress the retrieved pool into a focused extract, then answer on it."""

    def __init__(
        self, retriever: Retriever, llm: LLM, prompts: dict[str, str] | None = None
    ) -> None:
        self._retriever = retriever
        self._llm = llm
        resolved = prompts or load_technique("compression")
        self._compress_prompt = resolved["compress"]
        self._answer_prompt = resolved["answer"]

    def answer(self, query: str) -> RAGResult:
        """Compress the retrieved context in one call, then answer on the extract."""
        contexts = self._retriever.retrieve(query)
        if not contexts:
            generated = self._llm.generate(
                self._answer_prompt.format(context="", question=query)
            )
            return RAGResult(answer=generated.strip(), contexts=[])
        compressed_text = self._llm.generate(
            self._compress_prompt.format(
                question=query, context=format_context(contexts)
            )
        ).strip()
        compressed_contexts = [
            {"text": compressed_text, "score": 1.0, "source": "compression"}
        ]
        generated = self._llm.generate(
            self._answer_prompt.format(context=compressed_text, question=query)
        )
        return RAGResult(answer=generated.strip(), contexts=compressed_contexts)


rag_registry.register("compression", CompressionRAG)
```

- [ ] **Step 4: Register in the package `__init__`**

Em `backend/app/core/rag/__init__.py`: adicionar `from app.core.rag.compression import CompressionRAG` e `"CompressionRAG",` ao `__all__`.

- [ ] **Step 5: Add prompt specs and defaults**

Em `backend/app/core/prompts/loader.py`, adicionar ao `PROMPT_SPECS`:

```python
    "compression": {
        "compress": {"question", "context"},
        "answer": {"context", "question"},
    },
```

E ao `DEFAULT_PROMPTS`:

```python
    "compression": {
        "compress": (
            "Extraia do contexto abaixo apenas as partes relevantes para responder "
            "a pergunta, descartando o que for irrelevante. Preserve os fatos; nao "
            "invente. Responda apenas com o extrato condensado.\n\n"
            "Pergunta: {question}\n\nContexto:\n{context}\n\nExtrato relevante:"
        ),
        "answer": (
            "Use o contexto abaixo para responder a pergunta. Se o contexto nao for "
            "suficiente, diga o que for possivel.\n\nContexto:\n{context}\n\n"
            "Pergunta: {question}\n\nResposta:"
        ),
    },
```

- [ ] **Step 6: Create the .md prompt files**

Criar `backend/prompts/compression/compress.md`:

```
Extraia do contexto abaixo apenas as partes relevantes para responder a pergunta, descartando o que for irrelevante. Preserve os fatos; nao invente. Responda apenas com o extrato condensado.

Pergunta: {question}

Contexto:
{context}

Extrato relevante:
```

Criar `backend/prompts/compression/answer.md`:

```
Use o contexto abaixo para responder a pergunta. Se o contexto nao for suficiente, diga o que for possivel.

Contexto:
{context}

Pergunta: {question}

Resposta:
```

- [ ] **Step 7: Run the full RAG + options suite to verify integration**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_rag_compression.py tests/test_rag_hyde.py tests/test_rag_rerank.py tests/test_rag_crag.py -v`
Expected: PASS (todas).

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_options_api.py -q 2>/dev/null || cd backend && ./.venv/bin/python -c "from app.core.rag import build_rag; from app.core.rag.base import rag_registry; print(sorted(rag_registry.names()))"`
Expected: a lista inclui `compression, crag, hyde, rerank` além de `agentic, naive`.

- [ ] **Step 8: Commit**

```bash
git add backend/app/core/rag/compression.py backend/app/core/rag/__init__.py backend/app/core/prompts/loader.py backend/prompts/compression backend/tests/test_rag_compression.py
git commit -m "feat(rag): add contextual compression technique"
```

---

## Self-Review

**Spec coverage:**
- HyDE (`hyde`), fluxo hipótese→busca→responde, prompts `hypothesis`/`answer` → Task 1. ✓
- Rerank (`rerank`), `keep_n=3`, `_parse_ranking` robusto, pool vazio → Task 2. ✓
- CRAG (`crag`), grade SUFICIENTE/INSUFICIENTE, rewrite+re-retrieve, `max_corrections=1`, substitui pool → Task 3. ✓
- Compressão (`compression`), 1 chamada, colapsa contexts, pool vazio → Task 4. ✓
- Registro em `rag_registry` + import em `__init__` + `PROMPT_SPECS`/`DEFAULT_PROMPTS` + `.md` → todas as tasks. ✓
- Propagação automática a `/options.rags` (teste de registro), gestão de prompts e snapshot por experimento (via `PROMPT_SPECS`) → coberto pelos testes de registro/`load_technique` e pelo wiring existente. ✓
- Testes herméticos (stub retriever + fake LLM em fila) → todas as tasks. ✓

**Placeholder scan:** nenhum TBD/TODO; todo passo com código completo e comando + saída esperada. Os prompts usam texto sem acento para evitar divergência de encoding entre `DEFAULT_PROMPTS` e os `.md` (o `load_prompt` faz só `rstrip("\n")`, então o corpo precisa bater byte a byte para o roundtrip; ASCII elimina o risco).

**Type consistency:** todas as classes implementam `answer(query) -> RAGResult`; `build_rag(name, retriever=, llm=, prompts=)` idêntico ao uso do orquestrador; chaves de prompt em `PROMPT_SPECS` batem com as lidas em cada `__init__` (`resolved["<chave>"]`); `_parse_ranking(text, n) -> list[int]` consistente entre definição e teste. Os `.md` de `answer` são idênticos entre as quatro técnicas (cópias independentes, por design).
