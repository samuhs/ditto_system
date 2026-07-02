"""Tests for chat/dialogue models."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db.base import Base
from app.core.db.models import ChatConfig, Dialogue, DialogueMessage


def _session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_chat_config_persists():
    s = _session()
    cfg = ChatConfig(
        name="viagem-gemini", base="viagem", chunking="recursive", embedding="gemini",
        retriever="similarity", llm="gemini", persona="travel_guide",
    )
    s.add(cfg)
    s.commit()
    assert s.get(ChatConfig, cfg.id).persona == "travel_guide"


def test_dialogue_with_messages_cascade():
    s = _session()
    d = Dialogue(config_snapshot={"base": "viagem"})
    d.messages = [
        DialogueMessage(role="user", content="Oi", position=0),
        DialogueMessage(role="assistant", content="Olá!", position=1),
    ]
    s.add(d)
    s.commit()
    stored = s.get(Dialogue, d.id)
    assert [m.content for m in sorted(stored.messages, key=lambda m: m.position)] == ["Oi", "Olá!"]
    s.delete(stored)
    s.commit()
    assert s.query(DialogueMessage).count() == 0
