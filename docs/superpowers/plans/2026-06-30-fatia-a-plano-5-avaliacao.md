# Fatia A — Plano 5: Avaliação — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar a avaliação de respostas: um módulo de métricas próprias (sem a lib RAGAS) atrás de interface + registry, cobrindo relevância/fidelidade/precisão/recall de contexto, correção da resposta e ROUGE-L, mais uma função de conveniência que roda um conjunto de métricas sobre uma amostra.

**Architecture:** Um `app/core/vector_math.py` compartilhado (consolida o cálculo de cosseno hoje duplicado). Um módulo `app/core/evaluation/` com a interface `Evaluator` (registry), um `EvalSample` (Pydantic), métricas baseadas em embedding (recebem o embedder por injeção) e uma métrica de overlap (ROUGE-L, pura). Uma função `evaluate_sample(sample, metric_names, embedder)` aplica as métricas selecionadas, pulando as que exigem gabarito quando não há `reference_answer`. Tudo testável sem rede com um embedder fake.

**Tech Stack:** Python 3.11, Pydantic v2, pytest. Sem dependências novas.

## Global Constraints

- **Código em inglês:** identificadores, docstrings e mensagens de erro em inglês. Apenas dados de domínio em PT-BR.
- PEP-8; docstrings nas funções públicas; comentários só quando agregam.
- Toda métrica plugável atrás de interface + registry (reusa `app.core.registry.Registry`).
- Sem duplicação: o cálculo de cosseno fica em `app/core/vector_math.py` e é reusado (retrieval, semantic, evaluation).
- **Testes sem rede:** o embedder é injetado (fake nos testes); nenhuma chamada de API, nenhum download.
- Métricas: `answer_relevancy`, `faithfulness`, `context_precision` (sem gabarito); `context_recall`, `answer_correctness`, `rouge_l` (exigem `reference_answer`). Scores em ponto flutuante; as baseadas em cosseno são truncadas em `[0, 1]` com `max(0.0, valor)`.
- Métricas operacionais (latência, tokens) NÃO são deste plano — são medidas pelo orquestrador no Plano 6.
- venv de dev em `backend/.venv`. Rodar testes: `cd backend && ./.venv/bin/python -m pytest`. Saída pristina (zero warnings).
- Commits frequentes, um por task.

---

## File Structure

```
backend/
  app/core/vector_math.py            # cosine_similarity, cosine_distance (consolidado)
  app/core/retrieval/base.py         # passa a reexportar cosine_similarity de vector_math
  app/core/chunking/semantic.py      # passa a usar cosine_distance de vector_math
  app/core/evaluation/
    __init__.py                      # Evaluator, EvalSample, evaluation_registry, build_evaluator, evaluate_sample
    base.py                          # interface Evaluator (ABC) + EvalSample + Registry + build_evaluator
    embedding_metrics.py             # AnswerRelevancy, Faithfulness, ContextPrecision, ContextRecall, AnswerCorrectness
    overlap_metrics.py               # RougeL
    runner.py                        # evaluate_sample(...)
  tests/
    test_vector_math.py
    test_evaluation_embedding.py
    test_evaluation_overlap.py
    test_evaluation_runner.py
```

---

### Task 1: Consolidar o cosseno + interface de avaliação + métricas de embedding sem gabarito

**Files:**
- Create: `backend/app/core/vector_math.py`
- Modify: `backend/app/core/retrieval/base.py` (reexportar `cosine_similarity` de `vector_math`)
- Modify: `backend/app/core/chunking/semantic.py` (usar `cosine_distance` de `vector_math`)
- Create: `backend/app/core/evaluation/__init__.py`
- Create: `backend/app/core/evaluation/base.py`
- Create: `backend/app/core/evaluation/embedding_metrics.py`
- Create: `backend/tests/test_vector_math.py`
- Create: `backend/tests/test_evaluation_embedding.py`

