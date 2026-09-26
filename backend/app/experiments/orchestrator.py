"""Experiment orchestrator: run the cartesian product and persist results."""
import logging
import threading
import time
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.db.models import Experiment, ExperimentRun, QuestionProfile, RunResult
from app.core.difficulty import corpus_stats_for_base, question_profile, retrieval_profile
from app.core.embedding.base import build_embedder
from app.core.evaluation.base import EvalSample
from app.core.config.runtime import get_eval_embedding, get_ollama_models
from app.core.evaluation.runner import evaluate_sample, metrics_need_embedder
from app.core.llm import ollama
from app.core.llm.factory import is_local_llm, resolve_llm
from app.core.memory.device import resolve_embedding_device
from app.core.memory.leases import CachedQueryEmbedder, LeaseSwitcher
from app.core.memory.manager import ModelManager
from app.core.memory.profile import active_profile
from app.core.memory.stats import process_memory_bytes
from app.core.prompts import PROMPT_SPECS
from app.core.rag.base import build_rag
from app.core.retrieval.base import build_retriever
from app.core.vectorstore.qdrant import QdrantStore, collection_name
from app.experiments.schemas import ExperimentConfig, QuestionItem, combinations, index_pairs

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_DELAY_S = 5

# Marks a question that failed after every retry (stored as its answer).
ERROR_PREFIX = "[ERRO: "

# In-memory set of experiment ids for which a pause has been requested.
# Valid because the API runs as a single uvicorn process: the pause endpoint
# and the background task share this module-level state.
_pause_requests: set[int] = set()

# One experiment at a time: queued ones stay "pending" (shown as "Na fila").
# Single uvicorn process, so a module-level semaphore is enough.
_run_slot = threading.Semaphore(1)


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
    # Shared embedder cache; None builds a private one around embedder_factory.
    models: ModelManager | None = None

    def __post_init__(self) -> None:
        if self.models is None:
            self.models = ModelManager(self.embedder_factory, max_local=active_profile().max_local_models)


def _combinations(config: ExperimentConfig):
    """Every run in LLM-major order, so each LLM loads once per experiment."""
    return combinations(config)


def _store_question_profiles(
    session: Session, experiment_id: int, base: str, questions: list[QuestionItem], store
) -> None:
    """Record each question's pre-retrieval difficulty signals once (resumes skip them)."""
    known = {
        p.question
        for p in session.query(QuestionProfile).filter_by(experiment_id=experiment_id)
    }
    missing = [t for t in dict.fromkeys(q.text for q in questions) if t not in known]
    if not missing:
        return
    try:
        corpus = corpus_stats_for_base(store, base)
    except Exception as exc:  # noqa: BLE001  signals are optional; the run goes on
        logger.warning("corpus stats unavailable for %s: %s", base, exc)
        corpus = None
    for text in missing:
        session.add(
            QuestionProfile(
                experiment_id=experiment_id, question=text, signals=question_profile(text, corpus)
            )
        )
    session.commit()


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
        reference_contexts=question.evidence,
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
    """Run the experiment once the single experiment slot is free."""
    if config.eval_embedding is None:
        config = config.model_copy(update={"eval_embedding": get_eval_embedding()})
    with _run_slot:
        _run_experiment(experiment_id, config, questions, deps)


def _set_phase(session: Session, experiment: Experiment, phase: str | None) -> None:
    """Record the stage a staged experiment is in (shown by the UI); None clears it."""
    config = {k: v for k, v in (experiment.config or {}).items() if k != "phase"}
    if phase is not None:
        config["phase"] = phase
    experiment.config = config
    session.commit()


def _question_vectors(
    deps: ExperimentDeps, config: ExperimentConfig, questions: list[QuestionItem], device: str
) -> dict[str, dict[str, list[float]]]:
    """Stage A: embed every question once per retrieval embedding, then free the models."""
    texts = list(dict.fromkeys(q.text for q in questions))
    vectors: dict[str, dict[str, list[float]]] = {}
    for embedding in dict.fromkeys(e for _, e in index_pairs(config)):
        with deps.models.acquire(embedding, device) as embedder:
            # Injected embedders may predate embed_queries: fall back to one call per text.
            batch = getattr(embedder, "embed_queries", None)
            embedded = batch(texts) if batch else [embedder.embed_query(t) for t in texts]
            vectors[embedding] = dict(zip(texts, embedded))
    deps.models.evict_idle()  # the LLM gets the memory from here on
    return vectors


def _llm_server_model(name: str) -> str:
    """The model name the local LLM server knows (legacy named ids map to their model)."""
    for entry in get_ollama_models():
        if entry.get("id") == name:
            return entry["model"]
    return name


def _score_with_retry(sample: EvalSample, metrics: list, eval_embedder) -> dict[str, float]:
    """evaluate_sample with the same retry policy as generation; {} if it keeps failing."""
    for attempt in range(_MAX_RETRIES):
        try:
            return evaluate_sample(sample, metrics, embedder=eval_embedder)
        except Exception as exc:  # noqa: BLE001
            if attempt < _MAX_RETRIES - 1:
                logger.warning("scoring failed (attempt %d/%d): %s", attempt + 1, _MAX_RETRIES, exc)
                time.sleep(_RETRY_DELAY_S)
            else:
                logger.error("scoring failed after %d attempts: %s", _MAX_RETRIES, exc)
    return {}


