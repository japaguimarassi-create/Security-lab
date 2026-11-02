from klod.memory import MemoryStore

def test_memory_roundtrip(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite"))
    store.put("villager-1", "home", "A vila fica perto do rio")
    results = store.search("villager-1", "vila rio")
    assert results
    assert results[0]["memory_key"] == "home"

def test_updating_memory_removes_stale_embedding(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite"))
    store.put("npc", "goal", "protect the village", [1.0, 0.0], "embed-v1")
    store.put("npc", "goal", "learn to farm")
    hits = store.search("npc", "keep the settlement safe", 5, [1.0, 0.0], "embed-v1")
    assert hits == []
