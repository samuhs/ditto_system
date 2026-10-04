"""Building Grafos de conhecimento as background jobs: one LLM extrator over Índices of a Base.

The ingestion starts one ("gerar Grafo de conhecimento"), and so can a Base that
already exists: POST /graph-builds is the single entry point. A job builds each
Índice's Grafo in turn with build_graph, skipping a Grafo that is already current,
and reports chunks extracted / total of the Índice it is on.

Jobs live in this process (the API runs as one uvicorn process, as the
experiments' pause requests do). What makes a pause cheap lives in the database:
each chunk's extraction is cached as soon as it is read, so resuming, or simply
starting the same build again, asks the LLM extrator only for the chunks it has
not read yet.
"""
import itertools
import logging
import threading
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.graph.build import GraphBuildPaused, build_graph, current_graph
from app.core.graph.cache import ExtractionCache
from app.core.llm import ollama
from app.core.llm.factory import is_local_llm, resolve_llm
from app.core.memory.device import resolve_embedding_device
from app.core.memory.manager import ModelManager, work_slot
from app.core.memory.profile import active_profile
from app.core.prompts import load_prompt
from app.core.vectorstore.qdrant import QdrantStore

logger = logging.getLogger(__name__)

JobStatus = Literal["pending", "running", "paused", "done", "failed"]
# A job that will still read its Base.
ACTIVE: tuple[JobStatus, ...] = ("pending", "running")


class IndexBuild(BaseModel):
    """One Índice of a job: its Grafo's state and the chunks extracted so far."""

    chunking: str
    embedding: str
    # pending: not started (or paused before it finished); building: extracting now.
    status: Literal["pending", "building", "done", "failed"] = "pending"
    extracted: int = 0
    total: int = 0
    # The finished Grafo's stats (entities, relations, chunks, failed lines).
    stats: dict | None = None
    error: str | None = None


class GraphBuildJob(BaseModel):
    """A build of the Grafos de conhecimento of some Índices of a Base by one LLM extrator."""

    id: int
    base: str
    extractor: str
    indexes: list[IndexBuild]
    status: JobStatus = "pending"
    pause_requested: bool = False
    created_at: str
    finished_at: str | None = None


@dataclass
class GraphBuildDeps:
    """What a job runs with (overridable in tests)."""

    store: QdrantStore
    session_factory: Callable[[], Session]
    models: ModelManager
    llm_factory: Callable = resolve_llm
    # Chunks the LLM extrator reads at once; None: the memory profile's limit.
    max_concurrency: int | None = None

    def extraction_concurrency(self) -> int:
        return self.max_concurrency or active_profile().max_extraction_concurrency


def _embedder_scope(models: ModelManager, embedding: str, extractor: str, device: str):
    """Lease the Índice's embedder only to write the Grafo, after the extraction.

    Where the profile holds one local model, a local LLM extrator is unloaded
    first, so the two never share the memory (it reloads on its next call).
    """

    @contextmanager
    def lease():
        if models.max_local < 2 and is_local_llm(extractor) and models.is_local(embedding):
            ollama.unload_local_llm(extractor)
        with models.acquire(embedding, device) as embedder:
            yield embedder
        models.evict_idle()

    return lease


def _now() -> str:
    return datetime.now(UTC).isoformat()


