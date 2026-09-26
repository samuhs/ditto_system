"""Pydantic schemas for experiments."""
import itertools

from pydantic import BaseModel, Field


class QuestionItem(BaseModel):
    """A question to ask, with an optional reference answer and reference evidence."""

    text: str
    reference: str | None = None
    evidence: list[str] | None = None


class IndexPair(BaseModel):
    """One indexed chunking x embedding variant of a base (one Qdrant collection)."""

    chunking: str
    embedding: str


class ExperimentConfig(BaseModel):
    """Configuration for one experiment run."""

    name: str | None = None
    base: str
    chunkings: list[str]
    embeddings: list[str]
    rags: list[str]
    retrievers: list[str]
    metrics: list[str]
    # Explicit pairs to test; when set they replace the chunkings x embeddings product
    # (which may include pairs that were never indexed).
    indexes: list[IndexPair] | None = None
    # No default: every model is chosen explicitly (local ones need no API key).
    llms: list[str] = Field(min_length=1)
    # None: the API fills in the default saved under Ajustar > Avaliação.
    eval_embedding: str | None = None
    # Questions processed in parallel within each combination. >1 only pays off
    # when the LLM server serves concurrent requests (e.g. OLLAMA_NUM_PARALLEL);
    # per-question latency then includes time queued on the server.
    concurrency: int = Field(default=1, ge=1, le=32)
    # One model in memory at a time: embed the questions, generate, then score
    # (memory spec 3.4). False runs everything in one pass (escape hatch).
    staged: bool = True


def index_pairs(config: ExperimentConfig) -> list[tuple[str, str]]:
    """The (chunking, embedding) pairs an experiment runs over."""
    if config.indexes is not None:
        return [(i.chunking, i.embedding) for i in config.indexes]
    return list(itertools.product(config.chunkings, config.embeddings))


def _uses_retrieval(rag: str) -> bool:
    from app.core.rag.base import rag_registry

    return rag not in rag_registry.names() or rag_registry.get(rag).uses_retrieval


def combinations(config: ExperimentConfig):
    """Every run as (llm, (chunking, embedding), rag, retriever), in LLM-major order.

    A technique that never retrieves runs once per LLM, attached to the first
    index and retriever (which it ignores).
    """
    pairs = index_pairs(config)
    first = (pairs[0], config.retrievers[0]) if pairs and config.retrievers else None
    for llm, pair, rag, retriever in itertools.product(
        config.llms, pairs, config.rags, config.retrievers
    ):
        if _uses_retrieval(rag) or (pair, retriever) == first:
            yield llm, pair, rag, retriever


def combination_count(config: ExperimentConfig) -> int:
    """How many runs an experiment has."""
    return sum(1 for _ in combinations(config))