**Interfaces:**
- Consumes: `app.core.registry.Registry`, `app.core.embedding.base.Embedder`.
- Produces:
  - `app.core.vector_math.cosine_similarity(a, b) -> float` (0 se algum vetor for nulo); `cosine_distance(a, b) -> float` (= 1 - similaridade).
  - `EvalSample` (Pydantic): `question: str`, `answer: str`, `contexts: list[str]`, `reference_answer: str | None = None`.
  - `Evaluator` (ABC) com atributo de classe `requires_reference: bool = False` e método `score(self, sample: EvalSample) -> float`.
  - `evaluation_registry: Registry[type[Evaluator]]`; `build_evaluator(name: str, **kwargs) -> Evaluator`.
  - `AnswerRelevancy(embedder)` → `"answer_relevancy"`; `Faithfulness(embedder)` → `"faithfulness"`; `ContextPrecision(embedder)` → `"context_precision"`. Todas `requires_reference = False`.

- [ ] **Step 1: Escrever o teste de vector_math que falha**

`backend/tests/test_vector_math.py`:

```python
"""Tests for shared vector math helpers."""
from app.core.vector_math import cosine_distance, cosine_similarity


def test_cosine_similarity_identical():
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0


def test_cosine_similarity_orthogonal():
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_cosine_similarity_zero_vector():
    assert cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0


def test_cosine_distance_is_complement():
    assert cosine_distance([1.0, 0.0], [1.0, 0.0]) == 0.0
    assert cosine_distance([1.0, 0.0], [0.0, 1.0]) == 1.0
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_vector_math.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'app.core.vector_math'`.

- [ ] **Step 3: Implementar vector_math e consolidar os usos**

`backend/app/core/vector_math.py`:

```python
"""Shared vector math helpers."""


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Return the cosine similarity between two vectors (0 if either is zero)."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def cosine_distance(a: list[float], b: list[float]) -> float:
    """Return 1 - cosine similarity between two vectors."""
    return 1.0 - cosine_similarity(a, b)
```

Em `backend/app/core/retrieval/base.py`, remova a definição local de `cosine_similarity` e reexporte a compartilhada (mantendo o nome disponível para `mmr.py` e os testes):

```python
from app.core.vector_math import cosine_similarity  # re-exported for retrievers
```

(Garanta que `cosine_similarity` continue em `__all__`/disponível onde já era importado: `app.core.retrieval.base.cosine_similarity` e `app.core.retrieval.cosine_similarity`.)

Em `backend/app/core/chunking/semantic.py`, remova o `_cosine_distance` local e use o compartilhado:

```python
from app.core.vector_math import cosine_distance
```

Substitua as chamadas `_cosine_distance(...)` por `cosine_distance(...)`.

- [ ] **Step 4: Rodar a suíte inteira e ver passar**

Run: `cd backend && ./.venv/bin/python -m pytest -v`
Expected: PASS — os novos testes de vector_math e TODOS os anteriores (retrieval e semantic continuam funcionando via o helper consolidado). Zero warnings.

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/vector_math.py backend/app/core/retrieval/base.py backend/app/core/chunking/semantic.py backend/tests/test_vector_math.py
git commit -m "refactor: consolidate cosine math into core.vector_math"
```

- [ ] **Step 6: Escrever o teste das métricas de embedding que falha**

`backend/tests/test_evaluation_embedding.py`:

```python
"""Tests for embedding-based evaluation metrics (no reference needed)."""
from app.core.evaluation.base import EvalSample, build_evaluator, evaluation_registry
from app.core.evaluation.embedding_metrics import (
    AnswerRelevancy,
    ContextPrecision,
    Faithfulness,
)


class _FakeEmbedder:
    """Embeds text to a 2-dim topic vector: 'square'->[1,0], 'cheese'->[0,1]."""

    def embed_documents(self, texts):
        return [self.embed_query(t) for t in texts]

    def embed_query(self, text):
        t = text.lower()
        x = 1.0 if "square" in t else 0.0
        y = 1.0 if "cheese" in t else 0.0
        if x == 0.0 and y == 0.0:
            return [0.5, 0.5]
        return [x, y]

    @property
    def dimension(self) -> int:
        return 2


