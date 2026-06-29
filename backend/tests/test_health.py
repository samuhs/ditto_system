def test_health_returns_ok(client):
    """Verifica que GET /health retorna 200 e {"status": "ok"}."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
