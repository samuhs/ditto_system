"""Rodadas de anotação: sampling answers from Experimentos and recording the Avaliadores' notes."""
import random
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.annotation.agreement import (
    RESAMPLES,
    bootstrap_ci,
    confusion_matrix,
    krippendorff_alpha,
    spearman,
    weighted_kappa,
)
from app.annotation.rubric import DIMENSIONS, LEVELS, RUBRIC_VERSION
from app.core.db.models import (
    AnnotationAdjudication,
    AnnotationItem,
    AnnotationNote,
    AnnotationParticipant,
    AnnotationRound,
    Annotator,
    Experiment,
    ExperimentRun,
    RunResult,
)
from app.experiments.orchestrator import ERROR_PREFIX
from app.experiments.stats import mean_ci


class AnnotationError(Exception):
    """A request the Anotação cannot serve; `status` is the HTTP status to answer with."""

    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status


def _context_text(context) -> str:
    return context.get("text", "") if isinstance(context, dict) else str(context)


STRATA_DIMENSIONS = ("question_type", "rag", "llm")


def _parse_item(item: str) -> tuple[int, int]:
    try:
        experiment_id, run_id = (int(part) for part in item.split(":"))
    except ValueError as exc:
        raise AnnotationError(f"Combinação inválida: {item!r} (esperado experimento:combinação).") from exc
    return experiment_id, run_id


def resolve_runs(session: Session, items: list[str] | None,
                 experiment_id: int | None) -> list[tuple[Experiment, ExperimentRun]]:
    """The Combinações a Rodada samples from: the listed `items`, or every run of `experiment_id`.

    All of them must belong to the same Base: notes on answers from different Bases would
    mix two populations in one sample.
    """
    if items:
        pairs = []
        for item in dict.fromkeys(items):
            exp_id, run_id = _parse_item(item)
            run = session.get(ExperimentRun, run_id)
            if run is None or run.experiment_id != exp_id:
                raise AnnotationError(f"A Combinação {item} não existe.", status=404)
            pairs.append((run.experiment, run))
    else:
        experiment = session.get(Experiment, experiment_id) if experiment_id is not None else None
        if experiment is None:
            raise AnnotationError(f"Experimento {experiment_id} não existe.", status=404)
        pairs = [(experiment, run) for run in experiment.runs]
    running = sorted({exp.id for exp, _ in pairs if exp.status != "done"})
    if running:
        raise AnnotationError(
            "Experimento(s) ainda não concluído(s): " + ", ".join(f"#{i}" for i in running)
            + ". Sortear de um Experimento em andamento deixaria a amostra irreprodutível."
        )
    bases = {(exp.config or {}).get("base") for exp, _ in pairs}
    if len(bases) > 1:
        raise AnnotationError(
            "As Combinações vêm de Bases diferentes (" + ", ".join(sorted(map(str, bases))) + "); "
            "uma Rodada sorteia respostas de uma Base só."
        )
    return pairs


def _pool(session: Session, runs: list[tuple[Experiment, ExperimentRun]]) -> list[tuple[RunResult, ExperimentRun]]:
    by_id = {run.id: run for _, run in runs}
    results = session.scalars(
        select(RunResult).where(RunResult.run_id.in_(by_id)).order_by(RunResult.id)
    )
    return [(r, by_id[r.run_id]) for r in results
            if r.scores and not r.generated_answer.startswith(ERROR_PREFIX)]


def _stratum(result: RunResult, run: ExperimentRun, dims: list[str]) -> tuple:
    values = {"question_type": result.question_type or "", "rag": run.rag_technique, "llm": run.llm or ""}
    return tuple(values[d] for d in dims)


