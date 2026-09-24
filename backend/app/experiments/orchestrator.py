"""Experiment orchestrator: run the cartesian product and persist results."""
import itertools
import logging
import time
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.db.models import Experiment, ExperimentRun, RunResult
from app.core.embedding.base import build_embedder
from app.core.evaluation.base import EvalSample
from app.core.evaluation.runner import evaluate_sample
from app.core.llm.factory import resolve_llm
from app.core.prompts import PROMPT_SPECS
from app.core.rag.base import build_rag
from app.core.retrieval.base import build_retriever
from app.core.vectorstore.qdrant import QdrantStore, collection_name
from app.experiments.schemas import ExperimentConfig, QuestionItem

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_DELAY_S = 5

# In-memory set of experiment ids for which a pause has been requested.
# Valid because the API runs as a single uvicorn process: the pause endpoint
# and the background task share this module-level state.
_pause_requests: set[int] = set()


def request_pause(experiment_id: int) -> None:
    """Signal a running experiment to stop at its next checkpoint."""
    _pause_requests.add(experiment_id)


def _pause_requested(experiment_id: int) -> bool:
    return experiment_id in _pause_requests


@dataclass
class ExperimentDeps:
    """Injectable dependencies for running an experiment (overridable in tests)."""

    store: QdrantStore
    session_factory: Callable[[], Session]
    llm_factory: Callable = resolve_llm
    embedder_factory: Callable = build_embedder
    retriever_factory: Callable = build_retriever
    rag_factory: Callable = build_rag


def _build_retriever(deps: ExperimentDeps, name: str, collection: str, embedder, llm, prompts=None):
    """Build a retriever, injecting the llm/prompts only for retrievers that need it."""
    kwargs = {"store": deps.store, "collection": collection, "embedder": embedder}
    if name == "multi_query":
        kwargs["llm"] = llm
        kwargs["prompts"] = prompts
    return deps.retriever_factory(name, **kwargs)


def _process_question(rag, question: QuestionItem, metrics: list, eval_embedder):
    """Run rag.answer + evaluate for one question.

    Returns (answer, contexts, scores, latency_ms, tokens).
    """
    start = time.perf_counter()
    answer = rag.answer(question.text)
    latency_ms = int((time.perf_counter() - start) * 1000)
    context_texts = [c.get("text", "") for c in answer.contexts]
    sample = EvalSample(
        question=question.text,
        answer=answer.answer,
        contexts=context_texts,
        reference_answer=question.reference,
    )
    scores = evaluate_sample(sample, metrics, embedder=eval_embedder)
    return answer.answer, answer.contexts, scores, latency_ms, len(answer.answer.split())


def _process_question_with_retry(rag, question: QuestionItem, metrics: list, eval_embedder):
    """Try _process_question up to _MAX_RETRIES times with _RETRY_DELAY_S between attempts.

    Returns (answer_text, contexts, scores, latency_ms, tokens, error_str).
    On permanent failure error_str is set and the other values are None.
    """
    last_exc = None
    for attempt in range(_MAX_RETRIES):
        try:
            answer_text, contexts, scores, latency_ms, tokens = _process_question(
                rag, question, metrics, eval_embedder
            )
            return answer_text, contexts, scores, latency_ms, tokens, None
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt < _MAX_RETRIES - 1:
                logger.warning(
                    "Question %r failed (attempt %d/%d): %s — retrying in %ds",
                    question.text[:60],
                    attempt + 1,
                    _MAX_RETRIES,
                    exc,
                    _RETRY_DELAY_S,
                )
                time.sleep(_RETRY_DELAY_S)
            else:
                logger.error(
                    "Question %r failed after %d attempts: %s",
                    question.text[:60],
                    _MAX_RETRIES,
                    exc,
                )
    return None, None, None, None, None, str(last_exc)


