"""GET /system/memory reports the profile and what is loaded."""
from app.core.memory.manager import ModelManager, get_model_manager


class _Emb:
    dimension = 1


def test_memory_endpoint_reports_profile_and_models(client):
    manager = ModelManager(lambda name, **kw: _Emb(), max_local=1, is_local=lambda n: True)
    client.app.dependency_overrides[get_model_manager] = lambda: manager
    with manager.acquire("e5", "cpu"):
        body = client.get("/system/memory").json()
    assert body["profile"]["name"] == "standard"
    assert body["loaded_models"] == [{"name": "e5", "device": "cpu", "local": True, "in_use": 1}]
    assert body["total_bytes"] > 0 and body["process_memory_bytes"] > 0
