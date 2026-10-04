"""Experiment orchestrator: run the cartesian product and persist results."""
import logging
import threading
import time
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import AbstractContextManager, contextmanager, nullcontext
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.db.models import Experiment, ExperimentRun, QuestionProfile, RunResult
from app.core.difficulty import (
    corpus_stats_for_base,
    evidence_distance,
    question_profile,
    retrieval_profile,
)
from app.core.difficulty.perplexity import (
    PerplexitySkipped,
    cached_perplexities,
    perplexity_scorer_for,
)
from app.core.embedding.base import build_embedder
from app.core.evaluation.base import EvalSample
from app.core.config.runtime import get_eval_embedding
from app.core.evaluation.runner import evaluate_sample, metrics_need_embedder
from app.core.llm import ollama
from app.core.llm.factory import is_local_llm, resolve_llm
from app.core.memory.device import resolve_embedding_device
from app.core.memory.leases import CachedQueryEmbedder, LeaseSwitcher
from app.core.memory.manager import ModelManager
from app.core.memory.profile import active_profile
from app.core.memory.stats import process_memory_bytes
from app.core.graph.build import GraphBuildPaused, build_graph, current_graph
from app.core.graph.cache import ExtractionCache
from app.core.prompts import PROMPT_SPECS
from app.core.rag.base import build_rag, technique_class
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

# Experiment id -> {"extracted", "total"} chunks of the Grafo being built (same
# single-process reasoning; extraction threads update it, the API reads it).
_graph_progress: dict[int, dict[str, int]] = {}


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
    # Model name -> PerplexityScorer, or None when the model cannot be scored.
    perplexity_scorer_factory: Callable = perplexity_scorer_for

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
    evidence, types = {}, {}
    for q in questions:
        evidence.setdefault(q.text, q.evidence)
        types.setdefault(q.text, q.question_type)
    missing = [t for t in evidence if t not in known]
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
                experiment_id=experiment_id,
                question=text,
                signals=question_profile(text, corpus, evidence[text]),
                question_type=types[text],
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


def _uses_graph(rag_name: str) -> bool:
    """Whether the technique answers from the Índice's Grafo de conhecimento."""
    technique = technique_class(rag_name)
    return technique is not None and technique.uses_graph


def graph_build_progress(experiment_id: int) -> dict | None:
    """Chunks extracted / total of the Grafo being built now, or None if none is."""
    progress = _graph_progress.get(experiment_id)
    return dict(progress) if progress is not None else None


def _graph_embedder_scope(
    deps: ExperimentDeps, embedding: str, llm_name: str, device: str
) -> Callable[[], AbstractContextManager]:
    """Staged: lease the Índice's embedder only to write the graph, after the extraction.

    Where the profile holds one local model, a local LLM extrator is unloaded
    first, so the two never share the memory; the embedder leaves before
    generation (the LLM reloads on its next call).
    """

    @contextmanager
    def lease():
        if (
            deps.models.max_local < 2
            and is_local_llm(llm_name)
            and deps.models.is_local(embedding)
        ):
            ollama.unload_local_llm(llm_name)
        with deps.models.acquire(embedding, device) as embedder:
            yield embedder
        deps.models.evict_idle()

    return lease


def _run_graph(
    deps: ExperimentDeps,
    session: Session,
    experiment: Experiment,
    config: ExperimentConfig,
    chunking: str,
    embedding: str,
    llm_name: str,
    llm,
    embedder,
    leases: LeaseSwitcher,
    prompt: str | None,
    concurrency: int,
    device: str,
    staged: bool,
):
    """The run's Grafo de conhecimento: the cached one if current, else built now.

    A build shows as the "building_graph" phase with chunks extracted / total,
    reuses the extraction cache and raises GraphBuildPaused at a pause.
    """
    graph = current_graph(deps.store, config.base, chunking, embedding, llm_name, prompt)
    if graph is not None:
        return graph
    experiment_id = experiment.id
    if staged:
        # The LLM extrator gets the memory: no embedder lease (a HyDE or
        # multi-query fallback of an earlier run) stays loaded next to it.
        leases.close()
        deps.models.evict_idle()
    previous_phase = (experiment.config or {}).get("phase")
    _graph_progress[experiment_id] = {"extracted": 0, "total": 0}
    _set_phase(session, experiment, "building_graph")

    def on_progress(extracted: int, total: int) -> None:
        _graph_progress[experiment_id] = {"extracted": extracted, "total": total}

    try:
        return build_graph(
            deps.store, config.base, chunking, embedding, llm_name, llm,
            embedder_scope=(
                _graph_embedder_scope(deps, embedding, llm_name, device)
                if staged
                else lambda: nullcontext(embedder)
            ),
            prompt=prompt, max_concurrency=concurrency,
            cache=ExtractionCache(deps.session_factory),
            should_stop=lambda: _pause_requested(experiment_id),
            on_progress=on_progress,
        )
    finally:
        _graph_progress.pop(experiment_id, None)
        _set_phase(session, experiment, previous_phase)


