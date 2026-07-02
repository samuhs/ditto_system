"""Relational models for experiments, runs, and results."""
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db.base import Base


class Experiment(Base):
    """A comparison experiment across RAG pipeline compositions."""

    __tablename__ = "experiment"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    runs: Mapped[list["ExperimentRun"]] = relationship(
        back_populates="experiment", cascade="all, delete-orphan"
    )


class ExperimentRun(Base):
    """A single chunking x embedding x rag x retriever combination within an experiment."""

    __tablename__ = "experiment_run"

    id: Mapped[int] = mapped_column(primary_key=True)
    experiment_id: Mapped[int] = mapped_column(ForeignKey("experiment.id"))
    chunking: Mapped[str] = mapped_column(String(60))
    embedding: Mapped[str] = mapped_column(String(60))
    rag_technique: Mapped[str] = mapped_column(String(60))
    retriever: Mapped[str] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(20), default="pending")

    experiment: Mapped["Experiment"] = relationship(back_populates="runs")
    results: Mapped[list["RunResult"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class RunResult(Base):
    """Result for a single question within a run combination."""

    __tablename__ = "run_result"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("experiment_run.id"))
    question: Mapped[str] = mapped_column(String)
    reference_answer: Mapped[str | None] = mapped_column(String, nullable=True)
    generated_answer: Mapped[str] = mapped_column(String)
    retrieved_context: Mapped[list] = mapped_column(JSON, default=list)
    scores: Mapped[dict] = mapped_column(JSON, default=dict)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    tokens: Mapped[int] = mapped_column(Integer, default=0)

    run: Mapped["ExperimentRun"] = relationship(back_populates="results")


class ChatConfig(Base):
    """A saved chat configuration binding a collection + retriever + llm + persona."""

    __tablename__ = "chat_config"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    base: Mapped[str] = mapped_column(String(120))
    chunking: Mapped[str] = mapped_column(String(60))
    embedding: Mapped[str] = mapped_column(String(60))
    retriever: Mapped[str] = mapped_column(String(60))
    rag: Mapped[str] = mapped_column(String(60), default="naive")
    llm: Mapped[str] = mapped_column(String(60), default="gemini")
    persona: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Dialogue(Base):
    """A saved conversation, kept for later human evaluation."""

    __tablename__ = "dialogue"

    id: Mapped[int] = mapped_column(primary_key=True)
    config_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    messages: Mapped[list["DialogueMessage"]] = relationship(
        back_populates="dialogue", cascade="all, delete-orphan"
    )


class DialogueMessage(Base):
    """A single message within a saved dialogue."""

    __tablename__ = "dialogue_message"

    id: Mapped[int] = mapped_column(primary_key=True)
    dialogue_id: Mapped[int] = mapped_column(ForeignKey("dialogue.id"))
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(String)
    position: Mapped[int] = mapped_column(Integer, default=0)

    dialogue: Mapped["Dialogue"] = relationship(back_populates="messages")