def _score_results(
    session: Session, experiment_id: int, config: ExperimentConfig, deps: ExperimentDeps
) -> None:
    """Stage C: free the LLM, load the eval embedder once, score every stored answer."""
    for llm_name in dict.fromkeys(config.llms):
        if is_local_llm(llm_name):
            ollama.unload_local_llm(_llm_server_model(llm_name))
    rows = (
        session.query(RunResult)
        .join(ExperimentRun)
        .filter(ExperimentRun.experiment_id == experiment_id)
        .all()
    )
    pending = [r for r in rows if not r.scores and not r.generated_answer.startswith(ERROR_PREFIX)]
    if not pending:
        return
    device = resolve_embedding_device(active_profile())
    eval_context = (
        deps.models.acquire(config.eval_embedding, device)
        if metrics_need_embedder(config.metrics)
        else nullcontext(None)
    )
    with eval_context as eval_embedder:
        for row in pending:
            sample = EvalSample(
                question=row.question,
                answer=row.generated_answer,
                contexts=[c.get("text", "") for c in row.retrieved_context],
                reference_answer=row.reference_answer,
                reference_contexts=row.reference_contexts,
            )
            row.scores = _score_with_retry(sample, config.metrics, eval_embedder)
        session.commit()


def _run_experiment(
    experiment_id: int,
    config: ExperimentConfig,
    questions: list[QuestionItem],
    deps: ExperimentDeps,
) -> None:
    """Run every combination over every question and persist the results.

    Staged (the default): A) embed the questions, B) generate LLM by LLM with
    only the LLM in memory, C) score. Unstaged: one pass, scoring as it goes.
    """
    session = deps.session_factory()
    try:
        experiment = session.get(Experiment, experiment_id)
        experiment.status = "running"
        session.commit()
        _store_question_profiles(session, experiment_id, config.base, questions, deps.store)

        prompt_snapshot = (experiment.config or {}).get("prompts", {})
        profile = active_profile()
        device = resolve_embedding_device(profile, config.llms)
        concurrency = min(config.concurrency, profile.max_concurrency)
        if concurrency < config.concurrency:
            logger.info(
                "concurrency %d capped to %d by the %s memory profile",
                config.concurrency, concurrency, profile.name,
            )
        staged = config.staged
        vectors = _question_vectors(deps, config, questions, device) if staged else {}
        if staged:
            _set_phase(session, experiment, "generating")
        eval_context = (
            deps.models.acquire(config.eval_embedding, device)
            if not staged and metrics_need_embedder(config.metrics)
            else nullcontext(None)
        )
        inline_metrics = [] if staged else config.metrics

        paused = False
        loaded_llm_name, llm = None, None
        with eval_context as eval_embedder, LeaseSwitcher(deps.models) as leases:
            for llm_name, (chunking, embedding), rag_name, retriever_name in _combinations(config):
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

                if llm_name != loaded_llm_name:
                    llm, loaded_llm_name = deps.llm_factory(llm_name), llm_name
                if staged:
                    cached = vectors[embedding]
                    embedder = CachedQueryEmbedder(
                        cached,
                        # Only text the LLM writes (HyDE, multi-query, rewrites) loads the model.
                        fallback=lambda name=embedding: leases.get(name, device),
                        dimension=len(next(iter(cached.values()), [])),
                    )
                else:
                    embedder = leases.get(embedding, device)
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
                    rag, questions, inline_metrics, eval_embedder, concurrency, experiment_id,
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
                                reference_contexts=question.evidence,
                                generated_answer=f"{ERROR_PREFIX}{error}]",
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
                                reference_contexts=question.evidence,
                                generated_answer=answer_text,
                                retrieved_context=contexts,
                                retrieval_signals=retrieval_profile(contexts),
                                scores=scores,
                                latency_ms=latency_ms,
                                tokens=tokens,
                            )
                        )
                logger.info("run %d finished; API memory %.0f MB", run.id, process_memory_bytes() / 1e6)

                if paused:
                    run.status = "paused"
                    session.commit()
                    break

                run.status = "done"
                session.commit()

        if staged:
            # Scores what was generated, paused or not.
            _set_phase(session, experiment, "evaluating")
            _score_results(session, experiment_id, config, deps)
        experiment.status = "paused" if paused else "done"
        experiment.finished_at = datetime.now(UTC)
        _set_phase(session, experiment, None)
    except Exception as exc:  # noqa: BLE001  background task records failure, never raises
        session.rollback()
        experiment = session.get(Experiment, experiment_id)
        if experiment is not None:
            experiment.status = "failed"
            config_without_phase = {k: v for k, v in (experiment.config or {}).items() if k != "phase"}
            experiment.config = {**config_without_phase, "error": str(exc)}
            experiment.finished_at = datetime.now(UTC)
            session.commit()
    finally:
        _pause_requests.discard(experiment_id)
        session.close()
