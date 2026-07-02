"""Hermetic tests for the chat core (no network, no real model)."""
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.core.chat.agent import (
    build_retrieve_tool,
    extract_turn,
    to_lc_messages,
)
from app.core.chat.schemas import ChatMessage


class _StubRetriever:
    def retrieve(self, query: str) -> list[dict]:
        return [{"text": "The center is the main square.", "source_doc": "a.txt", "score": 0.9}]


def test_build_retrieve_tool_returns_formatted_context():
    tool = build_retrieve_tool(_StubRetriever())
    out = tool.invoke({"query": "where is the center?"})
    assert "main square" in out


class _BrokenRetriever:
    def retrieve(self, query: str) -> list[dict]:
        raise RuntimeError("collection missing")


def test_retrieve_tool_degrades_on_error():
    tool = build_retrieve_tool(_BrokenRetriever())
    out = tool.invoke({"query": "x"})
    assert isinstance(out, str) and out  # graceful message, no raise


def test_to_lc_messages_maps_roles():
    msgs = to_lc_messages([ChatMessage(role="user", content="oi"), ChatMessage(role="assistant", content="olá")])
    assert isinstance(msgs[0], HumanMessage) and msgs[0].content == "oi"
    assert isinstance(msgs[1], AIMessage) and msgs[1].content == "olá"


def test_extract_turn_pulls_reply_and_contexts():
    result = {"messages": [
        HumanMessage(content="oi"),
        ToolMessage(content="CTX one", tool_call_id="t1"),
        AIMessage(content="resposta final"),
    ]}
    turn = extract_turn(result)
    assert turn.answer == "resposta final"
    assert turn.contexts == ["CTX one"]
