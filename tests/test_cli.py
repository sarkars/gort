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
    out = tmp_path / "gort-policy.md"
    assert main(["build", "--preset", "support-bot", "-o", str(out)]) == 0
    text = out.read_text(encoding="utf-8")
    fams = {f for b in P.PRESETS["support-bot"]["bundles"] for f in P.BUNDLES[b]["families"]}
    for p in P.PATTERNS:
        assert (p["id"] in text) == (p["family"] in fams), p["id"]
    assert text.splitlines()[1] == P.PRECEDENCE


def test_exclude_and_constants():
    pk = P.pack(P.Preset.SUPPORT_BOT, exclude=["cold-transfer"])
    assert P.Bundle.UPSET_USERS == "upset-users"
    assert "handoff" in pk.bundles
    assert "cold-transfer" not in pk.policy()
    with pytest.raises(ValueError, match="Unknown pattern"):
        P.pack(bundles=["handoff"], exclude=["no-such-pattern"])
