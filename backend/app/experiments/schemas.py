"""Pydantic schemas for experiments."""
import itertools

from pydantic import BaseModel, Field, model_validator


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


class Combo(BaseModel):
    """One explicit Índice x técnica x Retriever to run (for every LLM).

    A técnica that reads no Índice (closed_book, oracle) may leave the Índice out:
    it runs attached to the first Índice another combo reads.
    """

    chunking: str | None = None
    embedding: str | None = None
    rag: str
    retriever: str

    def uses_index(self) -> bool:
        from app.core.rag.base import technique_class

        technique = technique_class(self.rag)  # unknown names run as retrieving
        return technique is None or technique.uses_index

    def uses_retrieval(self) -> bool:
        from app.core.rag.base import technique_class

        technique = technique_class(self.rag)
        return technique is None or technique.uses_retrieval


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
    # Sampling for every LLM in the experiment (answers and the LLM-assisted steps:
    # HyDE, multi-query, rewrites). None leaves the provider's default, which differs
    # between servers; 0 makes answers reproducible.
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    # Cap on tokens per generation. None: no explicit cap.
    max_tokens: int | None = Field(default=None, ge=1, le=32768)
    # One model in memory at a time: embed the questions, generate, then score
    # (memory spec 3.4). False runs everything in one pass (escape hatch).
    staged: bool = True
    # The LLM extrator whose Grafo de conhecimento graph/graph_mix query, one for the
    # whole experiment (an Índice may have Grafos from several). None: no GraphRAG
    # technique, or the API fills in the only extrator every chosen Índice has.
    graph_extractor: str | None = None
    # Explicit combinations to run instead of the chunkings x embeddings x rags x
    # retrievers product (still crossed with every LLM). The lists and `indexes`
    # are derived from them, so the checks that read the lists keep working.
    combos: list[Combo] | None = None

    @model_validator(mode="after")
    def _derive_lists_from_combos(self) -> "ExperimentConfig":
        if not self.combos:
            return self
        reading = [c for c in self.combos if c.uses_index()] or self.combos
        pairs = list(dict.fromkeys(
            (c.chunking, c.embedding) for c in reading if c.chunking and c.embedding
        ))
        if not pairs:
            raise ValueError("combos need at least one Índice (chunking and embedding)")
        derived = {
            "chunkings": list(dict.fromkeys(ch for ch, _ in pairs)),
            "embeddings": list(dict.fromkeys(em for _, em in pairs)),
            "rags": list(dict.fromkeys(c.rag for c in self.combos)),
            "retrievers": list(dict.fromkeys(c.retriever for c in self.combos)),
        }
        # Empty lists, or the ones a stored config already derived, are fine;
        # anything else would be silently overwritten.
        conflicting = [k for k, v in derived.items() if getattr(self, k) not in ([], v)]
        if conflicting:
            raise ValueError(f"combos replace {', '.join(conflicting)}: send them empty")
        for key, value in derived.items():
            setattr(self, key, value)
        self.indexes = [IndexPair(chunking=ch, embedding=em) for ch, em in pairs]
        return self


def index_pairs(config: ExperimentConfig) -> list[tuple[str, str]]:
    """The (chunking, embedding) pairs an experiment runs over."""
    if config.indexes is not None:
        return [(i.chunking, i.embedding) for i in config.indexes]
    return list(itertools.product(config.chunkings, config.embeddings))


def combinations(config: ExperimentConfig):
    """Every run as (llm, (chunking, embedding), rag, retriever), in LLM-major order.

    With explicit `combos`, exactly those run, once per LLM, in the order given,
    except repeats that differ only in what the técnica ignores (the Retriever, or
    the Índice, which an index-free técnica takes from the first one read).

    A technique that uses no Retriever runs once per Índice, attached to the first
    retriever (which it ignores); one that reads no Índice either (closed book)
    runs once per LLM, attached to the first index too.
    """
    from app.core.rag.base import technique_class

    if config.combos:
        first_pair = index_pairs(config)[0]
        runs = {}
        for c in config.combos:
            pair = (c.chunking, c.embedding) if c.uses_index() else first_pair
            key = (c.rag, c.retriever if c.uses_retrieval() else None,
                   pair if c.uses_index() else None)
            runs.setdefault(key, (pair, c.rag, c.retriever))
        for llm in config.llms:
            for pair, rag, retriever in runs.values():
                yield llm, pair, rag, retriever
        return
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
