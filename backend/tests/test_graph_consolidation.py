"""Tests for the Grafo de conhecimento's consolidation, seen through GraphRAG.

The LLM extrator is canned: each chunk "yields" the lines a small model really
writes for a city guide (the city's name repeated as a suffix, nicknames between
parentheses, close spellings), and the graph is built and queried as in a run.
"""
import math
import zlib

from qdrant_client import QdrantClient

from app.core.graph.build import ensure_graph
from app.core.rag.base import build_rag
from app.core.vectorstore.qdrant import QdrantStore
from app.ingestion.pipeline import ingest_documents
from app.ingestion.schemas import Document, IngestConfig

CITY = "Santo Antônio da Alegria"

DEOSDEDI = "# Deosdédi\nA Cachoeira do Deosdédi tem uma queda de doze metros."
DEOSDEDI_CITY = "# Acesso\nA Cachoeira do Deosdédi fica a oito quilômetros do centro."
DEDI = "# Dédi\nA Cachoeira do Dédi tem um poço para banho."
LAJINHA = "# Lajinha\nA Serra da Lajinha tem uma trilha de seis quilômetros."
LAGINHA = "# Laginha\nNo alto da Serra da Laginha há um mirante."
ADILSON = "# Adilson\nA Cachoeira do Adilson recebe visitas aos domingos."
OVERVIEW = "# Roteiro\nO roteiro passa pelo Museu, pela Praça, pela Igreja e pelo Coreto."

EXTRACTIONS = {
    DEOSDEDI: (
        "entidade<|>Cachoeira do Deosdédi (Cachoeira do Dédi)<|>lugar<|>Queda de doze metros.\n"
        f"entidade<|>{CITY}<|>lugar<|>Município do guia.\n"
        f"relacao<|>Cachoeira do Deosdédi (Cachoeira do Dédi)<|>{CITY}<|>localização<|>"
        "A cachoeira fica no município.\n<|FIM|>"
    ),
    DEOSDEDI_CITY: (
        f"entidade<|>Cachoeira do Deosdédi em {CITY}<|>estabelecimento<|>"
        "Fica a oito quilômetros do centro.\n"
        f"entidade<|>{CITY}<|>lugar<|>Município do guia.\n<|FIM|>"
    ),
    DEDI: (
        "entidade<|>Cachoeira do Dédi<|>lugar<|>Tem um poço para banho.\n"
        f"entidade<|>{CITY}<|>lugar<|>Município do guia.\n<|FIM|>"
    ),
    LAJINHA: (
        "entidade<|>Serra da Lajinha<|>lugar<|>Tem uma trilha de seis quilômetros.\n"
        f"entidade<|>{CITY}<|>lugar<|>Município do guia.\n<|FIM|>"
    ),
    LAGINHA: (
        "entidade<|>Serra da Laginha<|>lugar<|>Tem um mirante no alto.\n<|FIM|>"
    ),
    ADILSON: (
        "entidade<|>Cachoeira do Adilson<|>lugar<|>Recebe visitas aos domingos.\n"
        "relacao<|>Cachoeira do Adilson<|>Prefeitura<|>gestão<|>A Prefeitura cuida da cachoeira.\n"
        "relacao<|>Cachoeira do Adilson<|>9 de junho de 2022<|>data<|>Reaberta nessa data.\n"
        f"entidade<|>{CITY}<|>lugar<|>Município do guia.\n<|FIM|>"
    ),
    OVERVIEW: (
        f"entidade<|>{CITY}<|>lugar<|>Município do roteiro.\n"
        "entidade<|>Museu<|>lugar<|>Parada do roteiro.\n"
        "entidade<|>Praça<|>lugar<|>Parada do roteiro.\n"
        "entidade<|>Igreja<|>lugar<|>Parada do roteiro.\n"
        "entidade<|>Coreto<|>lugar<|>Parada do roteiro.\n"
        f"relacao<|>Museu<|>{CITY}<|>roteiro<|>O museu fica no município.\n"
        f"relacao<|>Praça<|>{CITY}<|>roteiro<|>A praça fica no município.\n"
        f"relacao<|>Igreja<|>{CITY}<|>roteiro<|>A igreja fica no município.\n"
        f"relacao<|>Coreto<|>{CITY}<|>roteiro<|>O coreto fica no município.\n<|FIM|>"
    ),
}

DIMENSION = 512


class _TrigramEmbedder:
    """Hashed character trigrams of the casefolded text: close spellings are close."""

    dimension = DIMENSION

    def embed_query(self, text):
        low = f"  {text.casefold()}  "
        vector = [0.0] * DIMENSION
        for i in range(len(low) - 2):
            vector[zlib.crc32(low[i:i + 3].encode()) % DIMENSION] += 1.0
        return vector

    def embed_documents(self, texts):
        return [self.embed_query(t) for t in texts]


def _cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    return dot / math.sqrt(sum(x * x for x in a) * sum(y * y for y in b))


