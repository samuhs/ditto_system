"""Experiment orchestrator: run the cartesian product and persist results."""
import itertools
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.db.models import Experiment, ExperimentRun, RunResult
from app.core.embedding.base import build_embedder
from app.core.evaluation.base import EvalSample
from app.core.evaluation.runner import evaluate_sample
from app.core.llm.base import build_llm
from app.core.rag.base import build_rag
from app.core.retrieval.base import build_retriever
from app.core.vectorstore.qdrant import QdrantStore, collection_name
from app.experiments.schemas import ExperimentConfig, QuestionItem


@dataclass
class ExperimentDeps:
    """Injectable dependencies for running an experiment (overridable in tests)."""

    store: QdrantStore
    session_factory: Callable[[], Session]
    llm_factory: Callable = build_llm
    embedder_factory: Callable = build_embedder
    retriever_factory: Callable = build_retriever
    rag_factory: Callable = build_rag


def _build_retriever(deps: ExperimentDeps, name: str, collection: str, embedder, llm):
    """Build a retriever, injecting the llm only for retrievers that need it."""
    kwargs = {"store": deps.store, "collection": collection, "embedder": embedder}
    if name == "multi_query":
        kwargs["llm"] = llm
    return deps.retriever_factory(name, **kwargs)


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

        llm = deps.llm_factory(config.llm)
        eval_embedder = deps.embedder_factory(config.eval_embedding)

        for chunking, embedding, rag_name, retriever_name in itertools.product(
            config.chunkings, config.embeddings, config.rags, config.retrievers
        ):
            run = ExperimentRun(
                experiment_id=experiment_id,
                chunking=chunking,
                embedding=embedding,
                rag_technique=rag_name,
                retriever=retriever_name,
                status="running",
            )
            session.add(run)
            session.commit()

            embedder = deps.embedder_factory(embedding)
            col = collection_name(config.base, chunking, embedding)
            retriever = _build_retriever(deps, retriever_name, col, embedder, llm)
            rag = deps.rag_factory(rag_name, retriever=retriever, llm=llm)

            for question in questions:
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
                scores = evaluate_sample(sample, config.metrics, embedder=eval_embedder)
                session.add(
                    RunResult(
                        run_id=run.id,
                        question=question.text,
                        reference_answer=question.reference,
                        generated_answer=answer.answer,
                        retrieved_context=answer.contexts,
                        scores=scores,
                        latency_ms=latency_ms,
                        tokens=len(answer.answer.split()),
                    )
                )
            run.status = "done"
            session.commit()

        experiment.status = "done"
        experiment.finished_at = datetime.now(UTC)
        session.commit()
    except Exception as exc:  # noqa: BLE001  background task records failure, never raises
        session.rollback()
        experiment = session.get(Experiment, experiment_id)
        if experiment is not None:
            experiment.status = "failed"
            experiment.config = {**experiment.config, "error": str(exc)}
            session.commit()
    finally:
        session.close()
