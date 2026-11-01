from klod.knowledge import KnowledgeStore
from klod.memory import MemoryStore

def test_semantic_knowledge_retrieval_can_match_different_words(tmp_path):
    store = KnowledgeStore(str(tmp_path / "semantic.sqlite"))
    body = "This guide explains how to register custom creatures in a mod and connect entity behavior to events. " * 2
    saved = store.put("minecraft", "Creature registration", body,
                      "https://example.org/creatures", "CC-BY-4.0", "Example")
    passages = store.split_passages("Creature registration", body, max_chars=400, overlap=40)
    store.save_vectors(saved["id"], "test-embedder", passages[:2], [[1.0, 0.0], [0.8, 0.2]])
    result = store.search_hybrid("minecraft", "custom creature entity", [1.0, 0.0],
                                 "test-embedder", 3)
    assert result
    assert result[0]["id"] == saved["id"]
    assert result[0]["retrieval"] == "semantic"
    assert "Creature registration" in result[0]["passage"]

def test_semantic_memory_retrieval(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite"))
    store.put("npc-1", "promise", "The player promised to protect the village.",
              [1.0, 0.0], "test-embedder")
    hits = store.search("npc-1", "keep settlement safe", 5, [0.99, 0.01], "test-embedder")
    assert hits
    assert hits[0]["memory_key"] == "promise"
    assert hits[0]["retrieval"] == "semantic"
