"""Injected prompts flow into agentic RAG and the multi_query retriever."""
from app.core.rag.agentic import AgenticRAG
from app.core.retrieval.multi_query import MultiQueryRetriever


class _StubRetriever:
    def retrieve(self, query: str) -> list[dict]:
        return [{"text": "ctx", "source_doc": "a.txt", "chunk_index": 0, "score": 0.9}]


class _EchoLLM:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return "ANSWER: done"


def test_agentic_uses_injected_decide_prompt():
    llm = _EchoLLM()
    rag = AgenticRAG(
        _StubRetriever(),
        llm,
        prompts={"decide": "DECIDE {question} // {context}", "answer": "ANS {context} {question}"},
    )
    rag.answer("q?")
    assert llm.prompts[0].startswith("DECIDE ")


class _FakeEmbedder:
    def embed_documents(self, texts):
        return [self.embed_query(t) for t in texts]

    def embed_query(self, text):
        return [1.0, 0.0, 0.0]

    @property
    def dimension(self) -> int:
        return 3


class _RecordingLLM:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return "variation one\nvariation two"


def test_multi_query_uses_injected_prompt():
    from qdrant_client import QdrantClient

    from app.core.vectorstore.qdrant import QdrantStore

    store = QdrantStore(client=QdrantClient(":memory:"))
    llm = _RecordingLLM()
    retriever = MultiQueryRetriever(
        store=store,
        collection="missing__x__y",
        embedder=_FakeEmbedder(),
        llm=llm,
        prompts={"generate": "MQ {n} :: {question}"},
    )
    # retrieve() will query an empty/missing collection; we only assert the prompt used.
    try:
        retriever.retrieve("q?")
    except Exception:
        pass
    assert llm.prompts and llm.prompts[0].startswith("MQ 3 :: ")
