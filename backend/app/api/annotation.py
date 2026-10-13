"""Endpoints of the Anotação humana: Avaliadores, Rodadas de anotação and notes."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.annotation.export import to_csv, to_latex
from app.annotation.rubric import RUBRIC
from app.annotation.service import (
    AnnotationError,
    adjudicate,
    adjudication_view,
    close_round,
    create_retest,
    create_round,
    final_notes,
    get_annotator,
    get_round,
    join_round,
    list_rounds as list_round_summaries,
    note_out,
    preview_round,
    queue,
    remove_participant,
    retest_agreement,
    round_agreement,
    round_progress,
    round_summary,
    round_validation,
    save_note,
    set_adjudicator,
)
from app.api.deps import get_session_factory
from app.core.db.models import Annotator

router = APIRouter()


def _clean_name(value: str) -> str:
    value = " ".join(value.split())
    if not value:
        raise ValueError("informe o nome")
    return value


class AnnotatorIn(BaseModel):
    name: str = Field(max_length=120)

    _not_blank = field_validator("name")(_clean_name)


class AnnotatorPatch(BaseModel):
    active: bool


class RoundIn(BaseModel):
    name: str = Field(max_length=120)
    # The Combinações to sample from ("experiment:run"), or every run of one Experimento.
    items: list[str] | None = None
    experiment_id: int | None = None
    sample_size: int = Field(gt=0)
    seed: int | None = Field(None, ge=0, le=2**31 - 1)  # the column is a 32-bit integer
    description: str = ""
    strata: list[Literal["question_type", "rag", "llm"]] = []
    allocation: Literal["proportional", "equal"] = "proportional"
    pilot: bool = False

    _not_blank = field_validator("name")(_clean_name)

    @model_validator(mode="after")
    def _has_source(self) -> "RoundIn":
        if not self.items and self.experiment_id is None:
            raise ValueError("informe as Combinações (items) ou o experiment_id")
        return self


class RoundPatch(BaseModel):
    adjudicator_id: int | None


class AdjudicationIn(BaseModel):
    annotator_id: int
    correctness: int | None = Field(None, ge=0, le=2)
    grounding: int | None = Field(None, ge=0, le=2)


class ParticipantIn(BaseModel):
    annotator_id: int


class NoteIn(BaseModel):
    correctness: int | None = Field(None, ge=0, le=2)
    # None when the Fundamentação does not apply (no retrieved context) or cannot be judged.
    grounding: int | None = Field(None, ge=0, le=2)
    cannot_evaluate: bool = False
    reason: str | None = Field(None, max_length=500)
    comment: str | None = Field(None, max_length=2000)


def _annotator_out(a: Annotator) -> dict:
    return {"id": a.id, "name": a.name, "active": a.active}


def _session(factory: sessionmaker[Session] = Depends(get_session_factory)):
    session = factory()
    try:
        yield session
    finally:
        session.close()


def _or_http(call):
    """Run `call`, turning an AnnotationError into the HTTP error it names."""
    try:
        return call()
    except AnnotationError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc


@router.get("/annotators")
def list_annotators(active: bool | None = Query(None), session: Session = Depends(_session)) -> list[dict]:
    """Avaliadores by name; `active` filters active or inactive ones."""
    query = select(Annotator).order_by(Annotator.name)
    if active is not None:
        query = query.where(Annotator.active == active)
    return [_annotator_out(a) for a in session.scalars(query)]


@router.post("/annotators", status_code=201)
def create_annotator(body: AnnotatorIn, session: Session = Depends(_session)) -> dict:
    """Register a new Avaliador; a name already taken (ignoring case) is a 409."""
    taken = session.scalar(select(Annotator).where(func.lower(Annotator.name) == body.name.lower()))
    if taken is not None:
        raise HTTPException(status_code=409, detail=_taken(taken))
    annotator = Annotator(name=body.name)
    session.add(annotator)
    try:
        session.commit()
    except IntegrityError as exc:  # the same name registered at the same moment
        session.rollback()
        raise HTTPException(status_code=409, detail=f"Já existe um avaliador chamado {body.name}.") from exc
    return _annotator_out(annotator)


def _taken(annotator: Annotator) -> str:
    if annotator.active:
        return f"Já existe um avaliador chamado {annotator.name}. Escolha o nome na lista."
    return (f"Já existe um avaliador chamado {annotator.name}, desativado. "
            "Peça ao pesquisador para reativá-lo na página de Rodadas.")


@router.patch("/annotators/{annotator_id}")
def update_annotator(annotator_id: int, body: AnnotatorPatch, session: Session = Depends(_session)) -> dict:
    """Activate or deactivate an Avaliador; their notes are kept either way."""
    annotator = _or_http(lambda: get_annotator(session, annotator_id))
    annotator.active = body.active
    session.commit()
    return _annotator_out(annotator)


@router.get("/annotation/rubric")
def get_rubric() -> dict:
    """The Rubrica the Avaliadores score with."""
    return RUBRIC


@router.get("/annotation/rounds")
def list_rounds(session: Session = Depends(_session)) -> list[dict]:
    """Rodadas de anotação, newest first."""
    return list_round_summaries(session)


@router.post("/annotation/rounds", status_code=201)
def post_round(body: RoundIn, session: Session = Depends(_session)) -> dict:
    """Sample answers of an Experimento into a new Rodada (same seed, same sample)."""
    rnd = _or_http(lambda: create_round(
        session, body.name, body.sample_size, items=body.items, experiment_id=body.experiment_id,
        seed=body.seed, description=body.description, strata=list(body.strata),
        allocation=body.allocation, pilot=body.pilot,
    ))
    return round_summary(rnd)


@router.post("/annotation/rounds/preview")
def post_round_preview(body: RoundIn, session: Session = Depends(_session)) -> dict:
    """What a Rodada with this design would sample, stratum by stratum, without creating it."""
    return _or_http(lambda: preview_round(session, body.items, body.experiment_id, body.sample_size,
                                          list(body.strata), body.allocation))


@router.get("/annotation/rounds/{round_id}")
def round_detail(round_id: int, session: Session = Depends(_session)) -> dict:
    """A Rodada with each Avaliador's progress."""
    rnd = _or_http(lambda: get_round(session, round_id))
    return {**round_summary(rnd), "progress": round_progress(session, rnd)}


