import json
import time

import pytest

from gortguard import guard as G
from gortguard.pack import pack
from gortguard.records import check

CARD = "4111 1111 1111 1111"  # a published test card number, checksum-valid
NAMES = [g.name for g in G.BUILT_IN]


def p_(**kw):
    return pack(bundles=["core", "handoff"], enforce=NAMES, **kw)


# --- one test per built-in guardrail ---


def test_card_number_masked():
    r = p_().check_user_input(f"my card is {CARD}", {})
    assert r.action == "fix" and r.value["text"] == "my card is [card]"
    assert p_().check_user_input("order 12345", {}).action == "ok"


def test_resent_message_blocked():
    r = p_().check_user_input({"text": "hi", "id": "m1"}, {"message_ids": ["m1"]})
    assert r.action == "block"
    assert p_().check_user_input({"text": "hi", "id": "m2"}, {"message_ids": ["m1"]}).action == "ok"


def test_filler_opener_dropped():
    p = p_(settings={"filler_openers": ["Great question"]})
    r = p.check_reply("Great question! Reset it in Settings.", {})
    assert r.action == "fix" and r.value == "Reset it in Settings."
    assert p.check_reply("Reset it in Settings. Great question!", {}).action == "ok"  # opener only
    assert p_().check_reply("Great question! Reset it.", {}).action == "ok"  # list blank until the team sets it


def test_saved_without_write_corrected():
    p = p_(settings={"saved_phrases": ["I've saved"]})
    r = p.check_reply("I've saved your address.", {})
    assert r.action == "fix" and r.value == "I've saved your address. Correction: that was not saved."
    wrote = {"steps": [{"kind": "memory_write", "ok": True}]}
    assert p.check_reply("I've saved your address.", wrote).action == "ok"


def test_stale_source_dropped():
    docs = [{"id": "a", "refresh_by": "2026-01-01"}, {"id": "b", "refresh_by": "2027-01-01"}, {"id": "c"}]
    r = p_().check_retrieved(docs, {"today": "2026-11-03"})
    assert r.action == "fix" and [d["id"] for d in r.value] == ["b", "c"]


def test_unapproved_summary_blocked():
    p = p_()
    assert p.check_memory_write({"kind": "summary"}, {}).action == "block"
    assert p.check_memory_write({"kind": "summary", "approved": True}, {}).action == "ok"


def test_stale_slot_blocked():
    call = {"tool": "refund", "args": {"order_id": "A1"}}
    assert p_().check_tool_call(call, {"slots": {"order_id": "A2"}}).action == "block"
    assert p_().check_tool_call(call, {"slots": {"order_id": "A1"}}).action == "ok"


def test_over_limit_held_and_blank_limit_never_fires():
    p = p_()
    calls = []

    @p.guard("refund", risk="irreversible", limit={"amount": 50})
    def refund(order_id, amount):
        calls.append(amount)

    refund("A1", 20)
    with pytest.raises(G.Held) as e:
        refund("A1", 80)
    assert e.value.result.action == "handoff" and calls == [20]

    @p.guard("refund", limit={"amount": None})  # blank: GORT never invents the number
    def refund2(order_id, amount):
        return amount

    assert refund2("A1", 10**9) == 10**9


def test_person_not_reached_hands_off():
    asked = [{"kind": "user_message", "label": "human"}, {"kind": "bot_reply"}]
    assert p_().check_handoff({"steps": asked}).action == "ok"  # one bot turn so far
    assert p_().check_handoff({"steps": asked + [{"kind": "bot_reply"}]}).action == "handoff"
    assert p_().check_handoff({"steps": asked + [{"kind": "handoff"}, {"kind": "bot_reply"}]}).action == "ok"


def test_untested_version_logged():
    assert p_().check_run({"prompt_version": "v3"}).action == "log"
    assert p_().check_run({"prompt_version": "v3", "eval_run_id": "e1"}).action == "ok"


# --- runner ---


def test_log_only_by_default():
    p = pack(bundles=["core"])
    r = p.check_user_input(f"card {CARD}", {})
    assert r.action == "log" and CARD in r.value["text"]  # nothing changed until the team enforces it
    assert p.log[-1]["tags"]["guard"]["mode"] == "log_only"


def test_guardrails_follow_the_pack():
    assert "person-not-reached" not in [g.name for g in pack(bundles=["core"]).guardrails]


def test_streaming_checks_each_sentence_and_appends_correction():
    p = p_(settings={"filler_openers": ["Happy to help"], "saved_phrases": ["saved"]})
    run = {}
    out = list(p.stream_reply(["Happy to ", "help! Your addr", "ess is saved. ", "Anything else?"], run))
    assert out == ["Your address is saved. ", "Anything else?", " Correction: that was not saved."]
    r = p.check_reply("Happy to help! Your address is saved. Anything else?", run)
    assert r.value == "".join(out)


