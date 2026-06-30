"""Pydantic schemas for experiments."""
from pydantic import BaseModel


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
    llm: str = "gemini"
    eval_embedding: str = "gemini"
