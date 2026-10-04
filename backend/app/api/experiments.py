"""Endpoints to create and inspect experiments."""
import csv
import io
import re
import unicodedata
from datetime import timezone
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ValidationError
from sqlalchemy.exc import IntegrityError

from app.core.config.runtime import get_eval_embedding
from app.core.db.base import SessionLocal
from app.core.db.models import Experiment
from app.core.evaluation.gold_metrics import ALL_HOPS_METRIC, hops_found
from app.core.graph.build import current_extractors
from app.core.memory.manager import get_model_manager
from app.core.memory.profile import active_profile
from app.core.prompts import PROMPT_SPECS, load_prompt, load_technique
from app.core.rag.base import rag_registry
from app.core.vectorstore.qdrant import QdrantStore, collection_name
from app.experiments.csv_loader import parse_questions_csv
from app.experiments.difficulty import question_difficulty
from app.experiments.fingerprint import experiment_fingerprint, fingerprint_changes
from app.experiments.naming import generate_experiment_name
from app.experiments.orchestrator import (
    ExperimentDeps,
    _pause_requested,
    request_pause,
    resume_experiment,
    run_experiment,
)
from app.experiments.preflight import memory_warnings
from app.experiments.schemas import ExperimentConfig, combination_count, index_pairs

router = APIRouter()


def _iso_utc(dt):
    """Serialize a naive-UTC datetime as a tz-aware ISO string (or None)."""
    return dt.replace(tzinfo=timezone.utc).isoformat() if dt else None


def _evidence_hops(result) -> list[int]:
    """Hop of each reference passage; results stored before hops existed are single-hop."""
    if result.evidence_hops:
        return result.evidence_hops
    return [1] * len(result.reference_contexts or [])


def _hops_found(result) -> list[dict]:
    """Whether each hop's evidence was retrieved; empty when nothing was retrieved."""
    contexts = [c.get("text", "") for c in result.retrieved_context or []]
    if not contexts or not result.reference_contexts:
        return []
    found = hops_found(result.reference_contexts, _evidence_hops(result), contexts)
    return [{"hop": hop, "found": hit} for hop, hit in found.items()]


def _lenient(name: str) -> str:
    """A name casefolded, without accents or punctuation, with single spaces."""
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^0-9a-z]+", " ", plain.casefold()).split())


def _bridges_found(result) -> list[dict]:
    """Whether the Grafo found each annotated Entidade-ponte; empty without a Grafo.

    Lenient on spelling only: the names match ignoring case, accents and
    punctuation ("parque ecologico" finds "Parque Ecológico", "parque" does not).
    """
    if result.graph_explanation is None:
        return []
    names = {_lenient(e["name"]) for e in result.graph_explanation.get("entities", [])}
    return [
        {"entity": bridge, "found": _lenient(bridge) in names}
        for bridge in result.bridge_entities or []
        if _lenient(bridge)
    ]


def _result_rows(experiment: Experiment) -> list[dict]:
    """Flatten an experiment's runs into one row per (combination, question)."""
    profiles = {p.question: p.signals for p in experiment.question_profiles}
    # Matching evidence to chunks is fuzzy text alignment: only paid for when
    # the experiment scores context_all_hops.
    match_hops = ALL_HOPS_METRIC in (experiment.config or {}).get("metrics", [])
    rows = []
    for run in experiment.runs:
        for result in run.results:
            rows.append(
                {
                    "chunking": run.chunking,
                    "embedding": run.embedding,
                    "rag": run.rag_technique,
                    "retriever": run.retriever,
                    "llm": run.llm or "gemini",
                    "question": result.question,
                    "reference": result.reference_answer,
                    "question_type": result.question_type or "simples",
                    "evidence_hops": _evidence_hops(result),
                    "bridge_entities": result.bridge_entities or [],
                    "hops_found": _hops_found(result) if match_hops else [],
                    "answer": result.generated_answer,
                    "scores": result.scores,
                    "latency_ms": result.latency_ms,
                    "tokens": result.tokens,
                    "question_signals": profiles.get(result.question, {}),
                    "retrieval_signals": result.retrieval_signals or {},
                    # GraphRAG runs: the Grafo de conhecimento's stats; None otherwise.
                    "graph_stats": run.graph_stats,
                    # GraphRAG results: entities found and facts used; None otherwise.
                    "graph_explanation": result.graph_explanation,
                    "bridges_found": _bridges_found(result),
                }
            )
    return rows