@router.post("/annotation/rounds/{round_id}/participants")
def post_participant(round_id: int, body: ParticipantIn, session: Session = Depends(_session)) -> dict:
    """An Avaliador joins an open Rodada; joining again changes nothing."""
    _or_http(lambda: join_round(session, get_round(session, round_id),
                                get_annotator(session, body.annotator_id)))
    return {"round_id": round_id, "annotator_id": body.annotator_id}


@router.delete("/annotation/rounds/{round_id}/participants/{annotator_id}")
def delete_participant(round_id: int, annotator_id: int, session: Session = Depends(_session)) -> dict:
    """Remove an Avaliador (registered by mistake, say) from a Rodada, with their notes in it."""
    deleted = _or_http(lambda: remove_participant(session, get_round(session, round_id), annotator_id))
    return {"round_id": round_id, "annotator_id": annotator_id, "notes_deleted": deleted}


@router.patch("/annotation/rounds/{round_id}")
def patch_round(round_id: int, body: RoundPatch, session: Session = Depends(_session)) -> dict:
    """Designate (or clear) the Rodada's adjudicator."""
    rnd = _or_http(lambda: set_adjudicator(session, get_round(session, round_id), body.adjudicator_id))
    return round_summary(rnd)


@router.get("/annotation/rounds/{round_id}/adjudication")
def get_adjudication(round_id: int, annotator_id: int = Query(...), session: Session = Depends(_session)) -> dict:
    """The disputed Items of a closed Rodada, for its adjudicator only."""
    return _or_http(lambda: adjudication_view(session, get_round(session, round_id),
                                              get_annotator(session, annotator_id)))


@router.put("/annotation/items/{item_id}/adjudication")
def put_adjudication(item_id: int, body: AdjudicationIn, session: Session = Depends(_session)) -> dict:
    """The adjudicator's decision on every disputed dimension of an Item."""
    decision = _or_http(lambda: adjudicate(session, item_id, body.annotator_id, body.correctness, body.grounding))
    return {"item_id": decision.item_id, "correctness": decision.correctness, "grounding": decision.grounding}


@router.get("/annotation/rounds/{round_id}/final")
def get_final(round_id: int, session: Session = Depends(_session)) -> dict:
    """The Nota final of each Item and how many are still pending."""
    return _or_http(lambda: final_notes(session, get_round(session, round_id)))


@router.get("/annotation/rounds/{round_id}/validation")
def get_validation(round_id: int, resamples: int = Query(10_000, ge=100, le=10_000),
                   session: Session = Depends(_session)) -> dict:
    """The human Nota final against the automatic metrics (Spearman, means per Combinação and type)."""
    return _or_http(lambda: round_validation(session, get_round(session, round_id), resamples))


