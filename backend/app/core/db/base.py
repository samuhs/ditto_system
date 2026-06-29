"""SQLAlchemy configuration: engine, session, and declarative base."""
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config.settings import get_settings


class Base(DeclarativeBase):
    """Declarative base for all models."""


engine = create_engine(get_settings().database_url, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, future=True)


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
