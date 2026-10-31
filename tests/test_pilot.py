import json
import re
from collections import Counter
from pathlib import Path

from gortguard.packformat import load_entry, validate

ROOT = Path(__file__).parent.parent
PILOT = sorted((ROOT / "packs" / "pilot").glob("*.json"))


def test_pilot_has_50_entries_that_load():
    assert len(PILOT) == 50
    entries = [load_entry(p) for p in PILOT]
    assert all(e["pattern"] == p.stem and e["status"] == "proposed" for e, p in zip(entries, PILOT))
    assert all(any(v.get("over_correct") for v in e["evals"]) for e in entries)


def test_count_page_matches_the_entries():
    kinds = Counter(json.loads(p.read_text(encoding="utf-8"))["guardrail"].get("kind", "none") for p in PILOT)
    page = (ROOT / "docs" / "pilot-count.md").read_text(encoding="utf-8")
    for k in ("rule", "judge", "none"):
        assert re.search(rf"^\| {k} \| {kinds[k]} \|$", page, re.MULTILINE)


def test_guardrail_languages_field():
    entry = json.loads(PILOT[0].read_text(encoding="utf-8"))
    rule = {"kind": "rule", "checks": "reply", "condition": "x", "action": "log", "limits": {}}
    assert validate(dict(entry, guardrail=dict(rule, languages=["en"]))) == []
    assert validate(dict(entry, guardrail=dict(rule, languages=[])))
