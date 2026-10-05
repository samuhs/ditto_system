"""Pydantic schemas for experiments."""
import itertools

from pydantic import BaseModel, Field, field_validator

from app.core.vectorstore.qdrant import validate_base_name


QUESTION_TYPES = ("simples", "ponte", "comparacao", "agregacao")


class QuestionItem(BaseModel):
    """A question to ask, with an optional reference answer and reference evidence.

    evidence_hops gives the hop (1-based) each evidence passage supports, aligned
    with evidence; passages sharing a hop are alternatives for it.
    """

    text: str
    reference: str | None = None
    evidence: list[str] | None = None
    question_type: str = "simples"
    evidence_hops: list[int] | None = None
    bridge_entities: list[str] = Field(default_factory=list)


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
    # The LLM extrator whose Grafo de conhecimento graph/graph_mix query, one for the
    # whole experiment (an Índice may have Grafos from several). None: no GraphRAG
    # technique, or the API fills in the only extrator every chosen Índice has.
    graph_extractor: str | None = None

    @field_validator("base")
    @classmethod
    def _valid_base(cls, value: str) -> str:
        validate_base_name(value)
        return value


def index_pairs(config: ExperimentConfig) -> list[tuple[str, str]]:
    """The (chunking, embedding) pairs an experiment runs over."""
    if config.indexes is not None:
        return [(i.chunking, i.embedding) for i in config.indexes]
    return list(itertools.product(config.chunkings, config.embeddings))


def combinations(config: ExperimentConfig):
    """Every run as (llm, (chunking, embedding), rag, retriever), in LLM-major order.

    A technique that uses no Retriever runs once per Índice, attached to the first
    retriever (which it ignores); one that reads no Índice either (closed book)
    runs once per LLM, attached to the first index too.
    """
    from app.core.rag.base import technique_class

    pairs = index_pairs(config)
    first_pair = pairs[0] if pairs else None
    first_retriever = config.retrievers[0] if config.retrievers else None
    for llm, pair, rag, retriever in itertools.product(
        config.llms, pairs, config.rags, config.retrievers
    ):
        technique = technique_class(rag)  # unknown names run as retrieving
        uses_retrieval = technique is None or technique.uses_retrieval
        uses_index = technique is None or technique.uses_index
        if uses_retrieval or (
            retriever == first_retriever and (uses_index or pair == first_pair)
        ):
            yield llm, pair, rag, retriever


def combination_count(config: ExperimentConfig) -> int:
    """How many runs an experiment has."""
    return sum(1 for _ in combinations(config))
