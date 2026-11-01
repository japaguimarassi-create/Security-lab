import pytest
from klod.knowledge import KnowledgeStore

def test_knowledge_roundtrip_and_provenance(tmp_path):
    store = KnowledgeStore(str(tmp_path / "knowledge.sqlite"))
    body = "Forge permite registrar entidades e itens por meio de registries e eventos. " * 3
    saved = store.put("minecraft", "Forge docs", body, "https://example.org/forge",
                      "CC-BY-4.0", "Example project")
    assert saved["duplicate"] is False
    result = store.search("minecraft", "registrar entidades")
    assert result
    assert result[0]["source_url"] == "https://example.org/forge"
    assert result[0]["license"] == "CC-BY-4.0"
    duplicate = store.put("minecraft", "Forge docs", body, "https://example.org/forge",
                          "CC-BY-4.0", "Example project")
    assert duplicate["duplicate"] is True

def test_knowledge_rejects_unknown_license(tmp_path):
    store = KnowledgeStore(str(tmp_path / "knowledge.sqlite"))
    with pytest.raises(ValueError):
        store.put("x", "title", "Long enough body " * 10, "https://example.org", "UNKNOWN", "source")