def allocate(available: dict[tuple, int], size: int, allocation: str) -> tuple[dict, dict]:
    """Split `size` among strata: (target before capping, final allocation).

    `equal` gives each stratum the same share; `proportional` follows the stratum sizes
    (largest remainder). A stratum with fewer answers than its share gives the shortfall to
    the others, one at a time in key order, so the Rodada keeps the requested size.
    """
    keys = sorted(available)
    total = sum(available.values())
    if allocation == "equal":
        base, extra = divmod(size, len(keys))
        target = {k: base + (i < extra) for i, k in enumerate(keys)}
    else:
        exact = {k: size * available[k] / total for k in keys}
        target = {k: int(exact[k]) for k in keys}
        by_remainder = sorted(keys, key=lambda k: (-(exact[k] - target[k]), keys.index(k)))
        for k in by_remainder[: size - sum(target.values())]:
            target[k] += 1
    final = {k: min(target[k], available[k]) for k in keys}
    deficit = size - sum(final.values())
    while deficit > 0:
        for k in keys:
            if deficit and final[k] < available[k]:
                final[k] += 1
                deficit -= 1
    return target, final


def _plan(session: Session, items, experiment_id, sample_size, strata, allocation):
    for dim in strata:
        if dim not in STRATA_DIMENSIONS:
            raise AnnotationError(f"Não dá para estratificar por {dim!r}.")
    runs = resolve_runs(session, items, experiment_id)
    pool = _pool(session, runs)
    if sample_size > len(pool):
        raise AnnotationError(
            f"As Combinações escolhidas têm {len(pool)} respostas válidas; "
            f"não dá para sortear {sample_size}."
        )
    groups: dict[tuple, list] = {}
    for result, run in pool:
        groups.setdefault(_stratum(result, run, strata), []).append((result, run))
    target, final = allocate({k: len(v) for k, v in groups.items()}, sample_size, allocation)
    return runs, pool, groups, target, final


def preview_round(session: Session, items: list[str] | None, experiment_id: int | None,
                  sample_size: int, strata: list[str], allocation: str) -> dict:
    """How many answers each stratum has and how many the Rodada would take from it."""
    _, pool, groups, target, final = _plan(session, items, experiment_id, sample_size, strata, allocation)
    return {
        "available": len(pool), "size": sample_size,
        "strata": [{"key": dict(zip(strata, k)), "available": len(groups[k]),
                    "allocated": final[k], "short": target[k] > len(groups[k])}
                   for k in sorted(groups)],
    }


