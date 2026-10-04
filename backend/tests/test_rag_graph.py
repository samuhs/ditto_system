"""Tests for GraphRAG: build an Índice's Grafo de conhecimento and answer from it."""
from qdrant_client import QdrantClient

from app.core.graph.build import ensure_graph
from app.core.graph.knowledge import index_chunks
from app.core.rag.base import build_rag, rag_registry
from app.core.vectorstore.qdrant import QdrantStore, collection_name, parse_collection_name
from app.ingestion.pipeline import ingest_documents
from app.ingestion.schemas import Document, IngestConfig

CACHOEIRA = "# Um\nA Cachoeira do Dédi fica no Sítio Boa Vista."
SITIO = "# Dois\nO Sítio Boa Vista vende queijo artesanal aos sábados."
IGREJA = "# Três\nA Igreja Matriz fica na praça central."

# What the extractor "reads" in each chunk, in the prompt's '<|>' format.
EXTRACTIONS = {
    CACHOEIRA: (
        "entidade<|>Cachoeira do Dédi<|>lugar<|>Cachoeira da zona rural.\n"
        "entidade<|>Sítio Boa Vista<|>lugar<|>Sítio onde fica a cachoeira.\n"
        "relacao<|>Cachoeira do Dédi<|>Sítio Boa Vista<|>localização<|>"
        "A Cachoeira do Dédi fica no Sítio Boa Vista.\n<|FIM|>"
    ),
    SITIO: (
        "entidade<|>sítio  boa VISTA<|>estabelecimento<|>Vende queijo artesanal.\n"
        "entidade<|>Queijo artesanal<|>produto<|>Queijo vendido aos sábados.\n"
        "relacao<|>Sítio Boa Vista<|>Queijo artesanal<|>venda<|>O sítio vende queijo.\n<|FIM|>"
    ),
    IGREJA: (
        "entidade<|>Igreja Matriz<|>lugar<|>Igreja na praça central.\n"
        "isto não é uma linha do formato\n<|FIM|>"
    ),
}

VOCAB = ["cachoeira", "sítio", "queijo", "igreja", "praça"]


class _KeywordEmbedder:
    """Counts a few keywords, plus a constant so no vector is zero; no network."""

    dimension = len(VOCAB) + 1

    def embed_query(self, text):
        low = text.casefold()
        return [float(low.count(word)) for word in VOCAB] + [0.1]

    def embed_documents(self, texts):
        return [self.embed_query(t) for t in texts]


def _body(chunk):
    """The chunk's text after its heading line: what the extractor reads."""
    return chunk.split("\n", 1)[1]


class _ExtractorLLM:
    """Answers the extraction prompt with the canned lines of the chunk it was given."""

    def __init__(self):
        self.calls = 0

    def generate(self, prompt):
        self.calls += 1
        return next(lines for chunk, lines in EXTRACTIONS.items() if _body(chunk) in prompt)


class _AnswerLLM:
    def __init__(self):
        self.prompts = []

    def generate(self, prompt):
        self.prompts.append(prompt)
        return "Perto da cachoeira há queijo."


def _indexed_store():
    store = QdrantStore(client=QdrantClient(":memory:"))
    ingest_documents(
        [Document(name="guia.md", text=f"{CACHOEIRA}\n\n{SITIO}\n\n{IGREJA}")],
        IngestConfig(base="guia", chunkings=["markdown"], embeddings=["kw"]),
        store,
        embedder_factory=lambda name, **kw: _KeywordEmbedder(),
    )
    return store


def _graph(store, llm=None):
    return ensure_graph(
        store, base="guia", chunking="markdown", embedding="kw",
        extractor="mlx-community/Qwen2.5-3B-Instruct-4bit", llm=llm or _ExtractorLLM(),
        embedder=_KeywordEmbedder(),
    )


