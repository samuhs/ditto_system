"""The engine survives database restarts: dead pooled connections are replaced."""
from sqlalchemy import text

from app.core.db.base import make_engine


def test_dead_pooled_connection_is_replaced(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'db.sqlite'}")
    pooled = engine.raw_connection()
    dbapi_connection = pooled.dbapi_connection
    pooled.close()  # back to the pool, still open
    # What a database restart leaves behind: an idle pooled connection that is dead.
    dbapi_connection.close()
    with engine.connect() as conn:
        assert conn.execute(text("select 1")).scalar() == 1


def test_a_plain_postgresql_url_uses_the_declared_psycopg2_driver():
    # SQLAlchemy 2.1 made psycopg (v3) the default for postgresql://; the
    # project ships psycopg2-binary.
    assert make_engine("postgresql://u:p@localhost:5432/db").dialect.driver == "psycopg2"


def test_an_explicit_driver_in_the_url_is_kept():
    assert make_engine("sqlite:///:memory:").dialect.driver == "pysqlite"