def _error_result(run_id: int, question: QuestionItem, error: str) -> RunResult:
    """The stored row of a question that could not be answered."""
    return RunResult(
        run_id=run_id,
        question=question.text,
        reference_answer=question.reference,
        reference_contexts=question.evidence,
        question_type=question.question_type,
        evidence_hops=question.evidence_hops,
        bridge_entities=question.bridge_entities,
        generated_answer=f"{ERROR_PREFIX}{error}]",
        retrieved_context=[],
        scores={},
        latency_ms=0,
        tokens=0,
    )


def _process_question(rag, question: QuestionItem, metrics: list, eval_embedder):
    """Run rag.answer + evaluate for one question.

    Returns (answer, contexts, scores, latency_ms, tokens, graph_explanation).
    """
    start = time.perf_counter()
    if getattr(rag, "uses_evidence", False):
        answer = rag.answer(question.text, evidence=question.evidence)
    else:
        answer = rag.answer(question.text)
    latency_ms = int((time.perf_counter() - start) * 1000)
    context_texts = [c.get("text", "") for c in answer.contexts]
    sample = EvalSample(
        question=question.text,
        answer=answer.answer,
        contexts=context_texts,
        reference_answer=question.reference,
        reference_contexts=question.evidence,
        reference_hops=question.evidence_hops,
    )
    scores = evaluate_sample(sample, metrics, embedder=eval_embedder)
    return (
        answer.answer, answer.contexts, scores, latency_ms, len(answer.answer.split()),
        answer.graph_explanation,
    )


def _process_question_with_retry(rag, question: QuestionItem, metrics: list, eval_embedder):
    """Try _process_question up to _MAX_RETRIES times with _RETRY_DELAY_S between attempts.

    Returns (answer_text, contexts, scores, latency_ms, tokens, graph_explanation, error_str).
    On permanent failure error_str is set and the other values are None.
    """
    last_exc = None
    for attempt in range(_MAX_RETRIES):
        try:
            return (*_process_question(rag, question, metrics, eval_embedder), None)
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
    return None, None, None, None, None, None, str(last_exc)


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


def _store_evidence_distances(
    session: Session,
    experiment_id: int,
    config: ExperimentConfig,
    deps: ExperimentDeps,
    questions: list[QuestionItem],
    device: str,
) -> None:
    """Add GRADE's question-evidence distance to the profiles, with the eval embedder.

    Runs after generation, when the LLM no longer holds the memory. Optional:
    a failure is logged and the experiment still finishes.
    """
    evidence = {q.text: q.evidence for q in questions if q.evidence}
    profiles = [
        p
        for p in session.query(QuestionProfile).filter_by(experiment_id=experiment_id)
        if p.question in evidence and "evidence_distance" not in (p.signals or {})
    ]
    if not profiles:
        return
    try:
        with deps.models.acquire(config.eval_embedding, device) as embedder:
            for profile in profiles:
                distance = evidence_distance(embedder, profile.question, evidence[profile.question])
                profile.signals = {**profile.signals, "evidence_distance": distance}
        session.commit()
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        logger.warning("evidence distance skipped: %s", exc)


