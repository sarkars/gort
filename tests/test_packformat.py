import copy
import json
from pathlib import Path

import pytest

from gortguard.packformat import load_entry, validate

EXAMPLES = sorted((Path(__file__).parent.parent / "examples" / "packs").glob("*.json"))
GOOD = json.loads(EXAMPLES[0].read_text(encoding="utf-8"))


def test_both_examples_load():
    assert len(EXAMPLES) == 2
    for path in EXAMPLES:
        assert load_entry(path)["pattern"] == path.stem


def _bad(**change):
    entry = copy.deepcopy(GOOD)
    for k, v in change.items():
        if v is None:
            entry.pop(k)
        else:
            entry[k] = v
    return validate(entry)


def test_missing_part_fails():
    assert "$: missing guardrail" in _bad(guardrail=None)


def test_part_may_say_why_it_does_not_apply():
    assert _bad(code={"not_applicable": "no helper needed"}) == []
    assert _bad(code={"not_applicable": ""})


def test_eval_needs_pass_and_fail():
    ev = copy.deepcopy(GOOD["evals"])
    del ev[0]["fail_if"]
    assert any("fail_if" in e for e in _bad(evals=ev))


def test_limits_stay_blank():
    g = dict(GOOD["guardrail"], limits={"amount": 500})
    assert _bad(guardrail=g)
    assert _bad(guardrail=dict(GOOD["guardrail"], limits={"amount": None})) == []


def test_no_framework_mapping():
    assert any("maps_to" in e for e in _bad(maps_to={"nist_600_1": ["x"]}))


def test_unknown_pattern_id_is_error(tmp_path):
    f = tmp_path / "x.json"
    f.write_text(json.dumps(dict(GOOD, pattern="not-a-pattern")), encoding="utf-8")
    with pytest.raises(ValueError, match="not a Pattern ID"):
        load_entry(f)
