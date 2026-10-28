import copy
from pathlib import Path

import pytest

from gortguard.agentformat import SCHEMA, load_agent
from gortguard.packformat import validate

EXAMPLE = Path(__file__).parent.parent / "examples" / "agents" / "refund-agent.yaml"
GOOD = load_agent(EXAMPLE)


def _bad(**change):
    agent = copy.deepcopy(GOOD)
    for k, v in change.items():
        if v is None:
            agent.pop(k)
        else:
            agent[k] = v
    return validate(agent, SCHEMA, root=SCHEMA)


def test_refund_example_loads():
    assert GOOD["name"] == "refund-agent"
    assert _bad() == []


def test_tool_needs_a_known_risk_tag():
    tools = copy.deepcopy(GOOD["tools"])
    tools[0]["risk"] = []
    assert _bad(tools=tools)
    tools[0]["risk"] = ["dangerous"]
    assert _bad(tools=tools)


def test_missing_part_fails():
    assert "$: missing channels" in _bad(channels=None)


def test_unknown_channel_and_field_fail():
    assert _bad(channels=["sms"])
    assert "$: unknown field model" in _bad(model="x")


def test_prompt_may_be_a_file():
    assert _bad(prompt={"file": "prompts/refund.md"}) == []


def test_team_tags_are_strings_or_lists():
    assert _bad(tags={"team": ["a", "b"]}) == []
    assert _bad(tags={"team": 3})


def test_not_json_without_pyyaml_is_a_clear_error(tmp_path, monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "yaml", None)
    p = tmp_path / "agent.yaml"
    p.write_text("name: x\n", encoding="utf-8")
    with pytest.raises(ValueError, match="JSON syntax"):
        load_agent(p)
