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