def _run_questions(
    rag, questions: list[QuestionItem], metrics: list, eval_embedder,
    concurrency: int, experiment_id: int,
) -> Iterator[tuple[QuestionItem, tuple | None]]:
    """Yield (question, outcome) in question order, running up to `concurrency` at once.

    The outcome is None for a question skipped because a pause was requested
    before it started; questions already in flight run to completion.
    """

    def work(question: QuestionItem):
        if _pause_requested(experiment_id):
            return None
        return _process_question_with_retry(rag, question, metrics, eval_embedder)

    if concurrency <= 1:
        for question in questions:
            yield question, work(question)
        return
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        yield from zip(questions, pool.map(work, questions))


def run_experiment(
    experiment_id: int,
    config: ExperimentConfig,
    questions: list[QuestionItem],
    deps: ExperimentDeps,
) -> None:
    """Run every combination over every question and persist the results."""
    session = deps.session_factory()
    try:
        experiment = session.get(Experiment, experiment_id)
        experiment.status = "running"
        session.commit()

        prompt_snapshot = (experiment.config or {}).get("prompts", {})
        eval_embedder = deps.embedder_factory(config.eval_embedding)

        paused = False
        for chunking, embedding, rag_name, retriever_name, llm_name in itertools.product(
            config.chunkings, config.embeddings, config.rags, config.retrievers, config.llms
        ):
            # Checkpoint: stop before starting a new combination if paused.
            if _pause_requested(experiment_id):
                paused = True
                break

            run = ExperimentRun(
                experiment_id=experiment_id,
                chunking=chunking,
                embedding=embedding,
                rag_technique=rag_name,
                retriever=retriever_name,
                llm=llm_name,
                status="running",
            )
            session.add(run)
            session.commit()

            embedder = deps.embedder_factory(embedding)
            llm = deps.llm_factory(llm_name)
            col = collection_name(config.base, chunking, embedding)
            retriever = _build_retriever(
                deps, retriever_name, col, embedder, llm,
                prompts=prompt_snapshot.get("multi_query"),
            )
            rag_kwargs = {"retriever": retriever, "llm": llm}
            if rag_name in PROMPT_SPECS:
                rag_kwargs["prompts"] = prompt_snapshot.get(rag_name)
            rag = deps.rag_factory(rag_name, **rag_kwargs)

            # DB writes stay on this thread: the Session is not thread-safe.
            for question, outcome in _run_questions(
                rag, questions, config.metrics, eval_embedder,
                config.concurrency, experiment_id,
            ):
                # Checkpoint: questions not started before a pause are skipped.
                if outcome is None:
                    paused = True
                    continue

                answer_text, contexts, scores, latency_ms, tokens, error = outcome
                if error is not None:
                    session.add(
                        RunResult(
                            run_id=run.id,
                            question=question.text,
                            reference_answer=question.reference,
                            generated_answer=f"[ERRO: {error}]",
                            retrieved_context=[],
                            scores={},
                            latency_ms=0,
                            tokens=0,
                        )
                    )
                else:
                    session.add(
                        RunResult(
                            run_id=run.id,
                            question=question.text,
                            reference_answer=question.reference,
                            generated_answer=answer_text,
                            retrieved_context=contexts,
                            scores=scores,
                            latency_ms=latency_ms,
                            tokens=tokens,
                        )
                    )

            if paused:
                run.status = "paused"
                session.commit()
                break

            run.status = "done"
            session.commit()

        experiment.status = "paused" if paused else "done"
        experiment.finished_at = datetime.now(UTC)
        session.commit()
    except Exception as exc:  # noqa: BLE001  background task records failure, never raises
        session.rollback()
        experiment = session.get(Experiment, experiment_id)
        if experiment is not None:
            experiment.status = "failed"
            experiment.config = {**experiment.config, "error": str(exc)}
            experiment.finished_at = datetime.now(UTC)
            session.commit()
    finally:
        _pause_requests.discard(experiment_id)
        session.close()
