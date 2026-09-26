"""Tests for question-difficulty signals (no network, in-memory Qdrant)."""
import math

import pytest

from app.core.difficulty import (
    CorpusStats,
    corpus_stats_for_base,
    question_profile,
    retrieval_profile,
)

CORPUS = CorpusStats.from_texts([
    "A Ilha do Ar funciona das 8h às 18h.",
    "A Rua da Gastronomia tem doces e queijos.",
    "A Praça da Matriz fica no centro.",
])


def test_pattern_signals_flag_portuguese_question_types():
    profile = question_profile("Qual é o horário de funcionamento da Ilha do Ar?")
    assert profile["temporal"] == 1.0 and profile["negation"] == 0.0
    assert question_profile("Quantos km até Ribeirão Preto?")["numeric"] == 1.0
    assert question_profile("Não tem casa de câmbio?")["negation"] == 1.0
    assert question_profile("Quais são as principais atrações?")["aggregation"] == 1.0
    assert question_profile("Tem Wi-Fi grátis?")["yes_no"] == 1.0
    assert question_profile("Onde fica o centro?")["yes_no"] == 0.0


def test_length_and_sub_questions():
    profile = question_profile("Onde fica o centro? E a praça?")
    assert profile["sub_questions"] == 2.0
    assert profile["question_length"] == 5.0  # "o" and "a" are dropped


def test_corpus_signals_only_with_corpus_stats():
    assert "mean_idf" not in question_profile("Onde fica o centro?")
    profile = question_profile("Onde fica o aeroporto?", CORPUS)
    assert profile["out_of_corpus"] == pytest.approx(2 / 3)  # onde, aeroporto
    assert profile["max_idf"] == pytest.approx(math.log(4 / 1))


def test_rare_terms_raise_mean_idf():
    common = question_profile("Ilha do Ar", CORPUS)["mean_idf"]
    rare = question_profile("cachoeira do Baú", CORPUS)["mean_idf"]
    assert rare > common


def test_retrieval_profile_from_scores_best_first():
    contexts = [{"text": "a", "score": 0.5}, {"text": "b", "score": 0.9}, {"text": "c", "score": 0.7}]
    profile = retrieval_profile(contexts)
    assert profile["top_score"] == 0.9
    assert profile["score_gap"] == pytest.approx(0.2)
    assert profile["score_spread"] > 0


def test_retrieval_profile_empty_without_real_scores():
    assert retrieval_profile([]) == {}
    assert retrieval_profile([{"text": "x", "score": 1.0, "source": "compression"}]) == {}


def test_corpus_stats_for_base_reads_the_first_collection():
    from qdrant_client import QdrantClient

    from app.core.vectorstore.qdrant import QdrantStore

    store = QdrantStore(client=QdrantClient(":memory:"))
    assert corpus_stats_for_base(store, "viagem") is None
    store.ensure_collection("viagem__recursive__e5", 2)
    store.add("viagem__recursive__e5", [[1.0, 0.0], [0.0, 1.0]],
              [{"text": "ilha do ar"}, {"text": "praça da matriz"}])
    stats = corpus_stats_for_base(store, "viagem")
    assert stats.n_docs == 2 and stats.doc_freq["ilha"] == 1


def test_evidence_signals_only_with_evidence():
    assert "evidence_count" not in question_profile("Onde fica o centro?")
    profile = question_profile("Onde fica o centro?", evidence=["O centro fica na praça.", "Perto da igreja."])
    assert profile["evidence_count"] == 2.0
    assert profile["evidence_overlap"] == pytest.approx(2 / 3)  # fica, centro; not onde


def test_evidence_distance_is_one_minus_the_lowest_cosine():
    from app.core.difficulty import evidence_distance

    class _E:
        def embed_query(self, text):
            return {"q": [1.0, 0.0], "near": [1.0, 0.0], "far": [0.0, 1.0]}[text]

    assert evidence_distance(_E(), "q", ["near"]) == pytest.approx(0.0)
    assert evidence_distance(_E(), "q", ["near", "far"]) == pytest.approx(1.0)