def _store_perplexities(
    session: Session,
    experiment_id: int,
    config: ExperimentConfig,
    deps: ExperimentDeps,
    questions: list[QuestionItem],
) -> None:
    """Score each distinct question once per local LLM that supports it (perplexity).

    The question is the same across every combination, so it is scored once per
    model, not per run; scores already known to this process are reused.
    Optional: a failure is logged and the experiment still finishes.
    """
    texts = list(dict.fromkeys(q.text for q in questions))
    skipped: dict[str, dict] = {}
    profiles = {
        p.question: p
        for p in session.query(QuestionProfile).filter_by(experiment_id=experiment_id)
    }
    for llm_name in dict.fromkeys(config.llms):
        if not is_local_llm(llm_name):
            continue
        scorer = deps.perplexity_scorer_factory(llm_name)
        if scorer is None:
            continue
        try:
            scores = cached_perplexities(scorer, llm_name, texts)
        except PerplexitySkipped as exc:
            logger.warning("perplexity skipped for %s: %s", llm_name, exc)
            skipped[llm_name] = {"free_mb": exc.free_mb, "needed_mb": exc.needed_mb}
            continue
        except Exception as exc:  # noqa: BLE001
            logger.warning("perplexity failed for %s: %s", llm_name, exc)
            skipped[llm_name] = {"error": str(exc)[:300]}
            continue
        for text, value in scores.items():
            profile = profiles.get(text)
            if profile is not None:
                signals = dict(profile.model_signals or {})
                signals[llm_name] = {**signals.get(llm_name, {}), "perplexity": value}
                profile.model_signals = signals
        session.commit()
    if skipped:
        # Shown on the difficulty tab, so a missing signal is explained.
        experiment = session.get(Experiment, experiment_id)
        experiment.config = {**(experiment.config or {}), "perplexity_skipped": skipped}
        session.commit()


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
            ollama.unload_local_llm(llm_name)
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
                reference_hops=row.evidence_hops,
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
                if rag_name in PROMPT_SPECS or _uses_graph(rag_name):
                    rag_kwargs["prompts"] = prompt_snapshot.get(rag_name)
                if _uses_graph(rag_name):
                    # The LLM de resposta is, for now, also the LLM extrator.
                    try:
                        graph = _run_graph(
                            deps, session, experiment, config, chunking, embedding,
                            llm_name, llm, embedder, leases,
                            prompt=(prompt_snapshot.get(rag_name) or {}).get("extract"),
                            concurrency=concurrency, device=device, staged=staged,
                        )
                    except GraphBuildPaused:
                        # Extracted chunks are cached: a new run extracts only the rest.
                        paused = True
                        run.status = "paused"
                        session.commit()
                        break
                    except Exception as exc:  # noqa: BLE001  the other runs go on
                        logger.error("graph build failed for run %d: %s", run.id, exc)
                        for question in questions:
                            session.add(_error_result(run.id, question, f"Grafo: {exc}"))
                        run.status = "done"
                        session.commit()
                        continue
                    run.graph_stats = graph.stats
                    session.commit()
                    rag_kwargs.update(graph=graph, embedder=embedder)
                rag = deps.rag_factory(rag_name, **rag_kwargs)

                # The oracle answers from the reference evidence: only questions with one.
                run_questions = (
                    [q for q in questions if q.evidence]
                    if getattr(rag, "uses_evidence", False)
                    else questions
                )
                # DB writes stay on this thread: the Session is not thread-safe.
                for question, outcome in _run_questions(
                    rag, run_questions, inline_metrics, eval_embedder, concurrency, experiment_id,
                ):
                    # Checkpoint: questions not started before a pause are skipped.
                    if outcome is None:
                        paused = True
                        continue

                    answer_text, contexts, scores, latency_ms, tokens, explanation, error = outcome
                    if error is not None:
                        session.add(_error_result(run.id, question, error))
                    else:
                        session.add(
                            RunResult(
                                run_id=run.id,
                                question=question.text,
                                reference_answer=question.reference,
                                reference_contexts=question.evidence,
                                question_type=question.question_type,
                                evidence_hops=question.evidence_hops,
                                bridge_entities=question.bridge_entities,
                                generated_answer=answer_text,
                                retrieved_context=contexts,
                                graph_explanation=explanation,
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
        _store_evidence_distances(
            session, experiment_id, config, deps, questions,
            resolve_embedding_device(active_profile()) if staged else device,
        )
        _store_perplexities(session, experiment_id, config, deps, questions)
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