class GraphBuilds:
    """The jobs of this process: create, run, pause, resume and read them (thread-safe)."""

    def __init__(self) -> None:
        self._jobs: dict[int, GraphBuildJob] = {}
        self._prompts: dict[int, str] = {}
        self._ids = itertools.count(1)
        self._lock = threading.Lock()

    def create(
        self, base: str, extractor: str, indexes: list[tuple[str, str]], prompt: str | None = None
    ) -> GraphBuildJob:
        """Queue a job; `prompt` (default: the current extraction prompt) is fixed now."""
        with self._lock:
            job = GraphBuildJob(
                id=next(self._ids), base=base, extractor=extractor, created_at=_now(),
                indexes=[IndexBuild(chunking=c, embedding=e) for c, e in dict.fromkeys(indexes)],
            )
            self._jobs[job.id] = job
            self._prompts[job.id] = prompt or load_prompt("graph", "extract")
            return job.model_copy(deep=True)

    def get(self, job_id: int) -> GraphBuildJob | None:
        """A snapshot of the job, or None if this process has none with that id."""
        with self._lock:
            job = self._jobs.get(job_id)
            return job.model_copy(deep=True) if job else None

    def list_jobs(self, base: str | None = None) -> list[GraphBuildJob]:
        """Every job (of one Base, if given), newest first."""
        with self._lock:
            jobs = [j for j in self._jobs.values() if base is None or j.base == base]
            return [j.model_copy(deep=True) for j in sorted(jobs, key=lambda j: -j.id)]

    def active(self) -> list[GraphBuildJob]:
        """Jobs running or queued, oldest first: they will still read their Base."""
        return [j for j in reversed(self.list_jobs()) if j.status in ACTIVE]

    def request_pause(self, job_id: int) -> None:
        """Stop the job at its next chunk; chunks already extracted stay cached."""
        with self._lock:
            self._jobs[job_id].pause_requested = True

    def resume(self, job_id: int) -> GraphBuildJob:
        """Queue a paused (or failed) job again; run() then extracts only what is missing."""
        with self._lock:
            job = self._jobs[job_id]
            job.status, job.pause_requested, job.finished_at = "pending", False, None
            for item in job.indexes:
                if item.status != "done":
                    item.status, item.error = "pending", None
            return job.model_copy(deep=True)

    def run(self, job_id: int, deps: GraphBuildDeps) -> None:
        """Build the job's Grafos, one Índice at a time; never raises (errors are recorded).

        Waits for the work slot: one experiment or Grafo build at a time.
        """
        with work_slot:
            self._run(job_id, deps)

    def _update(self, job: GraphBuildJob, **changes) -> None:
        with self._lock:
            for key, value in changes.items():
                setattr(job, key, value)

    def _run(self, job_id: int, deps: GraphBuildDeps) -> None:
        job, prompt = self._jobs[job_id], self._prompts[job_id]
        if job.pause_requested:
            self._update(job, status="paused", finished_at=_now())
            return
        self._update(job, status="running")
        cache = ExtractionCache(deps.session_factory)
        device = resolve_embedding_device(active_profile(), [job.extractor])
        llm = None
        try:
            for item in job.indexes:
                if item.status == "done":
                    continue
                graph = current_graph(
                    deps.store, job.base, item.chunking, item.embedding, job.extractor, prompt
                )
                if graph is None:
                    llm = llm or deps.llm_factory(job.extractor)
                    self._update(item, status="building", extracted=0, total=0)
                    try:
                        graph = build_graph(
                            deps.store, job.base, item.chunking, item.embedding, job.extractor,
                            llm,
                            embedder_scope=_embedder_scope(
                                deps.models, item.embedding, job.extractor, device
                            ),
                            prompt=prompt, max_concurrency=deps.extraction_concurrency(), cache=cache,
                            should_stop=lambda: job.pause_requested,
                            on_progress=lambda done, total, item=item: self._update(
                                item, extracted=done, total=total
                            ),
                        )
                    except GraphBuildPaused:
                        self._update(item, status="pending")
                        self._update(job, status="paused", finished_at=_now())
                        return
                    except Exception as exc:  # noqa: BLE001  the other Índices go on
                        logger.error("Grafo build failed for %s × %s: %s",
                                     item.chunking, item.embedding, exc)
                        self._update(item, status="failed", error=str(exc)[:500])
                        continue
                total = graph.stats.get("chunks", 0)
                self._update(item, status="done", stats=graph.stats, extracted=total, total=total)
            failed = any(i.status == "failed" for i in job.indexes)
            self._update(job, status="failed" if failed else "done", finished_at=_now())
        except Exception as exc:  # noqa: BLE001  a background job records failure, never raises
            logger.exception("Grafo build job %d failed", job_id)
            for item in job.indexes:
                if item.status in ("pending", "building"):
                    self._update(item, status="failed", error=str(exc)[:500])
            self._update(job, status="failed", finished_at=_now())
        finally:
            # The memory goes back to the experiments: no embedder, no LLM extrator.
            deps.models.evict_idle()
            if llm is not None and is_local_llm(job.extractor):
                ollama.unload_local_llm(job.extractor)


# The process-wide jobs (the API's single uvicorn process).
graph_builds = GraphBuilds()
