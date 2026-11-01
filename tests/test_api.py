from fastapi.testclient import TestClient
from klod import api

def test_api_auth_and_health(monkeypatch, tmp_path):
    monkeypatch.setattr(api, "API_KEY", "test-secret")
    monkeypatch.setattr(api, "memory", api.MemoryStore(str(tmp_path / "memory.sqlite")))
    monkeypatch.setattr(api, "knowledge", api.KnowledgeStore(str(tmp_path / "knowledge.sqlite")))
    client = TestClient(api.app)
    assert client.get("/health").status_code == 200
    assert client.get("/v1/models").status_code == 401
    assert client.get("/v1/models", headers={"X-API-Key": "test-secret"}).status_code == 200

def test_memory_api(monkeypatch, tmp_path):
    monkeypatch.setattr(api, "API_KEY", "test-secret")
    monkeypatch.setattr(api, "SEMANTIC_ENABLED", False)
    monkeypatch.setattr(api, "memory", api.MemoryStore(str(tmp_path / "memory.sqlite")))
    client = TestClient(api.app)
    headers = {"X-API-Key": "test-secret"}
    saved = client.post("/v1/memory", headers=headers,
        json={"namespace":"npc-1","key":"home","value":"perto do rio"})
    assert saved.status_code == 200
    found = client.post("/v1/memory/search", headers=headers,
        json={"namespace":"npc-1","query":"rio"})
    assert found.status_code == 200
    assert found.json()["results"]

def test_specialist_list_and_unknown_route(monkeypatch, tmp_path):
    monkeypatch.setattr(api, "API_KEY", "test-secret")
    client = TestClient(api.app)
    headers = {"X-API-Key": "test-secret"}
    result = client.get("/v1/specialists", headers=headers)
    assert result.status_code == 200
    assert {item["id"] for item in result.json()["specialists"]} == {"programming", "minecraft"}
    unknown = client.post("/v1/specialists/unknown/chat", headers=headers,
        json={"messages":[{"role":"user","content":"hi"}]})
    assert unknown.status_code == 404
