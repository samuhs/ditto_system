"""Rodadas de anotação: sampling answers from Experimentos and recording the Avaliadores' notes."""
import random

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.annotation.rubric import RUBRIC_VERSION
from app.core.db.models import (
    AnnotationItem,
    AnnotationNote,
    AnnotationRound,
    Annotator,
    Experiment,
    ExperimentRun,
    RunResult,
)
from app.experiments.orchestrator import ERROR_PREFIX


class AnnotationError(Exception):
    """A request the Anotação cannot serve; `status` is the HTTP status to answer with."""

    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status


def _context_text(context) -> str:
    return context.get("text", "") if isinstance(context, dict) else str(context)


def _valid_results(session: Session, experiment_id: int) -> list[tuple[RunResult, ExperimentRun]]:
    rows = session.execute(
        select(RunResult, ExperimentRun)
        .join(ExperimentRun, RunResult.run_id == ExperimentRun.id)
        .where(ExperimentRun.experiment_id == experiment_id)
        .order_by(RunResult.id)
    ).all()
    return [(r, run) for r, run in rows
            if r.scores and not r.generated_answer.startswith(ERROR_PREFIX)]


def create_round(session: Session, name: str, experiment_id: int, sample_size: int,
                 seed: int | None = None, description: str = "") -> AnnotationRound:
    """Sample `sample_size` answered results of one Experimento into a new open Rodada."""
    if session.get(Experiment, experiment_id) is None:
        raise AnnotationError(f"Experimento {experiment_id} não existe.", status=404)
    pool = _valid_results(session, experiment_id)
    if sample_size > len(pool):
        raise AnnotationError(
            f"O Experimento {experiment_id} tem {len(pool)} respostas válidas; "
            f"não dá para sortear {sample_size}."
        )
    seed = random.SystemRandom().randrange(1, 10**6) if seed is None else seed
    picked = random.Random(seed).sample(pool, sample_size)
    rnd = AnnotationRound(name=name.strip(), description=description, seed=seed,
                          rubric_version=RUBRIC_VERSION, experiment_ids=[experiment_id])
    for position, (result, run) in enumerate(picked):
        rnd.items.append(AnnotationItem(
            position=position,
            source_result_id=result.id,
            experiment_id=experiment_id,
            combination={"chunking": run.chunking, "embedding": run.embedding,
                         "rag": run.rag_technique, "retriever": run.retriever, "llm": run.llm},
            question=result.question,
            question_type=result.question_type,
            reference_answer=result.reference_answer,
            evidence=list(result.reference_contexts or []),
            retrieved_context=[_context_text(c) for c in result.retrieved_context or []],
            generated_answer=result.generated_answer,
            auto_scores=dict(result.scores),
        ))
    session.add(rnd)
    session.commit()
    return rnd


def get_round(session: Session, round_id: int) -> AnnotationRound:
    rnd = session.get(AnnotationRound, round_id)
    if rnd is None:
        raise AnnotationError(f"Rodada {round_id} não existe.", status=404)
    return rnd


def get_annotator(session: Session, annotator_id: int) -> Annotator:
    annotator = session.get(Annotator, annotator_id)
    if annotator is None:
        raise AnnotationError(f"Avaliador {annotator_id} não existe.", status=404)
    return annotator


def round_summary(rnd: AnnotationRound, size: int | None = None) -> dict:
    """The Rodada's fields; `size` spares loading its Items when the caller already counted them."""
    return {
        "id": rnd.id, "name": rnd.name, "description": rnd.description, "status": rnd.status,
        "seed": rnd.seed, "rubric_version": rnd.rubric_version,
        "experiment_ids": list(rnd.experiment_ids),
        "size": len(rnd.items) if size is None else size,
        "created_at": rnd.created_at.isoformat() if rnd.created_at else None,
    }


def list_rounds(session: Session) -> list[dict]:
    """Rodadas newest first, counting Items in SQL instead of loading them."""
    counts = dict(session.execute(
        select(AnnotationItem.round_id, func.count()).group_by(AnnotationItem.round_id)
    ).all())
    rounds = session.scalars(select(AnnotationRound).order_by(AnnotationRound.id.desc()))
    return [round_summary(r, size=counts.get(r.id, 0)) for r in rounds]


def round_progress(session: Session, rnd: AnnotationRound) -> list[dict]:
    """Notes done per Avaliador who scored at least one Item of the Rodada."""
    rows = session.execute(
        select(Annotator, AnnotationNote)
        .join(AnnotationNote, AnnotationNote.annotator_id == Annotator.id)
        .join(AnnotationItem, AnnotationNote.item_id == AnnotationItem.id)
        .where(AnnotationItem.round_id == rnd.id)
        .order_by(Annotator.name)
    ).all()
    done: dict[int, list] = {}
    for annotator, note in rows:
        entry = done.setdefault(annotator.id, [annotator.name, 0])
        entry[1] += _is_done(note)
    return [{"annotator_id": aid, "name": name, "done": n, "total": len(rnd.items)}
            for aid, (name, n) in done.items()]


def _is_done(note: AnnotationNote | None) -> bool:
    return note is not None and note.correctness is not None


def queue(session: Session, rnd: AnnotationRound, annotator: Annotator) -> dict:
    """The Rodada as one Avaliador sees it: blind (no Técnica, LLM, Experimento or scores)."""
    notes = {n.item_id: n for n in session.scalars(
        select(AnnotationNote)
        .join(AnnotationItem, AnnotationNote.item_id == AnnotationItem.id)
        .where(AnnotationItem.round_id == rnd.id, AnnotationNote.annotator_id == annotator.id)
    )}
    items = []
    for item in rnd.items:
        note = notes.get(item.id)
        items.append({
            "id": item.id, "position": item.position, "question": item.question,
            "question_type": item.question_type, "reference_answer": item.reference_answer,
            "evidence": list(item.evidence), "retrieved_context": list(item.retrieved_context),
            "generated_answer": item.generated_answer,
            "note": ({"correctness": note.correctness, "grounding": note.grounding}
                     if note is not None else None),
        })
    return {"round": round_summary(rnd), "annotator": {"id": annotator.id, "name": annotator.name},
            "items": items, "done": sum(_is_done(notes.get(i.id)) for i in rnd.items),
            "total": len(rnd.items)}


def save_note(session: Session, item_id: int, annotator_id: int,
              correctness: int, grounding: int) -> AnnotationNote:
    item = session.get(AnnotationItem, item_id)
    if item is None:
        raise AnnotationError(f"Item {item_id} não existe.", status=404)
    get_annotator(session, annotator_id)
    if item.round.status != "open":
        raise AnnotationError("A Rodada está fechada: não aceita notas.", status=409)
    note = session.scalar(select(AnnotationNote).where(
        AnnotationNote.item_id == item_id, AnnotationNote.annotator_id == annotator_id))
    if note is None:
        note = AnnotationNote(item_id=item_id, annotator_id=annotator_id)
        session.add(note)
    note.correctness, note.grounding = correctness, grounding
    session.commit()
    return note
