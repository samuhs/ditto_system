"""Schemas and result types for the conversational agent."""
from dataclasses import dataclass, field

from pydantic import BaseModel


class ChatMessage(BaseModel):
    """One message in a conversation turn history."""

    role: str  # "user" | "assistant"
    content: str


@dataclass
class ChatTurnResult:
    """The agent's answer for one turn plus the contexts it retrieved."""

    answer: str
    contexts: list[str] = field(default_factory=list)
    # {"question": pre-retrieval signals, "retrieval": signals from the chunk scores}
    difficulty: dict = field(default_factory=dict)
    # The standalone question the documents were searched with ("" when not searched).
    query: str = ""


@dataclass
class ChatConfigView:
    """Plain snapshot of a chat config, decoupled from the ORM."""

    base: str
    chunking: str
    embedding: str
    retriever: str
    rag: str
    llm: str
    persona: str
