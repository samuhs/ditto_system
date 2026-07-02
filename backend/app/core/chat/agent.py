"""LangGraph ReAct conversational agent over a retriever tool."""
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from app.core.chat.schemas import ChatMessage, ChatTurnResult
from app.core.config.settings import get_settings
from app.core.rag.base import format_context

_CHAT_MODELS = {"gemini": "gemini-2.5-flash-lite"}


def build_chat_model(llm: str):
    """Return a tool-calling chat model for the given llm name. KeyError if unknown."""
    if llm not in _CHAT_MODELS:
        raise KeyError(f"unknown chat model: {llm}")
    from langchain_google_genai import ChatGoogleGenerativeAI

    return ChatGoogleGenerativeAI(
        model=_CHAT_MODELS[llm],
        google_api_key=get_settings().gemini_api_key,
    )


def build_retrieve_tool(retriever):
    """Build a search tool the agent can call; degrades to a message on failure."""

    @tool
    def retrieve(query: str) -> str:
        """Search the destination's documents for information relevant to the query."""
        try:
            contexts = retriever.retrieve(query)
        except Exception:  # noqa: BLE001  a retrieval failure must not crash the turn
            return "No information was found for this query."
        return format_context(contexts) or "No information was found for this query."

    return retrieve


def to_lc_messages(messages: list[ChatMessage]) -> list:
    """Convert our chat messages to LangChain Human/AI messages."""
    converted = []
    for m in messages:
        if m.role == "assistant":
            converted.append(AIMessage(content=m.content))
        else:
            converted.append(HumanMessage(content=m.content))
    return converted


def extract_turn(result: dict) -> ChatTurnResult:
    """Pull the final answer and any tool-retrieved contexts from an agent result."""
    messages = result.get("messages", [])
    contexts = [m.content for m in messages if isinstance(m, ToolMessage)]
    answer = ""
    for m in reversed(messages):
        if isinstance(m, AIMessage) and m.content:
            answer = m.content if isinstance(m.content, str) else str(m.content)
            break
    return ChatTurnResult(answer=answer, contexts=contexts)


def run_agent(persona: str, retriever, chat_model, messages: list[ChatMessage]) -> ChatTurnResult:
    """Run one conversational turn through a ReAct agent and return the result."""
    agent = create_react_agent(chat_model, tools=[build_retrieve_tool(retriever)], prompt=persona)
    result = agent.invoke({"messages": to_lc_messages(messages)})
    return extract_turn(result)