def create_round(session: Session, name: str, sample_size: int, *, items: list[str] | None = None,
                 experiment_id: int | None = None, seed: int | None = None, description: str = "",
                 strata: list[str] | None = None, allocation: str = "proportional",
                 pilot: bool = False) -> AnnotationRound:
    """Sample `sample_size` answered results of the chosen Combinações into a new open Rodada."""
    strata = list(strata or [])
    runs, _, groups, _, final = _plan(session, items, experiment_id, sample_size, strata, allocation)
    seed = random.SystemRandom().randrange(1, 10**6) if seed is None else seed
    rng = random.Random(seed)
    picked = [pair for k in sorted(groups) for pair in rng.sample(groups[k], final[k])]
    # Shuffled so the queue never shows one stratum (a Técnica, an LLM) in a block.
    rng.shuffle(picked)
    rnd = AnnotationRound(name=name.strip(), description=description, seed=seed,
                          rubric_version=RUBRIC_VERSION, pilot=pilot, strata=strata,
                          allocation=allocation,
                          experiment_ids=list(dict.fromkeys(exp.id for exp, _ in runs)))
    for position, (result, run) in enumerate(picked):
        rnd.items.append(AnnotationItem(
            position=position,
            source_result_id=result.id,
            experiment_id=run.experiment_id,
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
        "seed": rnd.seed, "rubric_version": rnd.rubric_version, "pilot": bool(rnd.pilot),
        "strata": list(rnd.strata or []), "allocation": rnd.allocation or "proportional",
        "adjudicator_id": rnd.adjudicator_id,
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
    """Notes done per Avaliador who joined the Rodada or scored at least one of its Items."""
    names = dict(session.execute(
        select(Annotator.id, Annotator.name)
        .join(AnnotationParticipant, AnnotationParticipant.annotator_id == Annotator.id)
        .where(AnnotationParticipant.round_id == rnd.id, AnnotationParticipant.removed_at.is_(None))
    ).all())
    done: dict[int, int] = dict.fromkeys(names, 0)
    rows = session.execute(
        select(Annotator.id, Annotator.name, AnnotationNote)
        .join(AnnotationNote, AnnotationNote.annotator_id == Annotator.id)
        .join(AnnotationItem, AnnotationNote.item_id == AnnotationItem.id)
        .where(AnnotationItem.round_id == rnd.id)
    ).all()
    for annotator_id, name, note in rows:
        names[annotator_id] = name
        done[annotator_id] = done.get(annotator_id, 0) + _is_done(note)
    total = len(rnd.items)
    return [{"annotator_id": aid, "name": names[aid], "done": done[aid], "total": total}
            for aid in sorted(names, key=lambda a: names[a].lower())]


def _participant(session: Session, round_id: int, annotator_id: int) -> AnnotationParticipant | None:
    return session.scalar(select(AnnotationParticipant).where(
        AnnotationParticipant.round_id == round_id, AnnotationParticipant.annotator_id == annotator_id))


def _add_participant(session: Session, round_id: int, annotator_id: int) -> None:
    session.add(AnnotationParticipant(round_id=round_id, annotator_id=annotator_id))
    try:
        session.commit()
    except IntegrityError:  # joined at the same moment by a second request: already in
        session.rollback()


def join_round(session: Session, rnd: AnnotationRound, annotator: Annotator) -> None:
    """Make the Avaliador a participant of an open Rodada (joining twice is a no-op;
    joining after a removal brings them back)."""
    if rnd.status != "open":
        raise AnnotationError("A Rodada está fechada.", status=409)
    if not annotator.active:
        raise AnnotationError(f"{annotator.name} está desativado.", status=409)
    participant = _participant(session, rnd.id, annotator.id)
    if participant is None:
        _add_participant(session, rnd.id, annotator.id)
    elif participant.removed_at is not None:
        participant.removed_at = None
        session.commit()


def remove_participant(session: Session, rnd: AnnotationRound, annotator_id: int) -> int:
    """Drop an Avaliador from a Rodada with all their notes in it; returns how many notes went.

    The removal is recorded (not deleted), so a screen still open with the old queue cannot
    quietly bring the Avaliador back by saving: they must pick the Rodada again.
    """
    if rnd.status != "open":
        raise AnnotationError("A Rodada está fechada: as notas estão congeladas.", status=409)
    participant = _participant(session, rnd.id, annotator_id)
    notes = list(session.scalars(
        select(AnnotationNote)
        .join(AnnotationItem, AnnotationNote.item_id == AnnotationItem.id)
        .where(AnnotationItem.round_id == rnd.id, AnnotationNote.annotator_id == annotator_id)
    ))
    active = participant is not None and participant.removed_at is None
    if not active and not notes:
        raise AnnotationError("Esse avaliador não participa desta Rodada.", status=404)
    for note in notes:
        session.delete(note)
    if participant is None:
        participant = AnnotationParticipant(round_id=rnd.id, annotator_id=annotator_id)
        session.add(participant)
    participant.removed_at = datetime.now(UTC).replace(tzinfo=None)
    session.commit()
    return len(notes)


def _order(rnd: AnnotationRound, annotator_id: int) -> list[AnnotationItem]:
    """The Rodada's Items in this Avaliador's own order: a stable permutation per (seed, Avaliador),
    so the order of presentation does not bias every Avaliador the same way."""
    items = list(rnd.items)
    random.Random(f"{rnd.seed}:{annotator_id}").shuffle(items)
    return items


def _is_done(note: AnnotationNote | None) -> bool:
    return note is not None and (note.correctness is not None or bool(note.cannot_evaluate))


def note_out(note: AnnotationNote) -> dict:
    return {"correctness": note.correctness, "grounding": note.grounding,
            "cannot_evaluate": bool(note.cannot_evaluate), "reason": note.reason, "comment": note.comment}


def _check_note(item: AnnotationItem, correctness, grounding, cannot_evaluate, reason) -> None:
    """The Rubrica's rules for one note on one Item."""
    if cannot_evaluate:
        if not (reason or "").strip():
            raise AnnotationError("Diga por que não dá para avaliar.")
        if correctness is not None or grounding is not None:
            raise AnnotationError("Quem não consegue avaliar não dá notas.")
        return
    if correctness is None:
        raise AnnotationError("Falta a nota de Correção.")
    if item.retrieved_context and grounding is None:
        raise AnnotationError("Falta a nota de Fundamentação.")
    if not item.retrieved_context and grounding is not None:
        raise AnnotationError("Sem trechos recuperados, a Fundamentação não se aplica.")


def queue(session: Session, rnd: AnnotationRound, annotator: Annotator) -> dict:
    """The Rodada as one Avaliador sees it: blind (no Técnica, LLM, Experimento or scores)."""
    notes = {n.item_id: n for n in session.scalars(
        select(AnnotationNote)
        .join(AnnotationItem, AnnotationNote.item_id == AnnotationItem.id)
        .where(AnnotationItem.round_id == rnd.id, AnnotationNote.annotator_id == annotator.id)
    )}
    items = []
    for item in _order(rnd, annotator.id):
        note = notes.get(item.id)
        items.append({
            "id": item.id, "position": item.position, "question": item.question,
            "question_type": item.question_type, "reference_answer": item.reference_answer,
            "evidence": list(item.evidence), "retrieved_context": list(item.retrieved_context),
            "generated_answer": item.generated_answer,
            "grounding_applicable": bool(item.retrieved_context),
            "note": note_out(note) if note is not None else None,
        })
    return {"round": round_summary(rnd), "annotator": {"id": annotator.id, "name": annotator.name},
            "items": items, "done": sum(_is_done(notes.get(i.id)) for i in rnd.items),
            "total": len(rnd.items)}


def save_note(session: Session, item_id: int, annotator_id: int, correctness: int | None,
              grounding: int | None, cannot_evaluate: bool = False, reason: str | None = None,
              comment: str | None = None) -> AnnotationNote:
    item = session.get(AnnotationItem, item_id)
    if item is None:
        raise AnnotationError(f"Item {item_id} não existe.", status=404)
    get_annotator(session, annotator_id)
    if item.round.status != "open":
        raise AnnotationError("A Rodada está fechada: não aceita notas.", status=409)
    _check_note(item, correctness, grounding, cannot_evaluate, reason)
    participant = _participant(session, item.round_id, annotator_id)
    if participant is not None and participant.removed_at is not None:
        raise AnnotationError("Você foi removido desta Rodada. Escolha a rodada de novo para voltar.",
                              status=409)
    if participant is None:  # scoring is participating
        _add_participant(session, item.round_id, annotator_id)
    note = session.scalar(select(AnnotationNote).where(
        AnnotationNote.item_id == item_id, AnnotationNote.annotator_id == annotator_id))
    if note is None:
        note = AnnotationNote(item_id=item_id, annotator_id=annotator_id)
        session.add(note)
    note.correctness, note.grounding = correctness, grounding
    note.cannot_evaluate = cannot_evaluate
    note.reason = reason.strip() if cannot_evaluate and reason else None
    note.comment = (comment or "").strip() or None
    session.commit()
    return note


def close_round(session: Session, rnd: AnnotationRound) -> AnnotationRound:
    """Freeze the notes of a Rodada before analysing them."""
    rnd.status = "closed"
    session.commit()
    return rnd


def _ci(value, interval) -> dict:
    low, high = interval if interval else (None, None)
    return {"value": value, "low": low, "high": high}


# A closed Rodada's notes never change, so its Concordância is computed once per process.
_closed_agreement: dict[tuple[int, int, int], dict] = {}


def round_agreement(session: Session, rnd: AnnotationRound, resamples: int = RESAMPLES) -> dict:
    """The Concordância of a Rodada; cached once the Rodada is closed (the bootstrap takes seconds)."""
    if rnd.status != "open":
        key = (id(session.get_bind()), rnd.id, resamples)  # the bind keeps test databases apart
        if key not in _closed_agreement:
            _closed_agreement[key] = _compute_agreement(session, rnd, resamples)
        return _closed_agreement[key]
    return _compute_agreement(session, rnd, resamples)


def _compute_agreement(session: Session, rnd: AnnotationRound, resamples: int) -> dict:
    """Concordância per Rubrica dimension: Krippendorff's ordinal alpha (2+ Avaliadores) and,
    with exactly two, quadratic-weighted kappa and the confusion matrix; plus the Items where
    the Avaliadores disagree. A score left out ("não se aplica", "não consigo avaliar") is a
    missing value for that dimension."""
    by_item, names = _notes_by_item(session, rnd)
    value = _value

    dimensions = {}
    for dim in DIMENSIONS:
        units = [[value(by_item.get(item.id, {}).get(n), dim) for n in names] for item in rnd.items]
        pairable = [u for u in units if sum(v is not None for v in u) >= 2]
        alpha = krippendorff_alpha(pairable)
        alpha_ci = bootstrap_ci(pairable, krippendorff_alpha, resamples) if alpha is not None else None
        entry = {"n": len(pairable), "alpha": _ci(alpha, alpha_ci), "kappa": None, "confusion": None}
        if len(names) == 2:
            pairs = [(u[0], u[1]) for u in pairable]
            a, b = [p[0] for p in pairs], [p[1] for p in pairs]
            kappa = weighted_kappa(a, b, LEVELS)
            if kappa is not None:
                def kappa_of(ps):
                    return weighted_kappa([p[0] for p in ps], [p[1] for p in ps], LEVELS)
                ci = bootstrap_ci(pairs, kappa_of, resamples)
                entry["kappa"] = _ci(kappa, ci)
            if pairs:
                entry["confusion"] = {"avaliadores": names, "levels": list(LEVELS),
                                      "matrix": confusion_matrix(a, b, LEVELS)}
        dimensions[dim] = entry

    disagreements = []
    for item in rnd.items:
        notes = by_item.get(item.id, {})
        if _disputed(notes):
            disagreements.append({
                "item_id": item.id, "position": item.position, "question": item.question,
                "generated_answer": item.generated_answer,
                "notes": {name: note_out(note) for name, note in sorted(notes.items())},
            })
    return {
        "round": round_summary(rnd), "avaliadores": names, "dimensions": dimensions,
        "disagreements": disagreements,
        "note": ("A Concordância precisa de pelo menos dois avaliadores nas mesmas respostas "
                 "(ou de uma rodada de reteste)." if len(names) < 2 else None),
    }


def _notes_by_item(
    session: Session, rnd: AnnotationRound,
) -> tuple[dict[int, dict[str, AnnotationNote]], list[str]]:
    """The Rodada's notes per Item, keyed by Avaliador name, and the names in order."""
    rows = session.execute(
        select(AnnotationNote, Annotator.name)
        .join(Annotator, AnnotationNote.annotator_id == Annotator.id)
        .join(AnnotationItem, AnnotationNote.item_id == AnnotationItem.id)
        .where(AnnotationItem.round_id == rnd.id)
    ).all()
    by_item: dict[int, dict[str, AnnotationNote]] = {}
    for note, name in rows:
        by_item.setdefault(note.item_id, {})[name] = note
    return by_item, sorted({name for _, name in rows}, key=str.lower)


def _value(note: AnnotationNote | None, dim: str):
    """A score as it counts for agreement: missing when left out or not evaluable."""
    if note is None or note.cannot_evaluate:
        return None
    return getattr(note, dim)


def _disputed(notes: dict[str, AnnotationNote]) -> list[str]:
    """The dimensions where the Avaliadores gave different scores."""
    return [dim for dim in DIMENSIONS if len({_value(n, dim) for n in notes.values()} - {None}) > 1]


def _scored(session: Session, rnd: AnnotationRound, annotator_id: int) -> bool:
    return bool(session.scalar(
        select(func.count()).select_from(AnnotationNote)
        .join(AnnotationItem, AnnotationNote.item_id == AnnotationItem.id)
        .where(AnnotationItem.round_id == rnd.id, AnnotationNote.annotator_id == annotator_id)
    ))


def set_adjudicator(session: Session, rnd: AnnotationRound, annotator_id: int | None) -> AnnotationRound:
    """Designate who decides the disagreements; never someone who scored this Rodada."""
    if annotator_id is not None:
        annotator = get_annotator(session, annotator_id)
        if _scored(session, rnd, annotator_id):
            raise AnnotationError(f"{annotator.name} deu notas nesta Rodada e não pode adjudicá-la.", status=409)
    rnd.adjudicator_id = annotator_id
    session.commit()
    return rnd


def _check_adjudicator(session: Session, rnd: AnnotationRound, annotator_id: int) -> None:
    if rnd.adjudicator_id != annotator_id:
        raise AnnotationError("Só o adjudicador designado pode ver e decidir as discordâncias.", status=403)
    if rnd.status != "closed":
        raise AnnotationError("Feche a Rodada antes da Adjudicação, para as discordâncias não mudarem.",
                              status=409)
    # Checked again here: designated while the Rodada was open, they may have scored it since.
    if _scored(session, rnd, annotator_id):
        raise AnnotationError("O adjudicador deu notas nesta Rodada e não pode decidir as discordâncias.",
                              status=409)


def adjudication_view(session: Session, rnd: AnnotationRound, annotator: Annotator) -> dict:
    """The disputed Items, with every Avaliador's note, for the adjudicator only."""
    _check_adjudicator(session, rnd, annotator.id)
    by_item, _ = _notes_by_item(session, rnd)
    decisions = _decisions(session, rnd)
    items = []
    for item in rnd.items:
        notes = by_item.get(item.id, {})
        disputed = _disputed(notes)
        if not disputed:
            continue
        decision = decisions.get(item.id)
        items.append({
            "id": item.id, "position": item.position, "question": item.question,
            "reference_answer": item.reference_answer, "evidence": list(item.evidence),
            "retrieved_context": list(item.retrieved_context), "generated_answer": item.generated_answer,
            "grounding_applicable": bool(item.retrieved_context),
            "notes": {name: note_out(n) for name, n in sorted(notes.items())},
            "disputed": disputed,
            "adjudication": ({"correctness": decision.correctness, "grounding": decision.grounding}
                             if decision else None),
        })
    return {"round": round_summary(rnd), "items": items,
            "decided": sum(i["adjudication"] is not None for i in items), "total": len(items)}


def adjudicate(session: Session, item_id: int, annotator_id: int, correctness: int | None,
               grounding: int | None) -> AnnotationAdjudication:
    """Record the adjudicator's scores for every disputed dimension of an Item."""
    item = session.get(AnnotationItem, item_id)
    if item is None:
        raise AnnotationError(f"Item {item_id} não existe.", status=404)
    _check_adjudicator(session, item.round, annotator_id)
    by_item, _ = _notes_by_item(session, item.round)
    disputed = _disputed(by_item.get(item_id, {}))
    if not disputed:
        raise AnnotationError("Os Avaliadores concordam neste Item: não há o que adjudicar.", status=409)
    given = {"correctness": correctness, "grounding": grounding}
    missing = [dim for dim in disputed if given[dim] is None]
    if missing:
        raise AnnotationError("Falta decidir: " + ", ".join(missing) + ".")
    decision = session.scalar(select(AnnotationAdjudication).where(AnnotationAdjudication.item_id == item_id))
    if decision is None:
        decision = AnnotationAdjudication(item_id=item_id, annotator_id=annotator_id)
        session.add(decision)
    decision.annotator_id = annotator_id  # whoever decided last
    decision.correctness = correctness if "correctness" in disputed else None
    decision.grounding = grounding if "grounding" in disputed else None
    session.commit()
    return decision


def final_notes(session: Session, rnd: AnnotationRound) -> dict:
    """The Nota final of each Item: the common score where the Avaliadores agree, the
    adjudicator's where they disagree, and nothing (pendente) while undecided."""
    by_item, _ = _notes_by_item(session, rnd)
    decisions = _decisions(session, rnd)
    items, pending = [], 0
    for item in rnd.items:
        notes = by_item.get(item.id, {})
        disputed = _disputed(notes)
        decision = decisions.get(item.id)
        final = {}
        for dim in DIMENSIONS:
            values = {_value(n, dim) for n in notes.values()} - {None}
            if dim in disputed:
                final[dim] = getattr(decision, dim) if decision else None
            else:
                final[dim] = next(iter(values)) if values else None
        # How many Avaliadores gave a usable score, in the dimension with most of them.
        scorers = max(sum(_value(n, dim) is not None for n in notes.values()) for dim in DIMENSIONS)
        if disputed and decision is None:
            status = "pendente"
            pending += 1
        elif disputed:
            status = "adjudicada"
        elif scorers >= 2:
            status = "concordância"
        else:
            status = "uma nota" if scorers == 1 else "sem notas"
        items.append({"id": item.id, "position": item.position, "final": final, "status": status,
                      "auto_scores": dict(item.auto_scores), "question_type": item.question_type,
                      "combination": dict(item.combination)})
    return {"round": round_summary(rnd), "items": items, "pending": pending}


def _decisions(session: Session, rnd: AnnotationRound) -> dict[int, AnnotationAdjudication]:
    return {a.item_id: a for a in session.scalars(
        select(AnnotationAdjudication)
        .join(AnnotationItem, AnnotationAdjudication.item_id == AnnotationItem.id)
        .where(AnnotationItem.round_id == rnd.id)
    )}


CORRECTNESS_METRICS = ("answer_correctness", "token_f1", "chrf", "rouge_l")
GROUNDING_METRICS = ("faithfulness",)


def _correlation(pairs: list[tuple[float, float]], metric: str, resamples: int) -> dict:
    rho = spearman([p[0] for p in pairs], [p[1] for p in pairs])
    ci = None
    if rho is not None:
        ci = bootstrap_ci(pairs, lambda ps: spearman([p[0] for p in ps], [p[1] for p in ps]), resamples)
    low, high = ci if ci else (None, None)
    return {"metric": metric, "n": len(pairs), "rho": rho, "low": low, "high": high}


def _group_means(rows: list[dict], key, resamples: int) -> list[dict]:
    """Mean human Correção and mean answer_correctness per group, over the same Items (those
    with both), so the two columns are comparable."""
    groups: dict = {}
    for row in rows:
        if row["automatic"] is not None:
            groups.setdefault(key(row), []).append(row)
    out = []
    for k, members in sorted(groups.items(), key=lambda kv: str(kv[0])):
        h = mean_ci([m["human"] for m in members], resamples)
        a = mean_ci([m["automatic"] for m in members], resamples)
        out.append({"key": k, "n": len(members),
                    "human": {"mean": h.mean, "low": h.low, "high": h.high},
                    "automatic": {"mean": a.mean, "low": a.low, "high": a.high}})
    return out


def round_validation(session: Session, rnd: AnnotationRound, resamples: int = RESAMPLES) -> dict:
    """The human Nota final against the automatic metrics stored with each Item: Spearman per
    metric (Correção against the answer metrics, Fundamentação against faithfulness) and the
    mean human Correção per Combinação (Técnica RAG × LLM) and per Tipo de pergunta, next to the
    mean answer_correctness. A dimension still pending adjudication is left out of that dimension
    only (the Item still counts in the other one); a pilot Rodada is refused."""
    if rnd.pilot:
        raise AnnotationError("Rodada piloto fica fora da análise: ela só calibra a Rubrica.", status=409)
    final = final_notes(session, rnd)
    by_id = {item.id: item for item in rnd.items}
    correlations = {"correctness": [], "grounding": []}
    for dim, metrics in (("correctness", CORRECTNESS_METRICS), ("grounding", GROUNDING_METRICS)):
        for metric in metrics:
            pairs = [(entry["final"][dim], by_id[entry["id"]].auto_scores[metric]) for entry in final["items"]
                     if entry["final"][dim] is not None and by_id[entry["id"]].auto_scores.get(metric) is not None]
            correlations[dim].append(_correlation(pairs, metric, resamples))
    rows = [{"human": e["final"]["correctness"], "automatic": by_id[e["id"]].auto_scores.get("answer_correctness"),
             "rag": by_id[e["id"]].combination.get("rag"), "llm": by_id[e["id"]].combination.get("llm"),
             "question_type": by_id[e["id"]].question_type}
            for e in final["items"] if e["final"]["correctness"] is not None]
    by_combination = [{"rag": g["key"][0], "llm": g["key"][1], **{k: v for k, v in g.items() if k != "key"}}
                      for g in _group_means(rows, lambda r: (r["rag"], r["llm"]), resamples)]
    by_type = [{"question_type": g["key"], **{k: v for k, v in g.items() if k != "key"}}
               for g in _group_means(rows, lambda r: r["question_type"] or "", resamples)]
    return {"round": round_summary(rnd), "pending": final["pending"], "n": len(rows),
            "correlations": correlations, "by_combination": by_combination, "by_question_type": by_type}