def test_answer_relevancy_higher_when_on_topic():
    embedder = _FakeEmbedder()
    metric = AnswerRelevancy(embedder)
    on_topic = metric.score(
        EvalSample(question="Where is the square?", answer="The square is downtown.", contexts=[])
    )
    off_topic = metric.score(
        EvalSample(question="Where is the square?", answer="We sell cheese.", contexts=[])
    )
    assert on_topic > off_topic


def test_faithfulness_higher_when_grounded():
    embedder = _FakeEmbedder()
    metric = Faithfulness(embedder)
    grounded = metric.score(
        EvalSample(question="q", answer="The square is here.", contexts=["The main square map."])
    )
    ungrounded = metric.score(
        EvalSample(question="q", answer="The square is here.", contexts=["We sell cheese."])
    )
    assert grounded > ungrounded


def test_context_precision_averages_relevance():
    embedder = _FakeEmbedder()
    metric = ContextPrecision(embedder)
    score = metric.score(
        EvalSample(
            question="Where is the square?",
            answer="a",
            contexts=["The square map.", "The square plaza."],
        )
    )
    assert score > 0.9


def test_embedding_metrics_registered_and_no_reference():
    assert {"answer_relevancy", "faithfulness", "context_precision"} <= set(
        evaluation_registry.names()
    )
    metric = build_evaluator("faithfulness", embedder=_FakeEmbedder())
    assert metric.requires_reference is False
```

- [ ] **Step 7: Rodar e ver falhar**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_evaluation_embedding.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'app.core.evaluation'`.

- [ ] **Step 8: Implementar a base de avaliação**

`backend/app/core/evaluation/base.py`:

```python
"""Evaluation metric interface, sample model, registry, and factory."""
from abc import ABC, abstractmethod

from pydantic import BaseModel

from app.core.registry import Registry


class EvalSample(BaseModel):
    """One evaluation unit: a question, an answer, its contexts, and an optional reference."""

    question: str
    answer: str
    contexts: list[str]
    reference_answer: str | None = None


class Evaluator(ABC):
    """Minimal interface every evaluation metric implements."""

    requires_reference: bool = False

    @abstractmethod
    def score(self, sample: EvalSample) -> float:
        """Return a metric score for the sample."""


evaluation_registry: Registry[type[Evaluator]] = Registry("evaluation")


def build_evaluator(name: str, **kwargs) -> Evaluator:
    """Instantiate a registered evaluation metric by name."""
    return evaluation_registry.get(name)(**kwargs)
```

- [ ] **Step 9: Implementar as métricas de embedding**

`backend/app/core/evaluation/embedding_metrics.py`:

```python
"""Embedding-based evaluation metrics (cosine similarity of meanings)."""
from app.core.embedding.base import Embedder
from app.core.evaluation.base import EvalSample, Evaluator, evaluation_registry
from app.core.vector_math import cosine_similarity


def _clamp(value: float) -> float:
    """Clamp a similarity to the non-negative [0, 1] range used for scores."""
    return max(0.0, value)


class _EmbeddingMetric(Evaluator):
    """Base class for metrics that embed text and compare with cosine similarity."""

    def __init__(self, embedder: Embedder) -> None:
        self._embedder = embedder


class AnswerRelevancy(_EmbeddingMetric):
    """How well the answer addresses the question."""

    def score(self, sample: EvalSample) -> float:
        """Cosine similarity between the answer and the question."""
        answer_vec = self._embedder.embed_query(sample.answer)
        question_vec = self._embedder.embed_query(sample.question)
        return _clamp(cosine_similarity(answer_vec, question_vec))


class Faithfulness(_EmbeddingMetric):
    """How grounded the answer is in the retrieved context."""

    def score(self, sample: EvalSample) -> float:
        """Cosine similarity between the answer and the joined contexts."""
        if not sample.contexts:
            return 0.0
        answer_vec = self._embedder.embed_query(sample.answer)
        context_vec = self._embedder.embed_query(" ".join(sample.contexts))
        return _clamp(cosine_similarity(answer_vec, context_vec))


class ContextPrecision(_EmbeddingMetric):
    """How relevant the retrieved contexts are to the question."""

    def score(self, sample: EvalSample) -> float:
        """Mean cosine similarity between the question and each context."""
        if not sample.contexts:
            return 0.0
        question_vec = self._embedder.embed_query(sample.question)
        scores = [
            cosine_similarity(question_vec, self._embedder.embed_query(context))
            for context in sample.contexts
        ]
        return _clamp(sum(scores) / len(scores))


evaluation_registry.register("answer_relevancy", AnswerRelevancy)
evaluation_registry.register("faithfulness", Faithfulness)
evaluation_registry.register("context_precision", ContextPrecision)
```