def _total_combinations(cfg: dict) -> int:
    """Runs the stored config expands to (a closed-book run counts once per LLM)."""
    try:
        return combination_count(ExperimentConfig(**cfg))
    except ValidationError:
        n_llms = len(cfg.get("llms", [])) or 1
        return (
            len(cfg.get("chunkings", [])) * len(cfg.get("embeddings", []))
            * len(cfg.get("rags", [])) * len(cfg.get("retrievers", [])) * n_llms
        )


def _safe_filename(name: str) -> str:
    """Reduce an experiment name to an ASCII-only, filesystem-safe stem."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9._-]+", "_", ascii_name).strip("_") or "experiment"


def _results_csv(rows: list[dict]) -> str:
    """Render result rows as CSV with one column per metric plus the row mean."""
    metric_keys = sorted({k for row in rows for k in row["scores"]})
    question_keys = sorted({k for row in rows for k in row["question_signals"]})
    retrieval_keys = sorted({k for row in rows for k in row["retrieval_signals"]})
    graph_keys = list(dict.fromkeys(k for row in rows for k in row["graph_stats"] or {}))
    explained = any(row["graph_explanation"] is not None for row in rows)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["chunking", "embedding", "rag", "retriever", "llm",
         "pergunta", "resposta_referencia", "resposta",
         "tipo", "evidencia_salto", "entidades_ponte",
         *metric_keys, "media", "latency_ms", "tokens",
         *(f"pergunta_{k}" for k in question_keys), *(f"busca_{k}" for k in retrieval_keys),
         *(f"grafo_{k}" for k in graph_keys),
         *(["grafo_entidades_encontradas", "grafo_fatos_usados", "grafo_pontes_encontradas"] if explained else [])]
    )
    for row in rows:
        scores = row["scores"]
        mean = sum(scores.values()) / len(scores) if scores else ""
        writer.writerow(
            [row["chunking"], row["embedding"], row["rag"], row["retriever"], row["llm"],
             row["question"], row["reference"] or "", row["answer"],
             row["question_type"], "|".join(map(str, row["evidence_hops"])),
             "|".join(row["bridge_entities"]),
             *(scores.get(k, "") for k in metric_keys), mean, row["latency_ms"], row["tokens"],
             *(row["question_signals"].get(k, "") for k in question_keys),
             *(row["retrieval_signals"].get(k, "") for k in retrieval_keys),
             *((row["graph_stats"] or {}).get(k, "") for k in graph_keys),
             *(_explanation_cells(row) if explained else [])]
        )
    return buffer.getvalue()


def _explanation_cells(row: dict) -> list[str]:
    """Entities found, facts used and Entidades-ponte found, '|'-joined; empty without a Grafo."""
    explanation = row["graph_explanation"]
    if explanation is None:
        return ["", "", ""]
    return [
        "|".join(e["name"] for e in explanation.get("entities", [])),
        "|".join(explanation.get("facts", [])),
        "|".join(b["entity"] for b in row["bridges_found"] if b["found"]),
    ]


def _snapshot_prompts(config: ExperimentConfig) -> dict[str, dict[str, str]]:
    """Capture the current prompts of every technique the experiment uses."""
    techniques = list(config.rags)
    if "multi_query" in config.retrievers:
        techniques.append("multi_query")
    snapshot = {t: load_technique(t) for t in techniques if t in PROMPT_SPECS}
    for t in config.rags:
        if t in rag_registry.names() and rag_registry.get(t).uses_graph:
            # GraphRAG answers with the naive prompt. It never extracts: the Grafo it
            # queries keeps its own extraction prompt in its metadata.
            snapshot[t] = {"answer": load_prompt("naive", "answer")}
    return snapshot


def get_experiment_deps() -> ExperimentDeps:
    """FastAPI dependency providing the production experiment dependencies."""
    return ExperimentDeps(store=QdrantStore(), session_factory=SessionLocal, models=get_model_manager())


def _check_indexes_exist(config: ExperimentConfig, store: QdrantStore) -> None:
    """Reject index pairs that were never ingested for the base (422)."""
    existing = set(store.list_collections())
    missing = [
        f"{chunking} × {embedding}"
        for chunking, embedding in index_pairs(config)
        if collection_name(config.base, chunking, embedding) not in existing
    ]
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"base '{config.base}' has no index for: {', '.join(missing)}",
        )


def _check_evidence_for(config: ExperimentConfig, items: list) -> None:
    """Reject techniques that answer from the reference evidence when no question has any (422).

    Otherwise the oracle would run silently without a single answer.
    """
    needs = [
        r for r in config.rags
        if r in rag_registry.names() and rag_registry.get(r).uses_evidence
    ]
    if needs and not any(item.evidence for item in items):
        raise HTTPException(
            status_code=422,
            detail=(
                f"{', '.join(needs)} needs reference evidence: add an evidencia_referencia "
                "column to the questions CSV or remove it from the RAG techniques"
            ),
        )


def _check_graphs(config: ExperimentConfig, store: QdrantStore) -> None:
    """GraphRAG only queries: every chosen Índice needs a current Grafo by one LLM extrator (422).

    Fills in config.graph_extractor when it is not given and exactly one LLM
    extrator has a current Grafo on every chosen Índice; clears it without GraphRAG.
    """
    if config.graph_extractor is not None:
        config.graph_extractor = config.graph_extractor.strip() or None
    graph_rags = [
        r for r in config.rags if r in rag_registry.names() and rag_registry.get(r).uses_graph
    ]
    if not graph_rags:
        config.graph_extractor = None
        return
    pairs = list(dict.fromkeys(index_pairs(config)))
    collections = store.list_collections()
    available = {
        pair: set(current_extractors(store, config.base, *pair, collections=collections))
        for pair in pairs
    }
    techniques = " e ".join(graph_rags)
    if config.graph_extractor is None:
        common = set.intersection(*available.values()) if available else set()
        if len(common) == 1:
            config.graph_extractor = common.pop()
            return
        if common:
            raise HTTPException(status_code=422, detail=(
                f"Os Índices escolhidos têm Grafos de conhecimento de mais de um LLM extrator "
                f"({', '.join(sorted(common))}): escolha qual {techniques} vai consultar."
            ))
        if all(available.values()):
            raise HTTPException(status_code=422, detail=(
                f"Os Índices escolhidos têm Grafos de conhecimento, mas de LLMs extratores "
                f"diferentes: {techniques} precisa de um LLM extrator com Grafo em todos eles. "
                f"Gere o Grafo que falta ou desmarque Índices."
            ))
    missing = [
        f"{chunking} × {embedding}"
        for (chunking, embedding), extractors in available.items()
        if config.graph_extractor not in extractors
    ]
    if missing:
        by = f" do LLM extrator {config.graph_extractor}" if config.graph_extractor else ""
        raise HTTPException(status_code=422, detail=(
            f"{techniques} só consulta Índices que já têm Grafo de conhecimento{by}, e estes "
            f"não têm (ou o Grafo está desatualizado): {', '.join(missing)}. Gere o Grafo na "
            f"ingestão ou desmarque esses Índices."
        ))


@router.post("/experiments")
async def create_experiment(
    background_tasks: BackgroundTasks,
    config: str = Form(...),
    questions: UploadFile = File(...),
    deps: ExperimentDeps = Depends(get_experiment_deps),
) -> dict:
    """Create an experiment and run it in the background."""
    try:
        parsed = ExperimentConfig.model_validate_json(config)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    if parsed.indexes is not None:
        _check_indexes_exist(parsed, deps.store)
    if not parsed.name:
        parsed.name = generate_experiment_name()
    if parsed.eval_embedding is None:
        parsed.eval_embedding = get_eval_embedding()
    raw = await questions.read()
    try:
        csv_text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail="questions file is not valid UTF-8") from exc
    try:
        items = parse_questions_csv(csv_text)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _check_evidence_for(parsed, items)
    _check_graphs(parsed, deps.store)

    session = deps.session_factory()
    try:
        config_dump = parsed.model_dump()
        config_dump["prompts"] = _snapshot_prompts(parsed)
        # Índice/Grafo fingerprint (#21): the Retomada later blocks if this diverges.
        config_dump["fingerprint"] = experiment_fingerprint(parsed, deps.store)
        # Recorded with the experiment so a later Retomada (#17) can read them back
        # from the database instead of depending on the background task's memory.
        questions_dump = [item.model_dump() for item in items]
        experiment = Experiment(
            name=parsed.name, status="pending", config=config_dump, questions=questions_dump,
        )
        session.add(experiment)
        try:
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            raise HTTPException(
                status_code=409, detail=f"experiment name already exists: {parsed.name}"
            ) from exc
        session.refresh(experiment)
        experiment_id = experiment.id
        name = experiment.name
    finally:
        session.close()

    background_tasks.add_task(run_experiment, experiment_id, parsed, items, deps)
    warnings = memory_warnings(parsed, active_profile())
    return {"id": experiment_id, "name": name, "status": "pending", "warnings": warnings}


@router.post("/experiments/{experiment_id}/pause")
def pause_experiment(
    experiment_id: int,
    deps: ExperimentDeps = Depends(get_experiment_deps),
) -> dict:
    """Request a running experiment to pause at its next checkpoint."""
    session = deps.session_factory()
    try:
        experiment = session.get(Experiment, experiment_id)
        if experiment is None:
            raise HTTPException(status_code=404, detail="experiment not found")
        if experiment.status not in ("running", "pending"):
            raise HTTPException(
                status_code=409,
                detail=f"experiment is not running (status: {experiment.status})",
            )
    finally:
        session.close()
    request_pause(experiment_id)
    return {"id": experiment_id, "status": "pausing"}


def _resumable_reason(experiment: Experiment, store: QdrantStore) -> str | None:
    """Why POST /resume would fail right now (409); None when it would succeed (200).

    An Experimento with a recorded fingerprint (#21) is also blocked when the Índice or
    Grafo de conhecimento it used has since changed (reingested, rebuilt, gone stale);
    one created before #21 has no stored fingerprint and is never blocked by this check.
    """
    if experiment.status not in ("paused", "failed"):
        return f"Experimento com status '{experiment.status}' não pode ser retomado."
    if not experiment.questions:
        return (
            "Experimento sem perguntas gravadas (criado antes desta função) não pode ser retomado."
        )
    stored_fingerprint = (experiment.config or {}).get("fingerprint")
    if stored_fingerprint:
        try:
            config = ExperimentConfig(**(experiment.config or {}))
        except ValidationError:
            return None  # config predates a field this needs to recompute: do not block on it
        changes = fingerprint_changes(stored_fingerprint, experiment_fingerprint(config, store))
        if changes:
            return (
                "Não é possível retomar: o Índice ou o Grafo de conhecimento usado mudou desde "
                "a última Pausa (" + "; ".join(changes) + ")."
            )
    return None


class ResumeRequest(BaseModel):
    """Optional body of POST /experiments/{id}/resume: lower the concorrência before it runs."""

    concurrency: int | None = None


@router.post("/experiments/{experiment_id}/resume")
def resume_experiment_route(
    experiment_id: int,
    background_tasks: BackgroundTasks,
    payload: ResumeRequest | None = None,
    deps: ExperimentDeps = Depends(get_experiment_deps),
) -> dict:
    """Retomada: resume a paused or failed experiment, queued through the usual work slot.

    An optional {"concurrency": int} body lowers the Experimento's concorrência before it
    runs again (1 <= concurrency <= the config's current value; 422 outside that range).
    Refreshes the stored Índice/Grafo fingerprint (#21) to the state this Retomada starts
    from, so the next Pausa/Retomada compares against it instead of the one from creation.
    """
    session = deps.session_factory()
    try:
        experiment = session.get(Experiment, experiment_id)
        if experiment is None:
            raise HTTPException(status_code=404, detail="experiment not found")
        reason = _resumable_reason(experiment, deps.store)
        if reason is not None:
            raise HTTPException(status_code=409, detail=reason)
        config = dict(experiment.config or {})
        current_concurrency = config.get("concurrency", 1)
        if payload is not None and payload.concurrency is not None:
            if not (1 <= payload.concurrency <= current_concurrency):
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"concurrency deve ser entre 1 e {current_concurrency} "
                        "(a concorrência atual do Experimento)"
                    ),
                )
            config["concurrency"] = payload.concurrency
        try:
            config["fingerprint"] = experiment_fingerprint(ExperimentConfig(**config), deps.store)
        except ValidationError:
            pass  # config predates a field this needs: resume still proceeds, unfingerprinted
        experiment.config = config
        experiment.status = "pending"
        session.commit()
    finally:
        session.close()
    background_tasks.add_task(resume_experiment, experiment_id, deps)
    return {"id": experiment_id, "status": "pending"}


@router.get("/experiments")
def list_experiments(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    deps: ExperimentDeps = Depends(get_experiment_deps),
) -> dict:
    """List experiments (paginated), most recent first."""
    session = deps.session_factory()
    try:
        query = session.query(Experiment).order_by(Experiment.id.desc())
        total = query.count()
        rows = query.offset((page - 1) * page_size).limit(page_size).all()
        items = [
            {
                "id": e.id,
                "name": e.name,
                "status": e.status,
                "created_at": _iso_utc(e.created_at),
            }
            for e in rows
        ]
        return {"items": items, "total": total, "page": page, "page_size": page_size}
    finally:
        session.close()


@router.get("/experiments/{experiment_id}")
def get_experiment(
    experiment_id: int,
    deps: ExperimentDeps = Depends(get_experiment_deps),
) -> dict:
    """Return an experiment with its per-question results."""
    session = deps.session_factory()
    try:
        experiment = session.get(Experiment, experiment_id)
        if experiment is None:
            raise HTTPException(status_code=404, detail="experiment not found")
        results = _result_rows(experiment)
        cfg = experiment.config or {}
        total_combos = _total_combinations(cfg)
        completed_combos = sum(1 for run in experiment.runs if run.status == "done")
        resumable_reason = _resumable_reason(experiment, deps.store)
        return {
            "id": experiment.id,
            "name": experiment.name,
            "status": experiment.status,
            "created_at": _iso_utc(experiment.created_at),
            "finished_at": _iso_utc(experiment.finished_at),
            "pause_requested": _pause_requested(experiment_id),
            # Registro de pausa: every Pausa this experiment has had, oldest first.
            "pauses": experiment.pauses or [],
            # Whether POST /resume would currently succeed, and why not when it would not.
            "resumable": resumable_reason is None,
            "resumable_reason": resumable_reason,
            # The config's current concorrência: the UI's Retomar concurrency field's max.
            "concurrency": cfg.get("concurrency"),
            "error": cfg.get("error") or None,
            "eval_embedding": cfg.get("eval_embedding"),
            # The LLM extrator whose Grafos graph/graph_mix queried; None without them.
            "graph_extractor": cfg.get("graph_extractor"),
            "progress": {
                "completed": completed_combos,
                "total": total_combos,
                # Staged runs: "generating", then "evaluating" (scoring the answers).
                "phase": cfg.get("phase"),
            },
            "prompts": cfg.get("prompts"),
            "results": results,
        }
    finally:
        session.close()


@router.get("/experiments/{experiment_id}/difficulty")
def get_experiment_difficulty(
    experiment_id: int,
    metric: str | None = Query(None),
    deps: ExperimentDeps = Depends(get_experiment_deps),
) -> dict:
    """Per-question difficulty signals, observed difficulty per LLM and an IRT fit on a metric."""
    session = deps.session_factory()
    try:
        experiment = session.get(Experiment, experiment_id)
        if experiment is None:
            raise HTTPException(status_code=404, detail="experiment not found")
        return question_difficulty(experiment, metric)
    finally:
        session.close()


@router.get("/experiments/{experiment_id}/export.csv")
def export_experiment_csv(
    experiment_id: int,
    deps: ExperimentDeps = Depends(get_experiment_deps),
) -> Response:
    """Download every per-question result of an experiment as a CSV file."""
    session = deps.session_factory()
    try:
        experiment = session.get(Experiment, experiment_id)
        if experiment is None:
            raise HTTPException(status_code=404, detail="experiment not found")
        content = "\ufeff" + _results_csv(_result_rows(experiment))
        filename = f"{_safe_filename(experiment.name)}.csv"
    finally:
        session.close()
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