@router.post("/annotation/rounds/{round_id}/retest", status_code=201)
def post_retest(round_id: int, body: ParticipantIn, session: Session = Depends(_session)) -> dict:
    """A retest Rodada: the same Items for the same Avaliador, in a new order."""
    retest = _or_http(lambda: create_retest(session, get_round(session, round_id),
                                            get_annotator(session, body.annotator_id)))
    return round_summary(retest)


@router.get("/annotation/rounds/{round_id}/retests")
def get_retests(round_id: int, resamples: int = Query(10_000, ge=100, le=10_000),
                session: Session = Depends(_session)) -> list[dict]:
    """Intra-rater alpha between each Avaliador's two passes (this Rodada and its retests)."""
    return _or_http(lambda: retest_agreement(session, get_round(session, round_id), resamples))


def _download(content: str, media_type: str, filename: str) -> Response:
    return Response(content=content, media_type=media_type,
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/annotation/rounds/{round_id}/export.csv")
def export_csv(round_id: int, excel: bool = Query(False), session: Session = Depends(_session)) -> Response:
    """Every note of the Rodada (long format) with the Nota final and the automatic metrics;
    `excel=true` gives the ";"-separated, formula-safe version for spreadsheets in PT-BR."""
    rnd = _or_http(lambda: get_round(session, round_id))
    content = "\ufeff" + to_csv(session, rnd, final_notes(session, rnd), excel)  # BOM: spreadsheets read UTF-8
    return _download(content, "text/csv; charset=utf-8", f"anotacao-rodada-{round_id}.csv")


def _variant(lang: str, decimal: str) -> str:
    """File-name suffix telling the LaTeX variants apart (English, Portuguese with commas)."""
    if lang == "en":
        return "-en"
    return "-virgula" if decimal == "comma" else ""


@router.get("/annotation/rounds/{round_id}/export.tex")
def export_latex(round_id: int, resamples: int = Query(10_000, ge=100, le=10_000),
                 decimal: Literal["point", "comma"] = Query("point"),
                 lang: Literal["pt", "en"] = Query("pt"),
                 session: Session = Depends(_session)) -> Response:
    """Concordância and Spearman tables in LaTeX (booktabs), captions in Portuguese or English
    (`lang=en`, for the English paper); refused for pilot and retest Rodadas."""
    rnd = _or_http(lambda: get_round(session, round_id))
    validation = _or_http(lambda: round_validation(session, rnd, resamples))
    agreement = round_agreement(session, rnd, resamples)
    return _download(to_latex(agreement, validation, decimal, resamples, lang), "application/x-tex; charset=utf-8",
                     f"anotacao-rodada-{round_id}{_variant(lang, decimal)}.tex")


@router.post("/annotation/rounds/{round_id}/close")
def post_close(round_id: int, session: Session = Depends(_session)) -> dict:
    """Close the Rodada: no more notes, ready for the analysis."""
    return round_summary(_or_http(lambda: close_round(session, get_round(session, round_id))))


@router.get("/annotation/rounds/{round_id}/agreement")
def get_agreement(round_id: int, resamples: int = Query(10_000, ge=100, le=10_000),
                  session: Session = Depends(_session)) -> dict:
    """Concordância between the Avaliadores of a Rodada, with 95% bootstrap CIs."""
    return _or_http(lambda: round_agreement(session, get_round(session, round_id), resamples))


@router.get("/annotation/rounds/{round_id}/queue")
def round_queue(round_id: int, annotator_id: int = Query(...),
                session: Session = Depends(_session)) -> dict:
    """The Rodada's Items for one Avaliador, blind, with only that Avaliador's notes."""
    return _or_http(lambda: queue(session, get_round(session, round_id),
                                  get_annotator(session, annotator_id)))


@router.put("/annotation/items/{item_id}/notes/{annotator_id}")
def put_note(item_id: int, annotator_id: int, body: NoteIn, session: Session = Depends(_session)) -> dict:
    """Save (or replace) one Avaliador's note on an Item."""
    note = _or_http(lambda: save_note(session, item_id, annotator_id, body.correctness, body.grounding,
                                      body.cannot_evaluate, body.reason, body.comment))
    return {"item_id": note.item_id, "annotator_id": note.annotator_id, **note_out(note)}
