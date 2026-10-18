"""Token usage of the LLM calls made while answering one question.

The RAG techniques call the LLM several times per answer (agentic, crag, compression, a
multi-query retriever), always on the thread that answers the question. A thread-local
accumulator therefore collects every call of one answer without threading it through
each technique: the orchestrator opens a `track()` scope around `rag.answer`, and every
`ChatModelLLM.generate` inside it adds its call.
"""
import threading
from contextlib import contextmanager

_state = threading.local()


def empty() -> dict:
    return {"calls": 0, "input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0}


@contextmanager
def track():
    """Collect the calls made on this thread inside the block; yields the running totals."""
    previous = getattr(_state, "totals", None)
    totals = empty()
    _state.totals = totals
    try:
        yield totals
    finally:
        _state.totals = previous


def record(usage_metadata: dict | None) -> None:
    """Add one call (with LangChain's usage_metadata, when the provider reports it)."""
    totals = getattr(_state, "totals", None)
    if totals is None:
        return
    totals["calls"] += 1
    if not usage_metadata:
        return
    totals["input_tokens"] += int(usage_metadata.get("input_tokens") or 0)
    totals["output_tokens"] += int(usage_metadata.get("output_tokens") or 0)
    details = usage_metadata.get("output_token_details") or {}
    totals["reasoning_tokens"] += int(details.get("reasoning") or 0)
