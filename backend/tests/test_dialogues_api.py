"""Tests for the dialogue listing/detail/rating endpoints (hermetic)."""
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.chat import get_chat_deps
from app.core.chat.deps import ChatDeps
from app.core.db.base import Base
from app.core.db.models import Dialogue, DialogueMessage
from app.core.vectorstore.qdrant import QdrantStore
from app.main import create_app


@pytest.fixture
def env():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    deps = ChatDeps(
        store=QdrantStore(client=QdrantClient(":memory:")),
        session_factory=session_factory,
    )
    app = create_app()
    app.dependency_overrides[get_chat_deps] = lambda: deps
    return TestClient(app), session_factory


def _seed(
    session_factory,
    *,
    snapshot=None,
    messages=(("user", "Oi"),),
    rating=None,
    created_at=None,
):
    session = session_factory()
    try:
        d = Dialogue(
            config_snapshot=snapshot or {"name": "c1", "persona": "travel_guide"},
            rating=rating,
        )
        if created_at is not None:
            d.created_at = created_at
        d.messages = [
            DialogueMessage(role=r, content=c, position=i)
            for i, (r, c) in enumerate(messages)
        ]
        session.add(d)
        session.commit()
        session.refresh(d)
        return d.id
    finally:
        session.close()


def test_list_empty(env):
    client, _ = env
    body = client.get("/dialogues").json()
    assert body == {"items": [], "total": 0, "page": 1, "page_size": 20}


def test_list_pagination(env):
    client, sf = env
    for _ in range(3):
        _seed(sf)
    page1 = client.get("/dialogues?page=1&page_size=2").json()
    assert page1["total"] == 3
    assert len(page1["items"]) == 2
    page2 = client.get("/dialogues?page=2&page_size=2").json()
    assert len(page2["items"]) == 1


def test_list_rated_filter(env):
    client, sf = env
    _seed(sf, rating=8)
    _seed(sf, rating=None)
    rated = client.get("/dialogues?rated=rated").json()
    assert len(rated["items"]) == 1 and rated["items"][0]["rating"] == 8
    unrated = client.get("/dialogues?rated=unrated").json()
    assert len(unrated["items"]) == 1 and unrated["items"][0]["rating"] is None


def test_list_date_filter(env):
    client, sf = env
    _seed(sf, created_at=datetime(2026, 3, 10, 9, 0))
    _seed(sf, created_at=datetime(2026, 3, 11, 9, 0))
    body = client.get("/dialogues?date=2026-03-10").json()
    assert body["total"] == 1


def test_list_sort_rating_asc_puts_unrated_last(env):
    client, sf = env
    _seed(sf, rating=5)
    _seed(sf, rating=2)
    _seed(sf, rating=None)
    ratings = [it["rating"] for it in client.get("/dialogues?sort=rating_asc").json()["items"]]
    assert ratings == [2, 5, None]


def test_list_sort_rating_desc_puts_unrated_last(env):
    client, sf = env
    _seed(sf, rating=5)
    _seed(sf, rating=2)
    _seed(sf, rating=None)
    ratings = [it["rating"] for it in client.get("/dialogues?sort=rating_desc").json()["items"]]
    assert ratings == [5, 2, None]


def test_list_item_fields(env):
    client, sf = env
    long_q = "P" * 100
    _seed(
        sf,
        snapshot={"name": "guia", "persona": "travel_guide"},
        messages=(("user", long_q), ("assistant", "resp")),
    )
    item = client.get("/dialogues").json()["items"][0]
    assert item["name"] == "guia"
    assert item["persona"] == "travel_guide"
    assert item["message_count"] == 2
    assert item["preview"] == "P" * 80  # truncated to 80 chars


def test_list_invalid_params(env):
    client, _ = env
    assert client.get("/dialogues?rated=bogus").status_code == 422
    assert client.get("/dialogues?sort=bogus").status_code == 422
    assert client.get("/dialogues?date=nope").status_code == 422


def test_get_detail_returns_messages_in_order(env):
    client, sf = env
    did = _seed(
        sf,
        snapshot={"name": "c1", "persona": "travel_guide", "base": "viagem"},
        messages=(("user", "Pergunta"), ("assistant", "Resposta")),
    )
    body = client.get(f"/dialogues/{did}").json()
    assert body["id"] == did
    assert body["config_snapshot"]["persona"] == "travel_guide"
    assert body["messages"] == [
        {"role": "user", "content": "Pergunta"},
        {"role": "assistant", "content": "Resposta"},
    ]


def test_get_detail_404(env):
    client, _ = env
    assert client.get("/dialogues/9999").status_code == 404


def test_put_rating_persists(env):
    client, sf = env
    did = _seed(sf)
    resp = client.put(f"/dialogues/{did}/rating", json={"rating": 8})
    assert resp.status_code == 200
    assert resp.json() == {"id": did, "rating": 8}
    assert client.get(f"/dialogues/{did}").json()["rating"] == 8
    # rated_at was stamped
    session = sf()
    try:
        assert session.get(Dialogue, did).rated_at is not None
    finally:
        session.close()


def test_put_rating_is_editable(env):
    client, sf = env
    did = _seed(sf)
    client.put(f"/dialogues/{did}/rating", json={"rating": 8})
    client.put(f"/dialogues/{did}/rating", json={"rating": 3})
    assert client.get(f"/dialogues/{did}").json()["rating"] == 3


def test_put_rating_out_of_range(env):
    client, sf = env
    did = _seed(sf)
    assert client.put(f"/dialogues/{did}/rating", json={"rating": 11}).status_code == 422
    assert client.put(f"/dialogues/{did}/rating", json={"rating": -1}).status_code == 422


def test_put_rating_404(env):
    client, _ = env
    assert client.put("/dialogues/9999/rating", json={"rating": 5}).status_code == 404
