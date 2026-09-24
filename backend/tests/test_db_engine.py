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
