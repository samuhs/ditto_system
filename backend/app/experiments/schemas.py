"""Pydantic schemas for experiments."""
from pydantic import BaseModel, Field


class QuestionItem(BaseModel):
    """A question to ask, with an optional reference answer."""

    text: str
    reference: str | None = None


class ExperimentConfig(BaseModel):
    """Configuration for one experiment run."""

    name: str | None = None
    base: str
    chunkings: list[str]
    embeddings: list[str]
    rags: list[str]
    retrievers: list[str]
    metrics: list[str]
    llms: list[str] = ["gemini"]
    eval_embedding: str = "gemini"
    # Questions processed in parallel within each combination. >1 only pays off
    # when the LLM server serves concurrent requests (e.g. OLLAMA_NUM_PARALLEL);
    # per-question latency then includes time queued on the server.
    concurrency: int = Field(default=1, ge=1, le=32)