def test_question_naming_an_entity_brings_the_chunk_of_its_one_hop_neighbour():
    store = _indexed_store()
    assert store.count(collection_name("guia", "markdown", "kw")) == 3  # one chunk per paragraph
    llm = _AnswerLLM()
    rag = build_rag(
        "graph", retriever=None, llm=llm, graph=_graph(store), embedder=_KeywordEmbedder(),
        top_k_entities=1, top_k_relations=1, top_k=2,
    )

    result = rag.answer("O que tem perto da Cachoeira do Dédi?")

    # The question shares no word with the Sítio's chunk: only the Grafo reaches it.
    assert [c["text"] for c in result.contexts] == [CACHOEIRA, SITIO]
    assert all({"source_doc", "chunk_index", "score"} <= set(c) for c in result.contexts)
    assert result.answer == "Perto da cachoeira há queijo."
    # One LLM call, the generation: the naive answer prompt plus the facts.
    [prompt] = llm.prompts
    assert "O que tem perto da Cachoeira do Dédi?" in prompt
    assert SITIO in prompt
    assert "Cachoeira do Dédi → Sítio Boa Vista: A Cachoeira do Dédi fica" in prompt
    assert prompt.startswith("Use o contexto abaixo para responder a pergunta.")


def test_graph_merges_entities_by_normalized_name_and_counts_failed_lines():
    graph = _graph(_indexed_store())
    assert graph.stats == {
        "entities": 4,  # Cachoeira, Sítio (twice, merged), Queijo, Igreja
        "relations": 2,
        "chunks": 3,
        "lines": 8,
        "failed_lines": 1,
        "failed_chunks": 0,
    }
    assert graph.extractor == "mlx-community/Qwen2.5-3B-Instruct-4bit"


def test_graph_is_built_once_and_read_back_from_its_collections():
    store = _indexed_store()
    first = _ExtractorLLM()
    _graph(store, first)
    again = _ExtractorLLM()
    graph = _graph(store, again)
    assert first.calls == 3 and again.calls == 0
    assert graph.stats["entities"] == 4
    # The graph collections never pass for an Índice.
    indexes = [parse_collection_name(n) for n in store.list_collections()]
    assert [i for i in indexes if i is not None] == [("guia", "markdown", "kw")]


def test_graph_technique_is_registered_and_uses_an_index_but_no_retriever():
    technique = rag_registry.get("graph")
    assert technique.uses_index and not technique.uses_retrieval


def test_answer_keeps_the_entities_found_and_the_facts_used_apart_from_the_contexts():
    rag = build_rag(
        "graph", retriever=None, llm=_AnswerLLM(), graph=_graph(_indexed_store()),
        embedder=_KeywordEmbedder(), top_k_entities=1, top_k_relations=1, top_k=2,
    )

    result = rag.answer("O que tem perto da Cachoeira do Dédi?")

    # The question's entity, then its 1-hop neighbour reached through the Grafo.
    assert [(e["name"], e["hop"]) for e in result.graph_explanation["entities"]] == [
        ("Cachoeira do Dédi", 0), ("Sítio Boa Vista", 1),
    ]
    assert all(isinstance(e["score"], float) for e in result.graph_explanation["entities"])
    assert result.graph_explanation["facts"][0] == (
        "Cachoeira do Dédi → Sítio Boa Vista: A Cachoeira do Dédi fica no Sítio Boa Vista."
    )
    # The contexts stay chunks only.
    assert all(set(c) >= {"text", "score"} for c in result.contexts)
    assert not any("→" in c["text"] for c in result.contexts)


CITY = "Santo Antônio da Alegria"
# Ten chunks: the city in nine, the event in two, an unrelated creche in one.
GUIDE = {
    "Primeira edição do encontro.": ["Encontro de Carros Antigos", CITY],
    "Segunda edição do encontro.": ["Encontro de Carros Antigos", CITY],
    "A creche atende crianças.": ["Creche Maria do Carmo", CITY],
    **{f"Rua número {n} da cidade.": [CITY] for n in "abcdef"},
    "A igreja fica na praça.": ["Igreja Matriz"],
}
EVENT_QUESTION = "Em que mês acontece o Encontro de Carros Antigos?"