- [ ] **Step 10: Implementar o `__init__.py` parcial**

`backend/app/core/evaluation/__init__.py`:

```python
"""Evaluation package. Importing it registers the built-in metrics."""
from app.core.evaluation.base import (
    EvalSample,
    Evaluator,
    build_evaluator,
    evaluation_registry,
)
from app.core.evaluation.embedding_metrics import (
    AnswerRelevancy,
    ContextPrecision,
    Faithfulness,
)

__all__ = [
    "EvalSample",
    "Evaluator",
    "build_evaluator",
    "evaluation_registry",
    "AnswerRelevancy",
    "ContextPrecision",
    "Faithfulness",
]
```

- [ ] **Step 11: Rodar e ver passar**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_evaluation_embedding.py -v`
Expected: PASS (4 testes). Suíte inteira verde, zero warnings.

- [ ] **Step 12: Commit**

```bash
git add backend/app/core/evaluation backend/tests/test_evaluation_embedding.py
git commit -m "feat: evaluation interface + embedding metrics (relevancy, faithfulness, context precision)"
```

---

### Task 2: Métricas com gabarito (context_recall, answer_correctness, rouge_l)

**Files:**
- Modify: `backend/app/core/evaluation/embedding_metrics.py` (adicionar `ContextRecall`, `AnswerCorrectness`)
- Create: `backend/app/core/evaluation/overlap_metrics.py`
- Modify: `backend/app/core/evaluation/__init__.py` (registrar/exportar)
- Create: `backend/tests/test_evaluation_overlap.py`
- Modify: `backend/tests/test_evaluation_embedding.py` (testes das duas novas métricas com gabarito)

**Interfaces:**
- Consumes: `app.core.evaluation.base`, `app.core.vector_math`, `app.core.embedding.base.Embedder`.
- Produces:
  - `ContextRecall(embedder)` → `"context_recall"`, `requires_reference = True` — cosseno entre `reference_answer` e os contextos concatenados.
  - `AnswerCorrectness(embedder)` → `"answer_correctness"`, `requires_reference = True` — cosseno entre `answer` e `reference_answer`.
  - `RougeL()` → `"rouge_l"`, `requires_reference = True` — F-measure baseada na subsequência comum mais longa (LCS) entre tokens de `answer` e `reference_answer`.

- [ ] **Step 1: Escrever os testes que falham**

`backend/tests/test_evaluation_overlap.py`:

```python
"""Tests for overlap-based evaluation metrics (ROUGE-L)."""
from app.core.evaluation.base import EvalSample, evaluation_registry
from app.core.evaluation.overlap_metrics import RougeL


def test_rouge_l_identical_is_one():
    metric = RougeL()
    sample = EvalSample(
        question="q", answer="the cat sat", contexts=[], reference_answer="the cat sat"
    )
    assert metric.score(sample) == 1.0


def test_rouge_l_partial_overlap_between_zero_and_one():
    metric = RougeL()
    sample = EvalSample(
        question="q",
        answer="the cat sat on the mat",
        contexts=[],
        reference_answer="the dog sat",
    )
    score = metric.score(sample)
    assert 0.0 < score < 1.0


def test_rouge_l_disjoint_is_zero():
    metric = RougeL()
    sample = EvalSample(
        question="q", answer="alpha beta", contexts=[], reference_answer="gamma delta"
    )
    assert metric.score(sample) == 0.0


