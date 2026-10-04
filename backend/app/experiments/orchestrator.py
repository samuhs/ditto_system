"""Experiment orchestrator: run the cartesian product and persist results."""
import logging
import threading
import time
import traceback
from collections.abc import Callable, Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as _FutureTimeoutError
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

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
from app.core.config.runtime import get_eval_embedding, get_stall_limit_s
from app.core.evaluation.runner import evaluate_sample, metrics_need_embedder
from app.core.llm import ollama
from app.core.llm.factory import is_local_llm, resolve_llm
from app.core.memory.device import resolve_embedding_device
from app.core.memory.leases import CachedQueryEmbedder, LeaseSwitcher
from app.core.memory.manager import ModelManager, work_slot
from app.core.memory.profile import active_profile
from app.core.memory.stats import available_memory_bytes, process_memory_bytes
from app.core.graph.build import current_graph
from app.core.prompts import PROMPT_SPECS
from app.core.rag.base import build_rag, technique_class
from app.core.retrieval.base import build_retriever
from app.core.vectorstore.qdrant import QdrantStore, collection_name
from app.experiments.schemas import ExperimentConfig, QuestionItem, combinations, index_pairs
from app.experiments.watchdog import StallWatchdog

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_DELAY_S = 5

# #19: this many question failures in a row (after every retry), in any Combinação,
# trigger an automatic Pausa por Falhas consecutivas.
_CONSECUTIVE_FAILURES_LIMIT = 3

# Marks a question that failed after every retry (stored as its answer).
ERROR_PREFIX = "[ERRO: "

# Every reason a Pausa can have, recorded in the Registro de pausa (see CONTEXT.md,
# "Pausa"): manual (POST /pause), stall (#20, Travamento), consecutive_failures (#19),
# interrupted (API boot) and failed (an uncaught exception). Shared by `PauseRequest`,
# `request_pause` and `record_pause` so a typo here is a type error, not a silent typo
# in the Registro de pausa.
PauseReason = Literal["manual", "stall", "consecutive_failures", "interrupted", "failed"]


@dataclass
class PauseRequest:
    """A request to stop a running experiment at its next checkpoint, with why.

    `score_partial=True` (the Pausa manual endpoint's default) lets in-flight
    questions finish and then scores whatever was generated, as a manual Pausa
    always has. #19 (Falhas consecutivas) and #20 (Travamento) request
    `score_partial=False`: the run still lets in-flight questions finish and get
    recorded, but skips the scoring and difficulty-signal stages entirely, to free
    the machine right away for someone to investigate. `detail` becomes the pause
    entry's `last_error` (see `record_pause`).
    """

    reason: PauseReason
    score_partial: bool = True
    detail: dict | None = None


# Pending pause requests, by experiment id. Valid because the API runs as a single
# uvicorn process: the pause endpoint (or #19/#20, from inside the run itself) and
# the background task share this module-level state.
_pause_requests: dict[int, PauseRequest] = {}


def request_pause(
    experiment_id: int, reason: PauseReason = "manual", *,
    score_partial: bool = True, detail: dict | None = None,
) -> None:
    """Signal a running experiment to stop at its next checkpoint.

    POST /experiments/{id}/pause calls this with the defaults (a manual Pausa).
    #19 (Falhas consecutivas) and #20 (Travamento) call it from inside the run with
    their own `reason` and `score_partial=False`: the "pause now without scoring"
    path this ticket introduces and covers by test.
    """
    _pause_requests[experiment_id] = PauseRequest(reason=reason, score_partial=score_partial, detail=detail)


def _pause_requested(experiment_id: int) -> bool:
    return experiment_id in _pause_requests


def _memory_snapshot() -> dict:
    """Free system memory and this API process's own usage (MB), for a pause entry."""
    return {
        "free_mb": round(available_memory_bytes() / 1e6),
        "api_mb": round(process_memory_bytes() / 1e6),
    }


