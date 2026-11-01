from klod.specialists import get_specialist, list_specialists

def test_minecraft_specialist_enforces_version_compatibility():
    item = get_specialist("minecraft")
    assert "1.7.10" in item.system_prompt
    assert "Java 8" in item.system_prompt
    assert "never mix" in item.system_prompt.lower()
    assert item.default_knowledge_namespace == "minecraft"

def test_programming_specialist_exists():
    item = get_specialist("programming")
    assert "reproducible test" in item.system_prompt.lower()
    assert {x["id"] for x in list_specialists()} == {"programming", "minecraft"}