def test_rouge_l_requires_reference_and_registered():
    assert "rouge_l" in evaluation_registry.names()
    assert RougeL.requires_reference is True
```

Acrescente a `backend/tests/test_evaluation_embedding.py` (reusando o `_FakeEmbedder`):

```python
from app.core.evaluation.embedding_metrics import AnswerCorrectness, ContextRecall


def test_answer_correctness_higher_when_matching_reference():
    embedder = _FakeEmbedder()
    metric = AnswerCorrectness(embedder)
    assert metric.requires_reference is True
    close = metric.score(
        EvalSample(question="q", answer="the square", contexts=[], reference_answer="the square plaza")
    )
    far = metric.score(
        EvalSample(question="q", answer="the square", contexts=[], reference_answer="the cheese shop")
    )
    assert close > far


def test_context_recall_uses_reference_and_context():
    embedder = _FakeEmbedder()
    metric = ContextRecall(embedder)
    assert metric.requires_reference is True
    covered = metric.score(
        EvalSample(
            question="q",
            answer="a",
            contexts=["the square map"],
            reference_answer="the square plaza",
        )
    )
    assert covered > 0.9
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_evaluation_overlap.py tests/test_evaluation_embedding.py -v`
Expected: FAIL (`overlap_metrics` não existe; `ContextRecall`/`AnswerCorrectness` não existem).

- [ ] **Step 3: Adicionar as métricas de embedding com gabarito**

Acrescente a `backend/app/core/evaluation/embedding_metrics.py` (após as classes existentes, antes dos `register(...)`):

```python
class ContextRecall(_EmbeddingMetric):
    """Whether the retrieved context covers the reference answer."""

    requires_reference = True

    def score(self, sample: EvalSample) -> float:
        """Cosine similarity between the reference answer and the joined contexts."""
        if not sample.contexts or sample.reference_answer is None:
            return 0.0
        reference_vec = self._embedder.embed_query(sample.reference_answer)
        context_vec = self._embedder.embed_query(" ".join(sample.contexts))
        return _clamp(cosine_similarity(reference_vec, context_vec))


class AnswerCorrectness(_EmbeddingMetric):
    """How close the generated answer is to the reference answer."""

    requires_reference = True

    def score(self, sample: EvalSample) -> float:
        """Cosine similarity between the answer and the reference answer."""
        if sample.reference_answer is None:
            return 0.0
        answer_vec = self._embedder.embed_query(sample.answer)
        reference_vec = self._embedder.embed_query(sample.reference_answer)
        return _clamp(cosine_similarity(answer_vec, reference_vec))
```

E acrescente os registros (junto aos demais `register(...)`):

```python
evaluation_registry.register("context_recall", ContextRecall)
evaluation_registry.register("answer_correctness", AnswerCorrectness)
```

- [ ] **Step 4: Implementar o RougeL**

`backend/app/core/evaluation/overlap_metrics.py`:

```python
"""Overlap-based evaluation metrics (ROUGE-L via longest common subsequence)."""
from app.core.evaluation.base import EvalSample, Evaluator, evaluation_registry


def _lcs_length(a: list[str], b: list[str]) -> int:
    """Return the length of the longest common subsequence of two token lists."""
    rows = len(a) + 1
    cols = len(b) + 1
    table = [[0] * cols for _ in range(rows)]
    for i in range(1, rows):
        for j in range(1, cols):
            if a[i - 1] == b[j - 1]:
                table[i][j] = table[i - 1][j - 1] + 1
            else:
                table[i][j] = max(table[i - 1][j], table[i][j - 1])
    return table[-1][-1]


