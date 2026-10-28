import copy
import json
from pathlib import Path

import pytest

from gortguard.agentformat import load_agent
from gortguard.records import (
    FAMILIES,
    check,
    from_chat_events,
    from_spans,
    load_tags,
    tags,
)

EX = Path(__file__).parent.parent / "examples"
AGENT = load_agent(EX / "agents" / "refund-agent.yaml")
CHAT = from_chat_events(json.loads((EX / "runs" / "chat-run.json").read_text(encoding="utf-8")))
TOOL = from_spans(json.loads((EX / "runs" / "tool-run.json").read_text(encoding="utf-8")), agent=AGENT)


@pytest.mark.parametrize("records", [CHAT, TOOL], ids=["chat", "tool"])
def test_synthetic_run_converts_with_every_family(records):
    assert records[0]["record"] == "run"
    for r in records:
        assert check(r) == [], r["id"]
        assert set(r["tags"]) == set(FAMILIES)
        assert all(v == "unknown" or isinstance(v, dict) for v in r["tags"].values())


def test_chat_step_kinds_and_labels_kept():
    assert [s["kind"] for s in CHAT[1:]] == ["session_event", "user_message", "bot_reply", "user_message", "handoff", "session_event"]
    assert CHAT[4]["attributes"]["user_label.request_for_person"] is True
    assert CHAT[3]["tags"]["business"] == "unknown"


def test_tool_kinds_risk_and_timeout():
    assert [s["kind"] for s in TOOL[1:]] == ["handoff", "model_call", "retrieval", "tool_call", "timeout", "guardrail"]
    assert TOOL[5]["tags"]["guard"] == {"risk": ["write", "external", "irreversible"]}
    assert TOOL[0]["source"] == "otel_genai" and TOOL[0]["id"] == "synthetic-tool-1"


def test_finding_needs_quoted_evidence():
    finding = {"record": "finding", "id": "f1", "run_id": "synthetic-chat-1", "step_id": "e3",
               "pattern": "dead-end-i-don-t-understand-replies", "detector": "rule",
               "evidence": "Sorry, I didn't understand that.", "tags": tags(what_failed={"detector": "rule"})}
    assert check(finding) == []
    bad = copy.deepcopy(finding)
    bad["evidence"] = ""
    assert check(bad)


def test_missing_family_or_bad_kind_fails():
    step = copy.deepcopy(CHAT[1])
    del step["tags"]["risk"]
    assert "$.tags: missing risk" in check(step)
    step = copy.deepcopy(CHAT[1])
    step["kind"] = "chit_chat"
    assert check(step)
    assert check({"record": "trace"})


def test_tags_registry_format(tmp_path):
    assert [t["key"] for t in load_tags(EX / "tags.yaml")] == ["owning_team", "agent_version"]
    bad = tmp_path / "tags.yaml"
    bad.write_text('[{"key": "x", "family": "mood", "type": "enum", "source": "field", "status": "approved"}]')
    with pytest.raises(ValueError, match="family"):
        load_tags(bad)
