"""GraphRAG in an experiment: it only queries a Grafo built beforehand, never extracts.

run_experiment with fake LLMs, Qdrant :memory: and SQLite (no network, no Postgres).
"""
from contextlib import nullcontext

import pytest

from app.core.db.models import Experiment
from app.core.graph.build import build_graph
from app.core.vectorstore.qdrant import collection_name
from app.experiments.orchestrator import run_experiment
from app.experiments.schemas import QuestionItem
from tests.test_orchestrator import (  # noqa: F401
    _FakeEmbedder,
    _indexed_store,
    _new_experiment,
    _staged_config,
    _staged_deps,
    session_factory,
)

_EXTRACTOR = "mlx-community/Qwen2.5-3B-Instruct-4bit"

# One entity, one relation and a line the parser cannot read, in the extraction format.
_EXTRACTION_REPLY = (
    "entidade<|>Praça Central<|>lugar<|>Praça no centro.\n"
    "relacao<|>Praça Central<|>Igreja Matriz<|>vizinhança<|>A praça fica ao lado da igreja.\n"
    "uma linha fora do formato\n"
    "<|FIM|>"
)


class _ExtractorLLM:
    def generate(self, prompt):
        assert prompt.startswith("Extraia do texto")
        return _EXTRACTION_REPLY


class _AnswerLLM:
    """The LLM de resposta: counts any extraction prompt it is (wrongly) asked."""

    def __init__(self, extractions, prompts=None):
        self._extractions = extractions
        self._prompts = prompts

    def generate(self, prompt):
        if self._prompts is not None:
            self._prompts.append(prompt)
        if prompt.startswith("Extraia do texto"):
            self._extractions.append(prompt)
            return _EXTRACTION_REPLY
        return "Resposta gerada."


def _store_with_grafo(extractors=(_EXTRACTOR,)):
    store = _indexed_store("e5")
    for extractor in extractors:
        build_graph(store, "viagem", "recursive", "e5", extractor, _ExtractorLLM(),
                    lambda: nullcontext(_FakeEmbedder()))
    return store


def _run(session_factory, store, name, llm_names=None, prompts=None, **config):  # noqa: F811
    extractions = []
    deps = _staged_deps(store, session_factory, [])

    def llm_factory(llm_name, **kw):
        if llm_names is not None:
            llm_names.append(llm_name)
        return _AnswerLLM(extractions, prompts)

    deps.llm_factory = llm_factory
    experiment_id = _new_experiment(session_factory, name)
    run_experiment(
        experiment_id,
        _staged_config(**{"graph_extractor": _EXTRACTOR, **config}),
        [QuestionItem(text="Where?", evidence=["Para one."])],
        deps,
    )
    check = session_factory()
    experiment = check.get(Experiment, experiment_id)
    runs = {
        (r.rag_technique, r.retriever): (r.graph_stats, [
            (x.generated_answer, [c["text"] for c in x.retrieved_context], x.scores,
             x.graph_explanation)
            for x in r.results
        ])
        for r in experiment.runs
    }
    status = experiment.status
    check.close()
    return status, runs, extractions


