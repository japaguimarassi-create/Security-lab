from fastapi.testclient import TestClient
from klod import api

class FakeEngine:
    loaded = True
    status = {"loaded": True}
    def __init__(self):
        self.last_messages = None
    def generate(self, messages, max_tokens, temperature, top_p):
        self.last_messages = messages
        return "Use uma fila assíncrona para não bloquear o tick.", 12, 10

def test_specialist_list_and_unknown_route(monkeypatch):
    monkeypatch.setattr(api, "API_KEY", "test-secret")
    client = TestClient(api.app)
    headers = {"X-API-Key": "test-secret"}
    result = client.get("/v1/specialists", headers=headers)
    assert result.status_code == 200
    ids = {item["id"] for item in result.json()["specialists"]}
    assert {"general", "programming", "science", "mathematics", "minecraft"} <= ids
    unknown = client.post("/v1/specialists/unknown/chat", headers=headers,
        json={"messages":[{"role":"user","content":"hi"}]})
    assert unknown.status_code == 404

def test_minecraft_specialist_chat_returns_sources(monkeypatch, tmp_path):
    monkeypatch.setattr(api, "API_KEY", "test-secret")
    monkeypatch.setattr(api, "SEMANTIC_ENABLED", False)
    fake_engine = FakeEngine()
    monkeypatch.setattr(api, "engine", fake_engine)
    monkeypatch.setattr(api, "knowledge", api.KnowledgeStore(str(tmp_path / "knowledge.sqlite")))
    monkeypatch.setattr(api, "memory", api.MemoryStore(str(tmp_path / "memory.sqlite")))
    client = TestClient(api.app)
    headers = {"X-API-Key": "test-secret"}
    body = "Forge event handlers should avoid expensive work on the server tick. " * 3
    saved = client.post("/v1/knowledge/documents", headers=headers, json={
        "namespace":"minecraft","title":"Server tick guide","body":body,
        "source_url":"https://example.org/forge-tick","license":"CC-BY-4.0",
        "attribution":"Example"
    })
    assert saved.status_code == 200
    response = client.post("/v1/specialists/minecraft/chat", headers=headers, json={
        "messages":[{"role":"user","content":"How do I avoid freezing a Forge tick?"}]
    })
    assert response.status_code == 200
    payload = response.json()
    assert payload["specialist"] == "minecraft"
    assert payload["choices"][0]["message"]["content"].startswith("Use uma fila")
    assert payload["sources"][0]["url"] == "https://example.org/forge-tick"
    assert "Forge" in fake_engine.last_messages[0]["content"]
