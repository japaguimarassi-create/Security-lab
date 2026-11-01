from klod.memory import MemoryStore

def test_memory_roundtrip(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite"))
    store.put("villager-1", "home", "A vila fica perto do rio")
    results = store.search("villager-1", "vila rio")
    assert results
    assert results[0]["memory_key"] == "home"