@pytest.mark.parametrize("staged", [True, False])
def test_graph_answers_from_the_grafo_without_calling_the_extractor(session_factory, staged):  # noqa: F811
    store = _store_with_grafo()
    chunks = [p["payload"]["text"] for p in store.scroll(collection_name("viagem", "recursive", "e5"))]
    llm_names = []
    status, runs, extractions = _run(
        session_factory, store, f"graph-{staged}", llm_names=llm_names,
        rags=["naive", "graph"], retrievers=["similarity", "mmr"],
        metrics=["context_hit", "context_recall_gold"], staged=staged,
    )
    assert status == "done"
    # The LLM de resposta is never asked to extract, and the LLM extrator never loads.
    assert extractions == []
    assert set(llm_names) == {"qwen3:1.7b"}
    # graph does not multiply by the Retrievers.
    assert sorted(runs) == [("graph", "similarity"), ("naive", "mmr"), ("naive", "similarity")]
    stats, [(answer, contexts, scores, explanation)] = runs[("graph", "similarity")]
    # The malformed line is counted; the run records which LLM extrator built the Grafo.
    assert stats == {
        "entities": 2, "relations": 1, "chunks": len(chunks),
        "lines": 3 * len(chunks), "failed_lines": len(chunks), "failed_chunks": 0,
        "extractor": _EXTRACTOR,
    }
    assert answer == "Resposta gerada."
    assert contexts == chunks
    assert scores["context_hit"] == 1.0 and scores["context_recall_gold"] == 1.0
    assert sorted(e["name"] for e in explanation["entities"]) == ["Igreja Matriz", "Praça Central"]
    assert explanation["facts"] == ["Praça Central → Igreja Matriz: A praça fica ao lado da igreja."]
    naive_stats, [naive_row] = runs[("naive", "similarity")]
    assert naive_stats is None and naive_row[3] is None


def test_graph_mix_unites_the_grafos_chunks_with_each_retrievers(session_factory):  # noqa: F811
    store = _store_with_grafo()
    chunks = [p["payload"]["text"] for p in store.scroll(collection_name("viagem", "recursive", "e5"))]
    status, runs, extractions = _run(
        session_factory, store, "graph-mix",
        rags=["graph", "graph_mix"], retrievers=["similarity", "mmr"], metrics=["context_hit"],
    )
    assert status == "done" and extractions == []
    assert sorted(runs) == [
        ("graph", "similarity"), ("graph_mix", "mmr"), ("graph_mix", "similarity"),
    ]
    for key in [("graph_mix", "mmr"), ("graph_mix", "similarity")]:
        stats, [(answer, texts, _, _)] = runs[key]
        assert stats["entities"] == 2
        # Every chunk once: the Grafo's and the Retriever's, united.
        assert sorted(texts) == sorted(chunks) and len(texts) == len(set(texts))
        assert answer == "Resposta gerada."


def test_the_experiment_queries_the_grafo_of_its_own_extractor(session_factory):  # noqa: F811
    store = _store_with_grafo((_EXTRACTOR, "qwen3:1.7b"))
    status, runs, extractions = _run(session_factory, store, "two-grafos", rags=["graph"],
                                     metrics=["rouge_l"], graph_extractor="qwen3:1.7b")
    assert status == "done" and extractions == []
    [(stats, _)] = runs.values()
    assert stats["extractor"] == "qwen3:1.7b"


def test_graph_answers_with_the_experiments_snapshot_of_its_answer_prompt(session_factory):  # noqa: F811
    store = _store_with_grafo()
    prompts = []
    deps = _staged_deps(store, session_factory, [])
    deps.llm_factory = lambda name, **kw: _AnswerLLM([], prompts)
    session = session_factory()
    experiment = Experiment(name="graph-snapshot", status="pending", config={"prompts": {"graph": {
        "answer": "RESPONDA {question} COM {context}",
    }}})
    session.add(experiment)
    session.commit()
    experiment_id = experiment.id
    session.close()

    run_experiment(experiment_id,
                   _staged_config(rags=["graph"], metrics=["rouge_l"], graph_extractor=_EXTRACTOR),
                   [QuestionItem(text="Where?")], deps)

    assert [p for p in prompts if p.startswith("RESPONDA Where? COM ")]
    assert not [p for p in prompts if p.startswith("Extraia do texto")]


def test_an_index_without_a_current_grafo_fails_only_its_own_row(session_factory):  # noqa: F811
    store = _indexed_store("e5")  # no Grafo built
    status, runs, extractions = _run(session_factory, store, "no-grafo",
                                     rags=["graph", "naive"], metrics=["rouge_l"])
    assert status == "done" and extractions == []
    answers = {rag: rows[0][0] for (rag, _), (_, rows) in runs.items()}
    assert answers["graph"].startswith("[ERRO: Grafo: não há Grafo de conhecimento atual")
    assert answers["naive"] == "Resposta gerada."
