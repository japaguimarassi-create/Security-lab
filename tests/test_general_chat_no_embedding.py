from fastapi.testclient import TestClient
from klod import api

class FakeEngine:
    loaded = True
    status = {"loaded": True}
    def generate(self, messages, max_tokens, temperature, top_p):
        return "Olá!", 3, 2

class ForbiddenEmbedder:
    def encode_query(self, text):
        raise AssertionError("Embedding model should not run for a plain chat request")

def test_general_chat_skips_embedding_without_memory_or_knowledge(monkeypatch):
    monkeypatch.setattr(api, "API_KEY", "test-secret")
    monkeypatch.setattr(api, "SEMANTIC_ENABLED", True)
    monkeypatch.setattr(api, "engine", FakeEngine())
    monkeypatch.setattr(api, "embedder", ForbiddenEmbedder())
    client = TestClient(api.app)
    response = client.post("/v1/chat/completions",
        headers={"X-API-Key": "test-secret"},
        json={"messages":[{"role":"user","content":"Oi Klod"}]})
    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == "Olá!"