def _error_detail(exc: BaseException, limit: int = 4000) -> dict:
    """{"message", "traceback"} for an exception, the traceback kept short (last `limit` chars)."""
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    return {"message": str(exc), "traceback": tb[-limit:]}


def record_pause(
    session: Session,
    experiment: Experiment,
    *,
    reason: PauseReason,
    phase: str | None,
    in_flight: list[dict] | None = None,
    last_error: dict | None = None,
) -> None:
    """Append one entry to the Experimento's Registro de pausa (`experiment.pauses`).

    Called once a pause actually takes effect (never merely when it is requested):
    manual, `stall` (#20), `consecutive_failures` (#19), `interrupted` (API boot)
    and `failed` (an uncaught exception) all go through this, so GET
    /experiments/{id} has one history to read. `resumed_at` starts null; #17's
    Retomada fills it in when the experiment resumes.
    """
    entry = {
        "paused_at": datetime.now(UTC).isoformat(),
        "reason": reason,
        "phase": phase,
        "in_flight": in_flight or [],
        "last_error": last_error,
        "memory": _memory_snapshot(),
        "resumed_at": None,
    }
    experiment.pauses = [*(experiment.pauses or []), entry]
    session.commit()


def recover_interrupted_experiments(session_factory: Callable[[], Session]) -> None:
    """Mark Experimentos left `running`/`pending` by a crash or restart as paused.

    Called once by the API's `lifespan`, right after `create_all()`. The likeliest
    cause of an API restart mid-run is an out-of-memory crash, so interrupted
    Experimentos never resume on their own (ADR 0001) — nothing here is
    re-enqueued; a researcher decides when to Retomar. Any `ExperimentRun` left
    `running` becomes `paused` too, so a later Retomada (#17) can reuse it.
    """
    session = session_factory()
    try:
        stuck = session.query(Experiment).filter(Experiment.status.in_(["running", "pending"])).all()
        for experiment in stuck:
            phase = (experiment.config or {}).get("phase")
            experiment.status = "paused"
            _set_phase(session, experiment, None)
            record_pause(session, experiment, reason="interrupted", phase=phase)

        session.query(ExperimentRun).filter(ExperimentRun.status == "running").update(
            {"status": "paused"}, synchronize_session=False
        )
        session.commit()
    finally:
        session.close()


