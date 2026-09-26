"""SQLAlchemy configuration: engine, session, and declarative base."""
from collections.abc import Iterator

from sqlalchemy import Engine, create_engine, inspect, text
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


# Columns added after their table first shipped. create_all never alters an
# existing table, so these are added on startup: {table: {column: SQL type}}.
ADDED_COLUMNS = {"run_result": {"reference_contexts": "JSON", "retrieval_signals": "JSON"}}


def add_missing_columns(bind: Engine, columns: dict[str, dict[str, str]]) -> None:
    """Add each listed column its (existing) table still lacks. Idempotent."""
    inspector = inspect(bind)
    with bind.begin() as conn:
        for table, wanted in columns.items():
            if not inspector.has_table(table):
                continue
            present = {c["name"] for c in inspector.get_columns(table)}
            for column, sql_type in wanted.items():
                if column not in present:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}"))


def create_all() -> None:
    """Create all tables registered on Base and add columns newer than a table."""
    Base.metadata.create_all(engine)
    add_missing_columns(engine, ADDED_COLUMNS)
