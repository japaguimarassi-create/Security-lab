from fastapi.testclient import TestClient
from klod import api

def test_specialist_list_and_unknown_route(monkeypatch):
    monkeypatch.setattr(api, "API_KEY", "test-secret")
    client = TestClient(api.app)
    headers = {"X-API-Key": "test-secret"}
    result = client.get("/v1/specialists", headers=headers)
    assert result.status_code == 200
    assert {item["id"] for item in result.json()["specialists"]} == {"programming", "minecraft"}
    unknown = client.post("/v1/specialists/unknown/chat", headers=headers,
        json={"messages":[{"role":"user","content":"hi"}]})
    assert unknown.status_code == 404