class _ExtractorLLM:
    def generate(self, prompt):
        return next(lines for chunk, lines in EXTRACTIONS.items() if chunk in prompt)


class _AnswerLLM:
    def generate(self, prompt):
        return "Resposta."


def _graph():
    store = QdrantStore(client=QdrantClient(":memory:"))
    ingest_documents(
        [Document(name="guia.md", text="\n\n".join(EXTRACTIONS))],
        IngestConfig(base="guia", chunkings=["markdown"], embeddings=["tri"]),
        store,
        embedder_factory=lambda name, **kw: _TrigramEmbedder(),
    )
    return ensure_graph(
        store, base="guia", chunking="markdown", embedding="tri", extractor="qwen",
        llm=_ExtractorLLM(), embedder=_TrigramEmbedder(),
    )


def _chunk_text(graph, chunk_id):
    return graph.chunks[chunk_id]["text"]


def test_city_suffix_and_parenthesised_nickname_make_one_entity_with_an_alias():
    graph = _graph()

    entity = graph.entities["cachoeira do deosdédi"]
    assert entity.name == "Cachoeira do Deosdédi"
    assert entity.aliases == ["Cachoeira do Dédi"]
    # The nickname's own mention joins it too.
    assert sorted(_chunk_text(graph, c) for c in entity.chunk_ids) == sorted(
        [DEOSDEDI, DEOSDEDI_CITY, DEDI]
    )
    # Type by majority (lugar twice, estabelecimento once); descriptions concatenated.
    assert entity.type == "lugar"
    assert entity.description == (
        "Queda de doze metros. Fica a oito quilômetros do centro. Tem um poço para banho."
    )
    assert not [k for k in graph.entities if "dédi" in k and k != "cachoeira do deosdédi"]
    assert not [k for k in graph.entities if k.endswith(CITY.casefold()) and k != CITY.casefold()]
    # The relation follows its endpoint to the consolidated entity.
    assert "cachoeira do deosdédi" in graph.neighbours(CITY.casefold())


def test_close_spellings_are_linked_as_synonyms_and_different_entities_stay_apart():
    graph = _graph()
    embedder = _TrigramEmbedder()
    # The fake embedder puts the pairs on each side of the 0.8 threshold.
    assert _cosine(embedder.embed_query("Serra da Lajinha"),
                   embedder.embed_query("Serra da Laginha")) >= 0.8
    assert _cosine(embedder.embed_query("Cachoeira do Adilson"),
                   embedder.embed_query("Cachoeira do Deosdédi")) < 0.8

    lajinha, laginha = graph.entities["serra da lajinha"], graph.entities["serra da laginha"]
    # Linked both ways, never merged.
    assert "serra da laginha" in lajinha.synonyms and "serra da lajinha" in laginha.synonyms
    assert not graph.entities["cachoeira do adilson"].synonyms
    assert "cachoeira do adilson" not in graph.entities["cachoeira do deosdédi"].synonyms

    # A question naming one spelling reaches the chunk of the other through the link.
    rag = build_rag(
        "graph", retriever=None, llm=_AnswerLLM(), graph=graph, embedder=embedder,
        top_k_entities=1, top_k_relations=1, top_k=2,
    )
    texts = [c["text"] for c in rag.answer("Serra da Lajinha").contexts]
    assert LAJINHA in texts and LAGINHA in texts


def test_the_city_named_in_almost_every_chunk_does_not_dominate_the_chunk_scores():
    graph = _graph()
    embedder = _TrigramEmbedder()
    rag = build_rag(
        "graph", retriever=None, llm=_AnswerLLM(), graph=graph, embedder=embedder,
        top_k_entities=2, top_k_relations=1, top_k=2,
    )
    question = f"Trilha na Serra da Lajinha em {CITY}"
    # Both the city and the Serra are linked to the question...
    linked = graph.search_entities(embedder.embed_query(question), 2)
    assert {e.key for e, _ in linked} == {CITY.casefold(), "serra da lajinha"}

    texts = [c["text"] for c in rag.answer(question).contexts]
    # ...but the Serra's chunk comes first, not the roteiro that names the city's neighbours.
    assert texts == [LAJINHA, LAGINHA]


def test_a_relation_endpoint_with_no_entity_line_is_promoted_unless_it_is_a_date():
    graph = _graph()

    prefeitura = graph.entities["prefeitura"]
    assert prefeitura.type == "outro"
    assert prefeitura.description == "A Prefeitura cuida da cachoeira."
    assert [_chunk_text(graph, c) for c in prefeitura.chunk_ids] == [ADILSON]
    assert graph.neighbours("prefeitura") == ["cachoeira do adilson"]
    # The date is no entity, and its relation is gone.
    assert not [k for k in graph.entities if any(ch.isdigit() for ch in k)]
    assert graph.neighbours("cachoeira do adilson") == ["prefeitura"]
