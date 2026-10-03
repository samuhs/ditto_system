"""Tests for extracting a chunk's entities and relations with an LLM."""
from app.core.graph.extraction import Entity, Relation, extract


class _CannedLLM:
    """Returns a fixed reply and keeps the prompt it received."""

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.prompt = None

    def generate(self, prompt: str) -> str:
        self.prompt = prompt
        return self.reply


CHUNK = (
    "O Parque Ecológico José Jorge Felício fica na Rua Vicentino B. dos Santos "
    "e recebe o Encontro de Carros Antigos."
)

WELL_FORMED = """entidade<|>Parque Ecológico José Jorge Felício<|>lugar<|>Parque na entrada da cidade.
entidade<|>Encontro de Carros Antigos<|>evento<|>Encontro anual de carros antigos.
relacao<|>Encontro de Carros Antigos<|>Parque Ecológico José Jorge Felício<|>sede, evento<|>O encontro acontece no parque.
<|FIM|>"""


def test_well_formed_reply_yields_entities_and_relations():
    llm = _CannedLLM(WELL_FORMED)

    result = extract(llm, CHUNK)

    assert CHUNK in llm.prompt
    assert result.entities == [
        Entity(name="Parque Ecológico José Jorge Felício", type="lugar",
               description="Parque na entrada da cidade."),
        Entity(name="Encontro de Carros Antigos", type="evento",
               description="Encontro anual de carros antigos."),
    ]
    assert result.relations == [
        Relation(source="Encontro de Carros Antigos",
                 target="Parque Ecológico José Jorge Felício",
                 keywords="sede, evento", description="O encontro acontece no parque."),
    ]
    assert result.failed_lines == 0


def test_malformed_lines_are_dropped_and_counted_without_losing_the_good_ones():
    reply = """Aqui está a extração:
1. entidade<|>Ilha do Ar<|>lugar<|>Rampa de voo livre (1.100 m)
- relacao<|>Ilha do Ar<|>Serra da Lajinha<|>localização<|>A Ilha do Ar fica na serra.
entidade<|>Serra da Lajinha<|>lugar
relacao<|><|>Ilha do Ar<|>x<|>sem origem
("entidade"<|>"Morro da Santa Cruz"<|>"lugar"<|>"Morro com cruzeiro no cume.")
<|FIM|>"""

    result = extract(_CannedLLM(reply), CHUNK)

    assert [e.name for e in result.entities] == ["Ilha do Ar", "Morro da Santa Cruz"]
    assert result.entities[0].description == "Rampa de voo livre (1.100 m)"
    assert [(r.source, r.target) for r in result.relations] == [("Ilha do Ar", "Serra da Lajinha")]
    assert result.failed_lines == 3


def test_empty_reply_yields_an_empty_extraction():
    result = extract(_CannedLLM(""), CHUNK)

    assert result.entities == [] and result.relations == []
    assert result.failed_lines == 0


def test_an_edited_prompt_is_used():
    llm = _CannedLLM(WELL_FORMED)

    extract(llm, CHUNK, prompt="Extraia: {text}")

    assert llm.prompt == f"Extraia: {CHUNK}"


def test_entity_types_are_read_without_accents_or_capitals():
    reply = "entidade<|>Prefeitura<|>Organização<|>Governo da cidade.\n<|FIM|>"

    result = extract(_CannedLLM(reply), CHUNK)

    assert result.entities[0].type == "organizacao"