class RougeL(Evaluator):
    """ROUGE-L F-measure between the answer and the reference answer."""

    requires_reference = True

    def score(self, sample: EvalSample) -> float:
        """Return the LCS-based F1 between answer and reference tokens."""
        if sample.reference_answer is None:
            return 0.0
        answer_tokens = sample.answer.lower().split()
        reference_tokens = sample.reference_answer.lower().split()
        if not answer_tokens or not reference_tokens:
            return 0.0
        lcs = _lcs_length(answer_tokens, reference_tokens)
        if lcs == 0:
            return 0.0
        precision = lcs / len(answer_tokens)
        recall = lcs / len(reference_tokens)
        return 2 * precision * recall / (precision + recall)


evaluation_registry.register("rouge_l", RougeL)
```

- [ ] **Step 5: Atualizar o `__init__.py`**

Atualize `backend/app/core/evaluation/__init__.py` para importar e exportar `ContextRecall`, `AnswerCorrectness` e `RougeL`:

```python
"""Evaluation package. Importing it registers the built-in metrics."""
from app.core.evaluation.base import (
    EvalSample,
    Evaluator,
    build_evaluator,
    evaluation_registry,
)
from app.core.evaluation.embedding_metrics import (
    AnswerCorrectness,
    AnswerRelevancy,
    ContextPrecision,
    ContextRecall,
    Faithfulness,
)
from app.core.evaluation.overlap_metrics import RougeL

__all__ = [
    "EvalSample",
    "Evaluator",
    "build_evaluator",
    "evaluation_registry",
    "AnswerRelevancy",
    "ContextPrecision",
    "Faithfulness",
    "ContextRecall",
    "AnswerCorrectness",
    "RougeL",
]
```

- [ ] **Step 6: Rodar e ver passar**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_evaluation_overlap.py tests/test_evaluation_embedding.py -v`
Expected: PASS. Suíte inteira verde, zero warnings.

- [ ] **Step 7: Commit**

```bash
git add backend/app/core/evaluation backend/tests/test_evaluation_overlap.py backend/tests/test_evaluation_embedding.py
git commit -m "feat: reference-based metrics (context recall, answer correctness, rouge-l)"
```

---

### Task 3: Runner `evaluate_sample`

**Files:**
- Create: `backend/app/core/evaluation/runner.py`
- Modify: `backend/app/core/evaluation/__init__.py` (exportar `evaluate_sample`)
- Create: `backend/tests/test_evaluation_runner.py`

**Interfaces:**
- Consumes: `app.core.evaluation.base` (registry, `build_evaluator`, `EvalSample`, `Evaluator`), `app.core.embedding.base.Embedder`.
- Produces:
  - `evaluate_sample(sample: EvalSample, metric_names: list[str], embedder: Embedder | None = None) -> dict[str, float]` — para cada métrica selecionada: constrói o evaluator (injetando `embedder` quando a classe o aceita), pula (não inclui no resultado) as que têm `requires_reference = True` quando `sample.reference_answer is None`, e mapeia `nome -> score`.

Nota de implementação: para decidir se uma métrica precisa do embedder, inspecione a assinatura do `__init__` da classe registrada (ex.: `"embedder" in inspect.signature(cls.__init__).parameters`). `RougeL` não recebe embedder.

- [ ] **Step 1: Escrever o teste que falha**

`backend/tests/test_evaluation_runner.py`:

```python
"""Tests for the evaluation runner."""
from app.core.evaluation.base import EvalSample
from app.core.evaluation.runner import evaluate_sample


class _FakeEmbedder:
    def embed_documents(self, texts):
        return [self.embed_query(t) for t in texts]

    def embed_query(self, text):
        return [1.0, 0.0] if "square" in text.lower() else [0.0, 1.0]

    @property
    def dimension(self) -> int:
        return 2


def test_runner_computes_selected_metrics():
    sample = EvalSample(
        question="Where is the square?",
        answer="The square is downtown.",
        contexts=["The main square map."],
        reference_answer="The square plaza.",
    )
    scores = evaluate_sample(
        sample,
        ["answer_relevancy", "faithfulness", "rouge_l"],
        embedder=_FakeEmbedder(),
    )
    assert set(scores) == {"answer_relevancy", "faithfulness", "rouge_l"}
    assert all(isinstance(v, float) for v in scores.values())


def test_runner_skips_reference_metrics_without_reference():
    sample = EvalSample(
        question="Where is the square?",
        answer="The square is downtown.",
        contexts=["The main square map."],
        reference_answer=None,
    )
    scores = evaluate_sample(
        sample,
        ["answer_relevancy", "answer_correctness", "rouge_l"],
        embedder=_FakeEmbedder(),
    )
    assert set(scores) == {"answer_relevancy"}  # reference-based ones skipped
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_evaluation_runner.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'app.core.evaluation.runner'`.