class _GuideEmbedder:
    """The event question lies nearest to the event, then the creche, then the city."""

    dimension = 4
    _AXES = {"Encontro": 0, "Creche": 1, "Santo": 2}

    def embed_query(self, text):
        if text == EVENT_QUESTION:
            return [0.9, 0.5, 0.3, 0.0]
        vector = [0.0, 0.0, 0.0, 0.1]
        axis = self._AXES.get(text.split()[0])
        if axis is not None:
            vector[axis] = 1.0
        return vector

    def embed_documents(self, texts):
        return [self.embed_query(t) for t in texts]


class _GuideExtractorLLM:
    def generate(self, prompt):
        body = next(b for b in GUIDE if b in prompt)
        return "".join(f"entidade<|>{name}<|>lugar<|>Citado.\n" for name in GUIDE[body]) + "<|FIM|>"


def _guide_graph():
    store = QdrantStore(client=QdrantClient(":memory:"))
    text = "\n\n".join(f"# Seção {i}\n{body}" for i, body in enumerate(GUIDE))
    ingest_documents(
        [Document(name="guia.md", text=text)],
        IngestConfig(base="guia", chunkings=["markdown"], embeddings=["kw"]),
        store, embedder_factory=lambda name, **kw: _GuideEmbedder(),
    )
    return ensure_graph(
        store, base="guia", chunking="markdown", embedding="kw", extractor="qwen",
        llm=_GuideExtractorLLM(), embedder=_GuideEmbedder(),
    )


def test_specificity_is_a_soft_idf_so_an_entity_in_two_chunks_is_not_halved():
    graph = _guide_graph()
    assert len(graph.chunks) == 10

    # The city, in nine chunks of ten, counts for almost nothing; one chunk counts fully.
    assert graph.specificity(CITY.casefold()) < 0.1
    assert graph.specificity("creche maria do carmo") == 1.0
    assert 0.5 < graph.specificity("encontro de carros antigos") < 1.0

    rag = build_rag(
        "graph", retriever=None, llm=_AnswerLLM(), graph=graph, embedder=_GuideEmbedder(),
        top_k_entities=3, top_k_relations=1, top_k=1,
    )
    # The event is nearer the question than the creche: with 1/n its two chunks
    # would halve it below the creche's one; with the soft IDF it comes first.
    [context] = rag.answer(EVENT_QUESTION).contexts
    assert "edição do encontro" in context["text"]


def test_the_extractor_reads_the_chunk_without_its_heading_path():
    class _Recording(_GuideExtractorLLM):
        prompts = []

        def generate(self, prompt):
            self.prompts.append(prompt)
            return super().generate(prompt)

    store = QdrantStore(client=QdrantClient(":memory:"))
    text = "# Guia da cidade\n## Perguntas frequentes\n### O encontro\nPrimeira edição do encontro."
    ingest_documents(
        [Document(name="guia.md", text=text)],
        IngestConfig(base="guia", chunkings=["markdown"], embeddings=["kw"]),
        store, embedder_factory=lambda name, **kw: _GuideEmbedder(),
    )
    llm = _Recording()
    ensure_graph(store, base="guia", chunking="markdown", embedding="kw", extractor="qwen",
                 llm=llm, embedder=_GuideEmbedder())

    # The chunk keeps its headings (retrieval and the answer read them)...
    [chunk] = index_chunks(store, "guia", "markdown", "kw").values()
    assert chunk["text"].startswith("# Guia da cidade\n")
    # ...but the extractor gets the body only: headings are no entities.
    [prompt] = llm.prompts
    assert prompt.rstrip().endswith("Texto: Primeira edição do encontro.\nSaída:")
    assert "Guia da cidade" not in prompt and "Perguntas frequentes" not in prompt


def test_a_graph_built_by_an_older_version_of_the_build_is_rebuilt(monkeypatch):
    from app.core.graph import build

    store = _indexed_store()
    _graph(store)
    monkeypatch.setattr(build, "GRAPH_VERSION", build.GRAPH_VERSION + 1)

    again = _ExtractorLLM()
    _graph(store, again)
    assert again.calls == 3


def test_techniques_without_a_grafo_have_no_graph_explanation():
    from app.core.rag.base import RAGResult

    assert RAGResult(answer="a", contexts=[]).graph_explanation is None
