"""SQLAlchemy configuration: engine, session, and declarative base."""
from collections.abc import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config.settings import get_settings


class Base(DeclarativeBase):
    """Declarative base for all models."""


def make_engine(url: str) -> Engine:
    """Engine for the app database.

    pool_pre_ping tests each pooled connection before use, so connections left
    dead by a database restart (e.g. Docker Desktop restarting) are replaced
    instead of failing the request or hanging until a TCP timeout.
    """
    return create_engine(url, pool_pre_ping=True)


engine = make_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False)


def get_session() -> Iterator[Session]:
    """FastAPI dependency that provides one session per request."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def create_all() -> None:
    """Create all tables registered on Base."""
    Base.metadata.create_all(engine)
