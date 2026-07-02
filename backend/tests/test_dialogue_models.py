"""Tests for the Dialogue rating columns."""
from datetime import datetime

from app.core.db.models import Dialogue, DialogueMessage


def test_dialogue_rating_defaults_to_none(db_session):
    d = Dialogue(config_snapshot={"name": "c1"})
    d.messages = [DialogueMessage(role="user", content="Oi", position=0)]
    db_session.add(d)
    db_session.commit()
    db_session.refresh(d)
    assert d.rating is None
    assert d.rated_at is None


def test_dialogue_stores_rating_and_rated_at(db_session):
    when = datetime(2026, 7, 2, 10, 0)
    d = Dialogue(config_snapshot={}, rating=7, rated_at=when)
    db_session.add(d)
    db_session.commit()
    db_session.refresh(d)
    assert d.rating == 7
    assert d.rated_at == when
