import pytest
from klod.planner import build_planner_messages, parse_action_plan

def test_planner_validates_allowlist():
    messages = build_planner_messages("Proteja a vila", {"nearby": ["zombie"]}, ["alert", "hide"])
    assert messages[-1]["role"] == "user"
    result = parse_action_plan('{"intent":"defend","summary":"Alertar","actions":[{"type":"alert","target":"village","parameters":{},"reason":"threat"}]}', ["alert"])
    assert result["actions"][0]["type"] == "alert"

def test_planner_rejects_unapproved_action():
    raw = '{"intent":"x","summary":"x","actions":[{"type":"delete_world","target":"world","parameters":{}}]}'
    with pytest.raises(ValueError):
        parse_action_plan(raw, ["alert"])
