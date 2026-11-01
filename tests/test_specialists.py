from klod.specialists import get_specialist, list_specialists, route_message


def test_general_is_the_default_and_not_domain_limited():
    item = get_specialist("general")
    assert "not restricted to one topic" in item.system_prompt
    assert item.default_knowledge_namespace is None


def test_programming_specialist_exists():
    item = get_specialist("programming")
    assert "reproducible tests" in item.system_prompt.lower()


def test_minecraft_is_an_optional_specialist():
    item = get_specialist("minecraft")
    assert "optional domain" in item.system_prompt.lower()
    assert item.default_knowledge_namespace == "minecraft"


def test_domain_registry_covers_multiple_fields():
    ids = {item["id"] for item in list_specialists()}
    assert {
        "general", "programming", "science", "mathematics", "research",
        "writing", "education", "creative", "business", "minecraft"
    } <= ids


def test_router_selects_programming():
    result = route_message("Corrija este código Python e encontre o bug.")
    assert result["id"] == "programming"
    assert result["method"] == "keyword_router"


def test_router_selects_science_and_math():
    assert route_message("Explique a relatividade e a física quântica.")["id"] == "science"
    assert route_message("Resolva esta equação de álgebra.")["id"] == "mathematics"


def test_router_selects_research_and_writing():
    assert route_message("Faça uma pesquisa aprofundada com fontes e evidências.")["id"] == "research"
    assert route_message("Escreva um roteiro com este tema.")["id"] == "writing"


def test_router_keeps_unknown_topics_general():
    result = route_message("O que você acha de explorar novas ideias?")
    assert result["id"] == "general"
    assert result["method"] == "general_fallback"


def test_router_understands_minecraft_as_one_domain():
    assert route_message("Como criar um mod Minecraft usando Forge?")["id"] == "minecraft"
