from fastapi.testclient import TestClient
from klod import api


class FakeEngine:
    loaded = True
    status = {"loaded": True}

    def __init__(self):
        self.messages = None

    def generate(self, messages, max_tokens, temperature, top_p):
        self.messages = messages
        return "Resposta de teste.", 12, 4


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


def test_route_endpoint_is_domain_general(monkeypatch):
    monkeypatch.setattr(api, "API_KEY", "test-secret")
    client = TestClient(api.app)
    headers = {"X-API-Key": "test-secret"}
    science = client.post("/v1/route", headers=headers,
        json={"message":"Explique a relatividade e a física quântica."})
    general = client.post("/v1/route", headers=headers,
        json={"message":"Quero conversar sobre uma ideia nova."})
    assert science.json()["id"] == "science"
    assert general.json()["id"] == "general"


def test_chat_auto_routes_and_uses_general_core(monkeypatch):
    monkeypatch.setattr(api, "API_KEY", "test-secret")
    fake = FakeEngine()
    monkeypatch.setattr(api, "engine", fake)
    client = TestClient(api.app)
    response = client.post("/v1/chat/completions",
        headers={"X-API-Key": "test-secret"},
        json={"messages":[{"role":"user","content":"Explique a relatividade."}]})
    assert response.status_code == 200
    assert response.json()["specialist"] == "science"
    assert response.json()["routing"]["method"] == "keyword_router"
    assert "science specialist" in fake.messages[0]["content"].lower()


def test_chat_can_force_general_mode(monkeypatch):
    monkeypatch.setattr(api, "API_KEY", "test-secret")
    fake = FakeEngine()
    monkeypatch.setattr(api, "engine", fake)
    client = TestClient(api.app)
    response = client.post("/v1/chat/completions",
        headers={"X-API-Key": "test-secret"},
        json={"messages":[{"role":"user","content":"Explique a relatividade."}],
              "auto_route":False})
    assert response.status_code == 200
    assert response.json()["specialist"] == "general"
    assert response.json()["routing"]["method"] == "disabled"
    assert "general-purpose" in fake.messages[0]["content"].lower()