class _InFlightTracker:
    """Thread-safe registry of questions mid-call, for a pause entry's `in_flight`.

    One instance per experiment run (created in `_run_experiment`); `concurrency` > 1
    can have several questions mid-call at once. #19 and #20 read a snapshot the
    moment they decide to pause, before anything still running gets a chance to
    finish — that is the whole point of tracking it here instead of only looking at
    what the main loop has consumed so far.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: dict[int, dict] = {}
        self._next_token = 0

    def start(self, combo: dict, question: str) -> int:
        """Register one question as mid-call; returns a token for `finish`."""
        with self._lock:
            token = self._next_token
            self._next_token += 1
            self._items[token] = {**combo, "question": question}
        return token

    def finish(self, token: int) -> None:
        with self._lock:
            self._items.pop(token, None)

    def snapshot(self) -> list[dict]:
        """Combinação + pergunta of everything currently mid-call."""
        with self._lock:
            return list(self._items.values())


class _ConsecutiveFailureTracker:
    """Counts question failures in a row, across every Combinação, for #19.

    One instance per experiment run. `record_failure` returns True once
    `_CONSECUTIVE_FAILURES_LIMIT` failures have landed with no success between
    them; `record_success` resets the count to zero. The "no Grafo de
    conhecimento atual" error the orchestrator records on purpose (a Combinação
    whose Grafo does not exist) is written straight to `RunResult` without going
    through `_run_questions`, so it never reaches this tracker.
    """

    def __init__(self, limit: int = _CONSECUTIVE_FAILURES_LIMIT) -> None:
        self._limit = limit
        self._count = 0

    def record_success(self) -> None:
        self._count = 0

    def record_failure(self) -> bool:
        self._count += 1
        return self._count >= self._limit


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
    # Travamento limit in seconds (#20); None reads Configurações gerais at run time.
    stall_limit_s: float | None = None

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


def _existing_run(
    session: Session, experiment_id: int,
    chunking: str, embedding: str, rag_name: str, retriever_name: str, llm_name: str,
) -> ExperimentRun | None:
    """The ExperimentRun already recorded for this combination, if any (a Retomada's state)."""
    return (
        session.query(ExperimentRun)
        .filter_by(
            experiment_id=experiment_id, chunking=chunking, embedding=embedding,
            rag_technique=rag_name, retriever=retriever_name, llm=llm_name,
        )
        .one_or_none()
    )


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

    Returns (answer_text, contexts, scores, latency_ms, tokens, graph_explanation, error).
    On permanent failure `error` is the last exception raised (so #19 can record it
    verbatim in the Registro de pausa) and the other values are None.
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
    return None, None, None, None, None, None, last_exc


# How often a question's future is polled for a stall signal while waiting on it.
# Small relative to the fractions-of-a-second limits the test suite injects.
_STALL_POLL_S = 0.02


class _Abandoned(Exception):
    """Raised by `_await_or_abandon` when `stall_event` fires before the call returns.

    ADR 0001: Python cannot kill a thread, so whatever was running is left running,
    unobserved, in the background — its result (if it ever produces one) is never
    read by anyone. Every blocking stage a Travamento can interrupt (question
    generation in `_run_questions`, and, since round 2 of #20, question
    vectorization, scoring and the difficulty-signal stages that used to run
    straight on the main thread) raises or propagates this the same way, so
    `_run_experiment` has one single thing to catch.
    """


def _await_or_abandon(
    future: Future, stall_event: threading.Event | None, poll_s: float = _STALL_POLL_S,
):
    """Return `future`'s result, polling every `poll_s`.

    Raises `_Abandoned` the first time `stall_event` is found set, instead of
    waiting for `future` any further. `stall_event=None` means "no watchdog is
    running for this call": it then simply blocks until `future` resolves.
    """
    while True:
        try:
            return future.result(timeout=poll_s)
        except _FutureTimeoutError:
            if stall_event is not None and stall_event.is_set():
                raise _Abandoned from None


def _run_abandonable(fn: Callable[[], object], stall_event: threading.Event | None):
    """Run `fn` on its own worker thread so it can be abandoned mid-call (#20 round 2).

    Lets the blocking stages outside `_run_questions` (question vectorization,
    scoring, evidence distance, perplexity) be given up on too, the same way a
    stuck question already was: on its own thread, polled rather than awaited, so
    a Travamento never leaves the orchestrator's main loop stuck inside a call it
    cannot interrupt.

    `fn` must never touch the SQLAlchemy Session — it is not thread-safe, and the
    caller is the only one allowed to use it. `fn` should only compute and return
    a plain value for the caller to persist once this returns normally. Raises
    `_Abandoned` (never `fn`'s own late result, read or otherwise) when
    `stall_event` fires first; the worker thread is then left running, exactly
    like an abandoned question in `_run_questions`.
    """
    pool = ThreadPoolExecutor(max_workers=1)
    future = pool.submit(fn)
    abandoned = False
    try:
        return _await_or_abandon(future, stall_event)
    except _Abandoned:
        abandoned = True
        raise
    finally:
        pool.shutdown(wait=not abandoned, cancel_futures=abandoned)


def _run_questions(
    rag, questions: list[QuestionItem], metrics: list, eval_embedder,
    concurrency: int, experiment_id: int, combo: dict, tracker: "_InFlightTracker",
    stall_event: threading.Event | None = None,
) -> Iterator[tuple[QuestionItem, tuple | None]]:
    """Yield (question, outcome) in question order, running up to `concurrency` at once.

    The outcome is None for a question skipped because a pause was requested
    before it started, or because `stall_event` fired while this call was still
    waiting on it. The second case is the Travamento watchdog abandoning a stuck
    call (ADR 0001): every question runs on its own worker thread (even with
    concurrency 1), so the loop can give up waiting on one without blocking.
    Nothing here ever reads a future's result once it has been abandoned, so a
    late answer — the call unblocking well after the fact — is never recorded.

    Questions are submitted in a sliding window of at most `concurrency`, one
    at a time, each only once the caller has consumed an earlier outcome (not
    eagerly, all at once): a pause requested while processing that outcome —
    manual, Falhas consecutivas, or Travamento — is visible to `work()`'s own
    check before the next question starts. Submitting every question up front
    (as `ThreadPoolExecutor.map` would) loses that ordering at concurrency 1,
    where the loop used to run `work()` inline on its own thread: nothing would
    then stop a second, third, ... question from starting before the result
    that should have paused them was even recorded.

    Each question is registered on `tracker` for the span of its call, so a
    pause entry recorded while it runs (or stuck) can show it under `in_flight`.
    """

    def work(question: QuestionItem):
        if _pause_requested(experiment_id):
            return None
        token = tracker.start(combo, question.text)
        try:
            return _process_question_with_retry(rag, question, metrics, eval_embedder)
        finally:
            tracker.finish(token)

    pool = ThreadPoolExecutor(max_workers=max(concurrency, 1))
    window = max(concurrency, 1)
    pending = list(questions)
    in_flight: list[tuple[QuestionItem, Future]] = []
    abandoned = False

    def _fill_window() -> None:
        while pending and len(in_flight) < window:
            question = pending.pop(0)
            in_flight.append((question, pool.submit(work, question)))

    try:
        _fill_window()
        while in_flight:
            question, future = in_flight.pop(0)
            if abandoned:
                yield question, None
                continue
            try:
                outcome = _await_or_abandon(future, stall_event)
            except _Abandoned:
                abandoned = True
                outcome = None
            yield question, outcome
            if not abandoned:
                _fill_window()  # only now: after the caller has seen this outcome
        # Never submitted (the window stopped filling once abandoned): still one
        # yield per question, same as a pause caught before it started.
        for question in pending:
            yield question, None
    finally:
        # A stalled call is abandoned, not awaited (ADR 0001: Python cannot kill a
        # thread). shutdown(wait=True) here would block on the very thread this
        # loop just gave up on; a clean pass has nothing left running and shuts
        # down normally.
        pool.shutdown(wait=not abandoned, cancel_futures=abandoned)


def run_experiment(
    experiment_id: int,
    config: ExperimentConfig,
    questions: list[QuestionItem],
    deps: ExperimentDeps,
) -> None:
    """Run the experiment once the single experiment slot is free."""
    if config.eval_embedding is None:
        config = config.model_copy(update={"eval_embedding": get_eval_embedding()})
    # One experiment (or Grafo build) at a time: queued ones stay "pending" ("Na fila").
    with work_slot:
        _run_experiment(experiment_id, config, questions, deps)


def resume_experiment(experiment_id: int, deps: ExperimentDeps) -> None:
    """Retomada: run a paused (or failed) experiment again, continuing from the database.

    Sibling of `run_experiment`, scheduled by `POST /experiments/{id}/resume`. The
    config and questions were recorded with the experiment at creation (#16) instead of
    living only in the background task's memory, so a Retomada can read them back even
    after an API restart. It then runs through the very same `_run_experiment` loop and
    work slot: a Combinação with a `done` `ExperimentRun` is skipped, one `paused` or
    `running` is reused (its `[ERRO]` rows are deleted and only unanswered questions
    run), and one with no `ExperimentRun` yet is created — see `_existing_run`. The most
    recent Registro de pausa entry gets `resumed_at` before the run starts.
    """
    session = deps.session_factory()
    try:
        experiment = session.get(Experiment, experiment_id)
        config = ExperimentConfig(**(experiment.config or {}))
        questions = [QuestionItem(**d) for d in (experiment.questions or [])]
        if experiment.pauses:
            pauses = list(experiment.pauses)
            pauses[-1] = {**pauses[-1], "resumed_at": datetime.now(UTC).isoformat()}
            experiment.pauses = pauses
            session.commit()
    finally:
        session.close()
    run_experiment(experiment_id, config, questions, deps)


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


def _compute_evidence_distances(
    deps: ExperimentDeps, config: ExperimentConfig, device: str, pending: list[tuple[int, str, str]],
) -> dict[int, float]:
    """QuestionProfile id -> GRADE distance for each (id, question, evidence) triple.

    Touches no Session (runs off-thread, under `_run_abandonable`): the caller
    applies the result to the profiles and commits on the main thread.
    """
    with deps.models.acquire(config.eval_embedding, device) as embedder:
        return {pid: evidence_distance(embedder, question, text) for pid, question, text in pending}


def _store_evidence_distances(
    session: Session,
    experiment_id: int,
    config: ExperimentConfig,
    deps: ExperimentDeps,
    questions: list[QuestionItem],
    device: str,
    stall_event: threading.Event | None = None,
) -> None:
    """Add GRADE's question-evidence distance to the profiles, with the eval embedder.

    Runs after generation, when the LLM no longer holds the memory, on an
    abandonable worker thread (#20 round 2). Optional: any failure besides a
    Travamento (`_Abandoned`, let through so `_run_experiment` can pause) is
    logged and the experiment still finishes.
    """
    evidence = {q.text: q.evidence for q in questions if q.evidence}
    profiles = [
        p
        for p in session.query(QuestionProfile).filter_by(experiment_id=experiment_id)
        if p.question in evidence and "evidence_distance" not in (p.signals or {})
    ]
    if not profiles:
        return
    pending = [(p.id, p.question, evidence[p.question]) for p in profiles]
    by_id = {p.id: p for p in profiles}
    try:
        distances = _run_abandonable(
            lambda: _compute_evidence_distances(deps, config, device, pending), stall_event,
        )
    except _Abandoned:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("evidence distance skipped: %s", exc)
        return
    for pid, distance in distances.items():
        profile = by_id[pid]
        profile.signals = {**profile.signals, "evidence_distance": distance}
    session.commit()


def _compute_perplexities(
    perplexity_scorer_factory: Callable, llm_name: str, texts: list[str],
) -> dict[str, float] | None:
    """Perplexity of every text under `llm_name`, or None when it cannot be scored.

    Touches no Session (runs off-thread, under `_run_abandonable`): may raise
    `PerplexitySkipped` (not enough memory) same as `cached_perplexities` itself.
    """
    scorer = perplexity_scorer_factory(llm_name)
    if scorer is None:
        return None
    return cached_perplexities(scorer, llm_name, texts)


def _store_perplexities(
    session: Session,
    experiment_id: int,
    config: ExperimentConfig,
    deps: ExperimentDeps,
    questions: list[QuestionItem],
    stall_event: threading.Event | None = None,
) -> None:
    """Score each distinct question once per local LLM that supports it (perplexity).

    The question is the same across every combination, so it is scored once per
    model, not per run; scores already known to this process are reused. Each
    model's scoring runs on an abandonable worker thread (#20 round 2). Optional:
    any failure besides a Travamento (`_Abandoned`, let through so `_run_experiment`
    can pause) is logged and the experiment still finishes.
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
        try:
            scores = _run_abandonable(
                lambda name=llm_name: _compute_perplexities(deps.perplexity_scorer_factory, name, texts),
                stall_event,
            )
        except _Abandoned:
            raise
        except PerplexitySkipped as exc:
            logger.warning("perplexity skipped for %s: %s", llm_name, exc)
            skipped[llm_name] = {"free_mb": exc.free_mb, "needed_mb": exc.needed_mb}
            continue
        except Exception as exc:  # noqa: BLE001
            logger.warning("perplexity failed for %s: %s", llm_name, exc)
            skipped[llm_name] = {"error": str(exc)[:300]}
            continue
        if scores is None:
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


def _score_pending(
    deps: ExperimentDeps, config: ExperimentConfig, device: str,
    pending: list[tuple[int, EvalSample]],
) -> dict[int, dict[str, float]]:
    """Score every (RunResult id, EvalSample) pair; touches no Session (runs off-thread).

    The whole point of splitting this out of `_score_results`: it is the part that
    can block on the eval embedder, so it is the part `_run_abandonable` runs on a
    worker thread (#20 round 2). Returns run_result_id -> scores for the caller to
    apply and commit back on the main thread.
    """
    eval_context = (
        deps.models.acquire(config.eval_embedding, device)
        if metrics_need_embedder(config.metrics)
        else nullcontext(None)
    )
    with eval_context as eval_embedder:
        return {
            row_id: _score_with_retry(sample, config.metrics, eval_embedder)
            for row_id, sample in pending
        }


def _score_results(
    session: Session, experiment_id: int, config: ExperimentConfig, deps: ExperimentDeps,
    stall_event: threading.Event | None = None,
) -> None:
    """Stage C: free the LLM, load the eval embedder once, score every stored answer.

    The scoring itself runs on an abandonable worker thread (#20 round 2), same as
    question generation: a Travamento here no longer leaves the orchestrator's main
    loop stuck forever. Only this function's own Session reads/writes (picking the
    pending rows, then applying their scores) stay on the calling thread.
    """
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
    by_id = {row.id: row for row in pending}
    samples = [
        (
            row.id,
            EvalSample(
                question=row.question,
                answer=row.generated_answer,
                contexts=[c.get("text", "") for c in row.retrieved_context],
                reference_answer=row.reference_answer,
                reference_contexts=row.reference_contexts,
                reference_hops=row.evidence_hops,
            ),
        )
        for row in pending
    ]
    scores_by_id = _run_abandonable(lambda: _score_pending(deps, config, device, samples), stall_event)
    for row_id, scores in scores_by_id.items():
        by_id[row_id].scores = scores
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
    watchdog: StallWatchdog | None = None
    try:
        experiment = session.get(Experiment, experiment_id)
        experiment.status = "running"
        session.commit()
        _store_question_profiles(session, experiment_id, config.base, questions, deps.store)

        stall_limit_s = deps.stall_limit_s if deps.stall_limit_s is not None else get_stall_limit_s()
        # Half the Travamento limit: a call that outlasts it fails on its own,
        # entering the usual retry path, well before the watchdog would fire.
        call_timeout_s = stall_limit_s / 2
        # Same per-call timeout given to every LLM call also reaches remote embedders
        # (e.g. Gemini), through the ModelManager's own `_load` (never local ones: they
        # may not accept the kwarg). Cleared in `finally` so it never outlives this run
        # on `deps.models` when that is the shared, process-wide manager.
        deps.models.set_timeout(call_timeout_s)
        stall_event = threading.Event()

        def _on_stall() -> None:
            # Runs on the watchdog's own thread: no session/ORM access here, only
            # the module-level pause request and this run's abandon signal.
            request_pause(
                experiment_id, reason="stall", score_partial=False,
                detail={"message": f"Travamento: sem progresso por {stall_limit_s:.0f}s"},
            )
            stall_event.set()

        watchdog = StallWatchdog(stall_limit_s, _on_stall).start()

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
        paused = False
        pause_phase: str | None = None
        pause_in_flight: list[dict] = []
        tracker = _InFlightTracker()
        failures = _ConsecutiveFailureTracker()
        loaded_llm_name, llm = None, None

        vectors: dict[str, dict[str, list[float]]] = {}
        if staged:
            # Stage A: can stall just like any other blocking call (#20 round 2) —
            # abandoned on its own worker thread, before any Combinação starts.
            _set_phase(session, experiment, "vectorizing")
            watchdog.heartbeat()
            try:
                vectors = _run_abandonable(
                    lambda: _question_vectors(deps, config, questions, device), stall_event,
                )
            except _Abandoned:
                paused = True
                pause_phase = "vectorizing"
            else:
                _set_phase(session, experiment, "generating")
                watchdog.heartbeat()
        eval_context = (
            deps.models.acquire(config.eval_embedding, device)
            if not staged and metrics_need_embedder(config.metrics)
            else nullcontext(None)
        )
        inline_metrics = [] if staged else config.metrics

        if not paused:
            with eval_context as eval_embedder, LeaseSwitcher(deps.models) as leases:
                for llm_name, (chunking, embedding), rag_name, retriever_name in _combinations(config):
                    # Checkpoint: stop before starting a new combination if paused.
                    if _pause_requested(experiment_id):
                        paused = True
                        break

                    # Retomada (#17): a Combinação already `done` is skipped; one `paused`
                    # or `running` is reused (its [ERRO] rows redone, valid ones kept); one
                    # with no ExperimentRun yet is created, exactly as on a first run.
                    run = _existing_run(
                        session, experiment_id, chunking, embedding, rag_name, retriever_name, llm_name,
                    )
                    if run is not None and run.status == "done":
                        continue
                    if run is None:
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
                        answered: set[str] = set()
                    else:
                        run.status = "running"
                        existing_results = list(run.results)
                        answered = {
                            r.question for r in existing_results
                            if not r.generated_answer.startswith(ERROR_PREFIX)
                        }
                        for result in existing_results:
                            if result.generated_answer.startswith(ERROR_PREFIX):
                                session.delete(result)
                    session.commit()
                    watchdog.heartbeat()  # a Combinação just started

                    if llm_name != loaded_llm_name:
                        llm, loaded_llm_name = deps.llm_factory(llm_name, timeout=call_timeout_s), llm_name
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
                        # Only queries: the Grafo was built beforehand (ingestion or a
                        # Grafo build), by the LLM extrator the experiment chose.
                        graph = (
                            current_graph(deps.store, config.base, chunking, embedding,
                                          config.graph_extractor)
                            if config.graph_extractor else None
                        )
                        if graph is None:
                            # The API checks this up front; the Grafo can still go stale
                            # (re-ingested Índice, edited prompt) while the run waits.
                            logger.error("no current Grafo for run %d", run.id)
                            for question in questions:
                                if question.text in answered:
                                    continue  # a Retomada never redoes a valid answer
                                session.add(_error_result(run.id, question, (
                                    f"Grafo: não há Grafo de conhecimento atual do LLM extrator "
                                    f"{config.graph_extractor} para {chunking} × {embedding}"
                                )))
                            run.status = "done"
                            session.commit()
                            continue
                        run.graph_stats = {**graph.stats, "extractor": graph.extractor}
                        session.commit()
                        rag_kwargs.update(graph=graph, embedder=embedder)
                    rag = deps.rag_factory(rag_name, **rag_kwargs)

                    # The oracle answers from the reference evidence: only questions with one.
                    run_questions = (
                        [q for q in questions if q.evidence]
                        if getattr(rag, "uses_evidence", False)
                        else questions
                    )
                    # Retomada: a question already answered (not [ERRO]) never runs again.
                    if answered:
                        run_questions = [q for q in run_questions if q.text not in answered]
                    combo = {
                        "chunking": chunking, "embedding": embedding,
                        "rag": rag_name, "retriever": retriever_name, "llm": llm_name,
                    }
                    # DB writes stay on this thread: the Session is not thread-safe.
                    for question, outcome in _run_questions(
                        rag, run_questions, inline_metrics, eval_embedder, concurrency, experiment_id,
                        combo, tracker, stall_event=stall_event,
                    ):
                        # Checkpoint: questions not started before a pause are skipped,
                        # and so is a question _run_questions gave up waiting on because
                        # the watchdog fired (abandoned, never recorded — ADR 0001).
                        if outcome is None:
                            if not paused:
                                # First detection: snapshot whatever is still mid-call right
                                # now, before it has a chance to finish and clear itself.
                                paused = True
                                pause_in_flight = tracker.snapshot()
                            continue

                        answer_text, contexts, scores, latency_ms, tokens, explanation, error = outcome
                        if error is not None:
                            session.add(_error_result(run.id, question, str(error)))
                            if failures.record_failure():
                                # #19: this question's failure was the 3rd in a row (any
                                # Combinação) — pause now, without scoring, keeping the
                                # last exception for the Registro de pausa entry.
                                request_pause(
                                    experiment_id, reason="consecutive_failures", score_partial=False,
                                    detail=_error_detail(error),
                                )
                        else:
                            failures.record_success()
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
                        watchdog.heartbeat()  # a result was just recorded
                    logger.info("run %d finished; API memory %.0f MB", run.id, process_memory_bytes() / 1e6)

                    if paused:
                        run.status = "paused"
                        session.commit()
                        break

                    run.status = "done"
                    session.commit()

        # The phase a pause interrupted, captured before scoring (which would move
        # it to "evaluating") or the final clear below overwrite it. Vectorization's
        # own abandon already set this; a pause from inside the combinations loop
        # (checkpoint or a Travamento during generation) has not, so read it now.
        if paused and pause_phase is None:
            pause_phase = (experiment.config or {}).get("phase")
        pause_request = _pause_requests.get(experiment_id) if paused else None
        score_partial = pause_request is None or pause_request.score_partial

        if staged and score_partial:
            # Scores what was generated, paused or not — unless the pause asked to
            # skip scoring (#19/#20: free the machine right away).
            _set_phase(session, experiment, "evaluating")
            watchdog.heartbeat()
            try:
                _score_results(session, experiment_id, config, deps, stall_event)
            except _Abandoned:
                paused = True
                pause_phase = "evaluating"
                pause_request = _pause_requests.get(experiment_id)
                score_partial = pause_request is None or pause_request.score_partial
        if score_partial:
            _set_phase(session, experiment, "difficulty_signals")
            watchdog.heartbeat()
            try:
                _store_evidence_distances(
                    session, experiment_id, config, deps, questions,
                    resolve_embedding_device(active_profile()) if staged else device,
                    stall_event,
                )
                _store_perplexities(session, experiment_id, config, deps, questions, stall_event)
            except _Abandoned:
                paused = True
                pause_phase = "difficulty_signals"
                pause_request = _pause_requests.get(experiment_id)
                score_partial = pause_request is None or pause_request.score_partial
        experiment.status = "paused" if paused else "done"
        experiment.finished_at = datetime.now(UTC)
        _set_phase(session, experiment, None)
        if paused:
            record_pause(
                session, experiment,
                reason=pause_request.reason if pause_request else "manual",
                phase=pause_phase,
                in_flight=pause_in_flight,
                last_error=pause_request.detail if pause_request else None,
            )
    except Exception as exc:  # noqa: BLE001  background task records failure, never raises
        session.rollback()
        experiment = session.get(Experiment, experiment_id)
        if experiment is not None:
            experiment.status = "failed"
            config_without_phase = {k: v for k, v in (experiment.config or {}).items() if k != "phase"}
            # error kept on config for compatibility; the pauses entry is the new source.
            experiment.config = {**config_without_phase, "error": str(exc)}
            experiment.finished_at = datetime.now(UTC)
            session.commit()
            record_pause(
                session, experiment,
                reason="failed", phase=config_without_phase.get("phase"),
                last_error=_error_detail(exc),
            )
    finally:
        if watchdog is not None:
            watchdog.stop()  # the run is over either way: never fire after this
        deps.models.set_timeout(None)  # never outlive this run on a shared manager
        _pause_requests.pop(experiment_id, None)
        session.close()
