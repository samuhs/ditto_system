"""Tests for retrieval metrics against annotated reference evidence."""
from app.core.evaluation.base import EvalSample, evaluation_registry
from app.core.evaluation.gold_metrics import (
    ContextHit,
    ContextMRR,
    ContextRecallGold,
    evidence_found_in,
)

EVIDENCE_CENTER = "O centro se desenvolve ao redor da Praça Tereza Benedeti Chocair"
EVIDENCE_EXCHANGE = "não temos casas de câmbio dedicadas"
CHUNK_CENTER = (
    "### 1. Onde fica o centro da cidade?\n\nAh, o coração! O **centro** se desenvolve "
    "ao redor da **Praça Tereza Benedeti Chocair**, conhecida como Praça da Matriz."
)
CHUNK_EXCHANGE = "Como a cidade é menor, não temos casas de câmbio dedicadas."
CHUNK_OTHER = "A Ilha do Ar funciona das 8h às 18h e tem voo livre."


def _sample(contexts, evidence):
    return EvalSample(question="q", answer="a", contexts=contexts, reference_contexts=evidence)


def test_evidence_matches_despite_markdown_case_and_punctuation():
    assert evidence_found_in(EVIDENCE_CENTER, CHUNK_CENTER)
    assert not evidence_found_in(EVIDENCE_CENTER, CHUNK_OTHER)


def test_evidence_split_across_chunks_matches_the_chunk_holding_most_of_it():
    first_half = "O centro se desenvolve ao redor da Praça"
    assert evidence_found_in(EVIDENCE_CENTER, first_half)


def test_a_chunk_much_shorter_than_the_evidence_does_not_count():
    assert not evidence_found_in(EVIDENCE_CENTER, "Praça Tereza")


def test_context_hit_is_one_when_any_retrieved_chunk_holds_evidence():
    assert ContextHit().score(_sample([CHUNK_OTHER, CHUNK_CENTER], [EVIDENCE_CENTER])) == 1.0
    assert ContextHit().score(_sample([CHUNK_OTHER], [EVIDENCE_CENTER])) == 0.0


def test_context_mrr_is_the_reciprocal_rank_of_the_first_relevant_chunk():
    assert ContextMRR().score(_sample([CHUNK_CENTER, CHUNK_OTHER], [EVIDENCE_CENTER])) == 1.0
    assert ContextMRR().score(_sample([CHUNK_OTHER, CHUNK_OTHER, CHUNK_CENTER], [EVIDENCE_CENTER])) == 1 / 3
    assert ContextMRR().score(_sample([CHUNK_OTHER], [EVIDENCE_CENTER])) == 0.0


def test_context_recall_gold_is_the_share_of_evidence_retrieved():
    evidence = [EVIDENCE_CENTER, EVIDENCE_EXCHANGE]
    assert ContextRecallGold().score(_sample([CHUNK_CENTER], evidence)) == 0.5
    assert ContextRecallGold().score(_sample([CHUNK_EXCHANGE, CHUNK_CENTER], evidence)) == 1.0


def test_gold_metrics_need_reference_contexts_and_are_registered():
    for name, metric in [("context_hit", ContextHit), ("context_mrr", ContextMRR),
                         ("context_recall_gold", ContextRecallGold)]:
        assert evaluation_registry.get(name) is metric
        assert metric.requires_reference_contexts and not metric.requires_reference
