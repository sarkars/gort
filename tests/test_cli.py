import json

import pytest

from gortguard import pack as P
from gortguard.cli import main


def test_every_family_in_one_bundle_or_later():
    families = {p["family"] for p in P.PATTERNS}
    placed = [f for b in P.BUNDLES.values() for f in b["families"]] + P.LATER
    assert sorted(placed) == sorted(families)  # each family exactly once


def test_presets_name_real_bundles():
    for p in P.PRESETS.values():
        for b in p["bundles"]:
            assert b in P.BUNDLES


def test_search_transfer_finds_handoff(capsys):
    assert "handoff" in P.search("transfer")[0]
    assert main(["search", "transfer"]) == 0
    assert "handoff" in capsys.readouterr().out


def test_unknown_bundle_is_error(capsys):
    with pytest.raises(ValueError, match="Unknown bundle"):
        P.pack(bundles=["handof"])
    assert main(["build", "--bundles", "handof", "-o", "-"]) == 2
    assert "Did you mean: handoff" in capsys.readouterr().err


def test_alias_resolves():
    assert P.pack(bundles=["escalation"]).bundles == ["handoff"]


def test_support_bot_build_has_only_its_patterns(tmp_path):
    out, chk = tmp_path / "gort-policy.md", tmp_path / "gort-checklist.md"
    assert main(["build", "--preset", "support-bot", "-o", str(out), "--checklist", str(chk)]) == 0
    text, checklist = out.read_text(encoding="utf-8"), chk.read_text(encoding="utf-8")
    fams = {f for b in P.PRESETS["support-bot"]["bundles"] for f in P.BUNDLES[b]["families"]}
    for p in P.PATTERNS:
        ours = p["family"] in fams
        assert (f"{p['id']}]" in text or f"{p['id']}," in text) == (ours and "prompt" in p["place"]), p["id"]
        assert (f"[{p['id']}]" in checklist) == (ours and p["place"] != ["prompt"]), p["id"]
    assert text.splitlines()[1] == P.PRECEDENCE


def test_every_chat_pattern_has_evals(tmp_path):
    chat = [p for p in P.PATTERNS if P.bundle_of(p["family"])]
    assert all(P.EVALS.get(p["id"], {}).get("cases") for p in chat)
    ev = tmp_path / "gort-evals.jsonl"
    args = ["build", "--bundles", "handoff", "-o", str(tmp_path / "p.md"), "--checklist", str(tmp_path / "c.md")]
    assert main([*args, "--evals", str(ev), "--depth", "deep"]) == 0
    cases = [json.loads(ln) for ln in ev.read_text(encoding="utf-8").splitlines()]
    ids = {p["id"] for p in P.bundle_patterns("handoff")}
    assert {c["pattern"] for c in cases} == ids
    assert any(c["counter"] for c in cases)
    first = next(c for c in cases if c["pattern"] == "talk-to-a-human-ignored-or-looped")
    assert first["case"] == "Plain request" and [r["line"] for r in first["rubric"]] == ["R1", "R3"]


def test_eval_depth_and_focus():
    pk = P.pack("support-bot")
    deep, lite = pk.evals("deep"), pk.evals("lite")
    per = {}
    for c in lite:
        per.setdefault(c["pattern"], []).append(c["counter"])
    assert len(lite) < len(deep) and all(sorted(v) in ([False], [False, True]) for v in per.values())
    assert all(c["counter"] for c in pk.evals("deep", ["over-correct"]))
    assert all("ui" in c["place"] for c in pk.evals("lite", ["ui"]))
    assert {c["pattern"] for c in pk.evals("deep", ["escalation"])} == {p["id"] for p in P.bundle_patterns("handoff")}
    assert {c["pattern"] for c in pk.evals("deep", ["cold-transfer"])} == {"cold-transfer"}
    both = pk.evals("deep", ["handoff", "over-correct"])  # different kinds: AND
    assert both and all(c["counter"] and c["pattern"] in {p["id"] for p in P.bundle_patterns("handoff")} for c in both)
    either = pk.evals("deep", ["ui", "code"])  # same kind: OR
    assert {c["pattern"] for c in either} == {p["id"] for p in pk.patterns if {"ui", "code"} & set(p["place"])}
    with pytest.raises(ValueError, match="Unknown focus"):
        pk.evals("lite", ["handof"])
    with pytest.raises(ValueError, match="No eval cases"):
        pk.evals("lite", ["money"])  # money is not in support-bot


def test_widget_rules_stay_out_of_prompt():
    text = P.pack(bundles=["access-and-language"]).policy()
    assert "live region" not in text
    assert all(set(v) <= {"prompt", "code", "ui", "process"} for v in P._PLACE.values())
    assert set(P._PLACE) <= set(P.BY_ID)


def test_exclude_and_constants():
    pk = P.pack(P.Preset.SUPPORT_BOT, exclude=["cold-transfer"])
    assert P.Bundle.UPSET_USERS == "upset-users"
    assert "handoff" in pk.bundles
    assert "cold-transfer" not in pk.policy()
    with pytest.raises(ValueError, match="Unknown pattern"):
        P.pack(bundles=["handoff"], exclude=["no-such-pattern"])
