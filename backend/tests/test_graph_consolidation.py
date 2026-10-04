"""Tests for the Grafo de conhecimento's consolidation, seen through GraphRAG.

The LLM extrator is canned: each chunk "yields" the lines a small model really
writes for a city guide (the city's name repeated as a suffix, nicknames between
parentheses, close spellings), and the graph is built and queried as in a run.
"""
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


def _body(chunk):
    """The chunk's text after its heading line: what the extractor reads."""
    return chunk.split("\n", 1)[1]


class _ExtractorLLM:
    def generate(self, prompt):
        return next(lines for chunk, lines in EXTRACTIONS.items() if _body(chunk) in prompt)


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


def test_a_name_with_a_number_is_promoted_but_dates_times_and_values_are_not():
    from app.core.graph.consolidation import consolidate
    from app.core.graph.extraction import parse_extraction

    extraction = parse_extraction(
        "entidade<|>Bar do Hélio<|>estabelecimento<|>Bar na rodovia.\n"
        "relacao<|>Monumento Biker 23<|>Bar do Hélio<|>vizinhança<|>Fica ao lado do bar.\n"
        "relacao<|>Bar do Hélio<|>7h às 18h<|>horário<|>Abre das 7h às 18h.\n"
        "relacao<|>Bar do Hélio<|>R$ 20<|>preço<|>Lanche por R$ 20.\n<|FIM|>"
    )

    entities, relations = consolidate([{"chunk_id": 0, "extraction": extraction}])

    assert sorted(e.name for e in entities) == ["Bar do Hélio", "Monumento Biker 23"]
    assert [(r.source, r.target) for r in relations] == [("Monumento Biker 23", "Bar do Hélio")]


def test_synonyms_go_by_spelling_not_by_meaning():
    from app.core.graph.consolidation import link_synonyms
    from app.core.graph.knowledge import GraphEntity

    def entity(name):
        return GraphEntity(key=name.casefold(), name=name, type="lugar", description="",
                           chunk_ids=[0])

    names = ["Serra da Lajinha", "Serra da Laginha", "São Paulo", "Correios",
             "Cachoeira do Deosdédi", "Cachoeira do Deosdedi", "Cachoeira do Adilson"]
    linked = {e.key: e.synonyms for e in link_synonyms([entity(n) for n in names])}

    # A one-letter slip, or an accent, is the same name spelled two ways: linked both ways.
    assert set(linked["serra da lajinha"]) == {"serra da laginha"}
    assert set(linked["serra da laginha"]) == {"serra da lajinha"}
    assert set(linked["cachoeira do deosdédi"]) == {"cachoeira do deosdedi"}
    # Names an embedding puts close (the e5 gave São Paulo ~ Correios 0.8) stay apart.
    assert not linked["são paulo"] and not linked["correios"]
    assert not linked["cachoeira do adilson"]
    assert 0.85 <= linked["serra da lajinha"]["serra da laginha"] <= 1.0