- [ ] **Step 3: Implementar o runner**

`backend/app/core/evaluation/runner.py`:

```python
"""Run a selected set of evaluation metrics over one sample."""
import inspect

from app.core.embedding.base import Embedder
from app.core.evaluation.base import EvalSample, evaluation_registry


def evaluate_sample(
    sample: EvalSample,
    metric_names: list[str],
    embedder: Embedder | None = None,
) -> dict[str, float]:
    """Score a sample with the named metrics, skipping reference-only ones if absent."""
    scores: dict[str, float] = {}
    for name in metric_names:
        metric_class = evaluation_registry.get(name)
        if metric_class.requires_reference and sample.reference_answer is None:
            continue
        if "embedder" in inspect.signature(metric_class.__init__).parameters:
            metric = metric_class(embedder=embedder)
        else:
            metric = metric_class()
        scores[name] = metric.score(sample)
    return scores
```

- [ ] **Step 4: Exportar no `__init__.py`**

Acrescente ao `backend/app/core/evaluation/__init__.py` o import e o nome em `__all__`:

```python
from app.core.evaluation.runner import evaluate_sample
```

(e `"evaluate_sample"` em `__all__`.)

- [ ] **Step 5: Rodar e ver passar**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_evaluation_runner.py -v`
Expected: PASS (2 testes). Suíte inteira verde, zero warnings.

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/evaluation/runner.py backend/app/core/evaluation/__init__.py backend/tests/test_evaluation_runner.py
git commit -m "feat: evaluation runner (selected metrics, reference-aware)"
```

---

## Self-Review

**Spec coverage (Plano 5 cobre spec §7 — avaliação de respostas, com a decisão de métricas próprias):**
- Evaluator interface + registry (spec §7; extensível) → Task 1. ✅
- Métricas análogas às RAGAS, implementação própria: `answer_relevancy`, `faithfulness`, `context_precision` (sem gabarito) → Task 1; `context_recall`, `answer_correctness` (com gabarito) → Task 2. ✅
- Métrica de overlap com gabarito `rouge_l` → Task 2. ✅
- Runner que roda o conjunto selecionado e pula as que exigem gabarito quando ausente (alinha com o CSV `pergunta`+`resposta_referencia` opcional do spec §8) → Task 3. ✅
- Juiz trocável: as métricas baseadas em embedding usam o `Embedder` injetado (trocável) → Tasks 1, 2. ✅
- Operacionais (latência/tokens) explicitamente fora — medidas no Plano 6. ✅
- Consolidação do cosseno (sem duplicação, diretriz central) → Task 1. ✅

**Placeholder scan:** sem TBD/TODO; todos os passos com código/comando concreto. ✅

**Type consistency:**
- `Evaluator.score(sample) -> float` e `requires_reference: bool` consistentes entre base, métricas e runner. ✅
- `EvalSample(question, answer, contexts, reference_answer)` consistente entre base, métricas, runner e testes. ✅
- `build_evaluator`/`evaluate_sample` reusam `evaluation_registry.get`. ✅
- `cosine_similarity`/`cosine_distance` em `vector_math`, reusados por retrieval/semantic/evaluation (sem duplicação). ✅
- Métricas de embedding recebem `embedder=`; `RougeL` sem args; runner detecta via assinatura. ✅

**Escopo:** só avaliação de respostas (métricas + runner). Nada de orquestração de experimentos (Plano 6) nem operacionais. Sem over-build; sem dependência da lib RAGAS (decisão do usuário). ✅