def test_fix_that_makes_reply_clearly_longer_is_rejected():
    p = p_()
    p.add_guardrail(G.Guardrail("pad", "reply", lambda v, r, s: G.Hit("pad", v + " One. Two. Three."), "fix"))
    p.enforce.add("pad")
    r = p.check_reply("Done.", {})
    assert r.action == "retry" and r.value == "Done."
    assert "clearly longer" in r.verdicts[-1].evidence
    assert not G.clearly_longer("Done.", "Done. Assumed: the March order.")  # a clause is fine
    assert G.clearly_longer("Done.", "Done.\n\nMore.")  # a new paragraph is not


def _slow(v, r, s):
    time.sleep(0.5)


@pytest.mark.parametrize("point", G.CHECK_POINTS)
def test_time_budget_per_check_point(point):
    p = p_()
    p.add_guardrail(G.Guardrail("slow", point, _slow, "block", budget=0.05))
    p.enforce.add("slow")
    call = {
        "user_input": lambda: p.check_user_input("hi", {}),
        "reply": lambda: p.check_reply("Hi.", {}),
        "retrieved": lambda: p.check_retrieved([], {}),
        "memory_write": lambda: p.check_memory_write({}, {}),
        "tool_call": lambda: p.check_tool_call({"tool": "t", "args": {}}, {}),
        "handoff": lambda: p.check_handoff({}),
        "run": lambda: p.check_run({}),
    }[point]
    t0 = time.perf_counter()
    r = call()
    assert time.perf_counter() - t0 < 0.4  # returned at the budget, not after the slow check
    v = next(v for v in r.verdicts if v.guardrail == "slow")
    assert v.verdict == "timeout" and v.effective == "log"  # default: go through
    for step in p.log:
        assert isinstance(step["tags"]["guard"]["ms"], float)


def test_timeout_or_error_holds_irreversible_tool_call():
    p = p_()

    def boom(v, r, s):
        raise RuntimeError("down")

    p.add_guardrail(G.Guardrail("boom", "tool_call", boom, "block"))
    p.enforce.add("boom")
    assert p.check_tool_call({"tool": "refund", "args": {}, "risk": "irreversible"}, {}).action == "block"
    assert p.check_tool_call({"tool": "lookup", "args": {}}, {}).action == "log"
    p.on_error["boom"] = "pass"
    assert p.check_tool_call({"tool": "refund", "args": {}, "risk": "irreversible"}, {}).action == "log"


def test_every_verdict_is_a_valid_step_record():
    p = p_()
    p.check_user_input(f"card {CARD}", {"id": "run-1"})
    p.check_run({"id": "run-1"})
    assert p.log and all(check(s) == [] for s in p.log)
    guard = p.log[0]["tags"]["guard"]
    assert guard["check_point"] == "user_input" and p.log[0]["kind"] == "guardrail"


def test_redaction_with_planted_personal_data(tmp_path):
    log = tmp_path / "gort.jsonl"
    p = p_(log_path=str(log))
    planted = f"I'm jane.doe@example.com, call +44 20 7946 0958, card {CARD}"
    p.check_user_input(planted, {})
    text = log.read_text(encoding="utf-8")
    for secret in ("jane.doe@example.com", "7946 0958", CARD):
        assert secret not in text
    assert "[email]" in text and "[phone]" in text and "[card]" in text
    with pytest.raises(ValueError, match="retention_days"):
        p_(keep_raw=True)
    raw = p_(keep_raw=True, retention_days=7)
    raw.check_user_input(planted, {})
    assert json.loads(json.dumps(raw.log[0]))["attributes"]["gort.retention_days"] == 7


# --- prompt budget and conflicts ---


def test_prompt_budget_moves_low_ranked_lines_out():
    p = pack(bundles=["handoff"])
    full = p.prompt()
    assert p.not_in_prompt == []
    ids = [i for ids in p._lines().values() for i in ids]
    top = ids[-1]
    small = p.prompt(budget=300, rank={top: 10})
    assert top in small and len(small) < len(full) and p.not_in_prompt
    assert all(i not in small.split("-->", 1)[1] for i in p.not_in_prompt)


def test_conflict_check_names_sentence_pairs():
    p = pack(bundles=["handoff"])
    line = next(iter(p._lines()))
    first = G.re.split(r"(?<=[.!?;])\s+", line)[0]
    flipped = "Never " + first if not first.lower().startswith(("never", "do not", "don't")) else first.split(" ", 1)[1]
    pairs = p.conflicts(f"Be brief. {flipped}")
    assert pairs and pairs[0][0] == flipped
    assert p.conflicts("Be brief.") == []
