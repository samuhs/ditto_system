"""Pydantic schemas for experiments."""
import itertools

from pydantic import BaseModel, Field


class QuestionItem(BaseModel):
    """A question to ask, with an optional reference answer."""

    text: str
    reference: str | None = None


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
    llms: list[str] = ["gemini"]
    eval_embedding: str = "gemini"
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
