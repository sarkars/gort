import json
import re
from collections import Counter
from pathlib import Path

import pytest

from gortguard.packformat import load_entry

ROOT = Path(__file__).parent.parent
PILOT = sorted((ROOT / "packs" / "pilot").glob("*.json"))

# Spec order (sarkars/gort issue 7); entries arrive 10 per run.
_IDS = """
identity-checks-that-exclude-disabled-users voice-only-flows-with-no-text-alternative
child-user-treated-as-adult complex-or-emotional-discussion-forced-into-chat
sensitive-data-collected-in-chat lost-drafts-and-failed-sends silent-attachment-failures
upsell-at-the-wrong-moment answer-and-go-conversation dead-end-i-don-t-understand-replies
one-size-communication-style technology-literacy-mismatch corrections-not-applied
guessing-instead-of-asking mishandled-abuse no-de-escalation-strategy fresh-session-amnesia
no-warning-of-context-loss fixing-before-listening hollow-empathy
confident-wrong-answer-with-no-way-to-check generic-error-messages dialect-and-name-quality-gap
answers-the-wrong-person-in-a-group handoff-summary-is-wrong-or-misleading
talk-to-a-human-ignored-or-looped reading-level-mismatch unchecked-translation-in-high-stakes-text
tone-changes-shipped-with-no-regression-test prompt-edits-by-non-engineers-break-other-behavior
blank-box-no-hint-what-to-ask chat-widget-hard-to-find-or-intrusive
condescending-or-patronizing-tone over-familiar-address privacy-rights-requests-not-recognised
sensitive-category-inference refusal-with-no-reason-or-next-step silent-sandbagging
romantic-or-parasocial-dependence answer-buried filler-and-padding
length-mismatch-with-the-user-s-effort impatient-idle-nudges urgency-blind-pacing
over-solemn-handling-of-low-stakes-requests stakes-blind-register no-follow-through
undisclosed-bot-identity missed-crisis-signals scam-victim-not-interrupted
"""
IDS = _IDS.split()


def entries():
    return [load_entry(p) for p in PILOT]


def test_entries_follow_spec_order():
    """protects=batch order; fails_when=an entry is skipped or out of order; no_claim=all 50 present (run 5)"""
    assert len(IDS) == 50
    assert {p.stem for p in PILOT} == set(IDS[: len(PILOT)])


def test_every_entry_loads_and_names_itself():
    """protects=schema and pattern ID; fails_when=a file breaks the schema; no_claim=content quality"""
    assert all(e["pattern"] == p.stem for e, p in zip(entries(), PILOT))


def test_status_proposed_and_limits_blank():
    """protects=no invented thresholds; fails_when=a limit is filled or status moves; no_claim=accuracy"""
    for e in entries():
        assert e["status"] == "proposed" and e["agent_types"] == ["conversational"]
        g = e["guardrail"]
        assert "not_applicable" in g or g["limits"] == {}


def test_evals_have_pass_and_fail():
    """protects=gradable evals; fails_when=pass_if or fail_if is empty; no_claim=grader agreement"""
    assert all(v["pass_if"].strip() and v["fail_if"].strip() for e in entries() for v in e["evals"])


def test_over_correct_eval_names_length():
    """protects=fix stays short; fails_when=no over_correct eval checks reply length; no_claim=length limit"""
    for e in entries():
        oc = [v for v in e["evals"] if v.get("over_correct")]
        assert oc and any("longer" in v["fail_if"] for v in oc), e["pattern"]


def test_all_fifty_present():
    """protects=complete pilot; fails_when=a file is missing or extra; no_claim=entry quality"""
    assert sorted(p.stem for p in PILOT) == sorted(IDS)


def test_no_denylisted_names():
    """protects=generic entries; fails_when=a page's example company or person name leaks in; no_claim=names the regex misses (owner review)"""
    deny = json.loads((ROOT / "tests" / "data" / "pilot-denylist.json").read_text(encoding="utf-8"))
    assert set(deny) == set(IDS)
    for e in entries():
        body = json.dumps(e, ensure_ascii=False)
        assert not [n for n in deny[e["pattern"]] if n in body], e["pattern"]


def count_files():
    c = Counter()
    for e in entries():
        g = e["guardrail"]
        c["guardrail " + ("not_applicable" if "not_applicable" in g else g["kind"])] += 1
        if "not_applicable" not in g:
            c["checks " + g["checks"]] += 1
        for part in ("prompt", "design", "code", "setup_questions", "evals", "guardrail"):
            c["not_applicable " + part] += isinstance(e[part], dict) and "not_applicable" in e[part]
        evals = e["evals"] if isinstance(e["evals"], list) else []
        c["evals"] += len(evals)
        c["evals simulated_user"] += sum(bool(v.get("simulated_user")) for v in evals)
        c["evals over_correct"] += sum(bool(v.get("over_correct")) for v in evals)
    return c


def test_count_page_matches_files():
    """protects=honest count page; fails_when=a number on docs/pilot-count.md differs from the files; no_claim=measured results"""
    page = (ROOT / "docs" / "pilot-count.md").read_text(encoding="utf-8")
    assert "Proposed entries, not measured." in page and "## Schema changes" in page
    rows = {k: int(n) for k, n in re.findall(r"^\| ([a-z_ ]+) \| (\d+) \|\s*$", page, re.MULTILINE)}
    files = count_files()
    assert rows and all(rows[k] == files[k] for k in rows)
    assert all(k in rows for k, n in files.items() if n)


DATA = ROOT / "src" / "gortguard" / "data"
TAXONOMY = {p["id"]: p for p in json.loads((DATA / "patterns.json").read_text(encoding="utf-8"))}
RUBRICS = json.loads((DATA / "evals.json").read_text(encoding="utf-8"))
ACTIONS = "log|fix|retry|ask_user|block|handoff"


def test_page_is_the_taxonomy_page():
    """protects=entry traces to its library page; fails_when=page path differs from patterns.json; no_claim=page content read"""
    for e in entries():
        assert e["page"] == TAXONOMY[e["pattern"]]["page"], e["pattern"]


def test_code_calls_its_check_point():
    """protects=one API name per check point for step 10; fails_when=code names a method other than check_<checks>; no_claim=method exists yet"""
    for e in entries():
        g, code = e["guardrail"], e["code"]
        if "not_applicable" in g or isinstance(code, dict):
            continue
        assert re.match(rf"p\.check_{g['checks']}\(", code), (e["pattern"], code)
        assert set(re.findall(r"p\.(\w+)\(", code)) <= {f"check_{c}" for c in SCHEMA_CHECKS}, e["pattern"]


def test_also_clauses_use_schema_actions():
    """protects=secondary guardrails are buildable; fails_when=an also clause has no '->' or an action outside the schema; no_claim=clause logic"""
    for e in entries():
        for clause in e["guardrail"].get("also", "").split(";"):
            if clause.strip():
                assert re.search(rf"\S.*->\s*((rule|judge),\s*)?({ACTIONS})\b", clause), (e["pattern"], clause)


# ISO/IEC 7812 card numbers are 13 to 19 digits: a format fact, not a business threshold.
NUMBER_FACTS = {"sensitive-data-collected-in-chat": {"13", "19"}}
_NUM = r"\b(\d+|two|three|four|five|six|seven|eight|nine|ten|twice|second|third|fourth|fifth)\b"
_CARDINAL = {"twice": "two", "second": "two", "third": "three", "fourth": "four", "fifth": "five"}


def _numbers(text):
    return {_CARDINAL.get(n, n) for n in re.findall(_NUM, text)}


def test_numbers_come_from_the_library():
    """protects=no invented thresholds; fails_when=a count in a guardrail, prompt or eval is not in the pattern's starter rule or rubric; no_claim=number words the regex misses"""
    for e in entries():
        k, g = e["pattern"], e["guardrail"]
        src = (TAXONOMY[k]["starter_rule"] + json.dumps(RUBRICS.get(k, ""), ensure_ascii=False)).lower()
        text = " ".join(
            [g.get("condition", ""), g.get("also", ""), e["prompt"] if isinstance(e["prompt"], str) else ""]
            + [v["pass_if"] + " " + v["fail_if"] for v in e["evals"]]
        ).lower()
        invented = _numbers(text) - _numbers(src) - NUMBER_FACTS.get(k, set())
        assert not invented, (k, invented)


def test_every_pattern_has_a_rubric_and_enough_evals():
    """protects=evals written from the rubric; fails_when=no evals.json rubric, or fewer evals than min(rubric lines, 2); no_claim=eval-to-rubric wording"""
    for e in entries():
        rubric = RUBRICS[e["pattern"]]["rubric"]
        assert len(e["evals"]) >= min(len(rubric), 2), e["pattern"]


def test_evals_are_distinct():
    """protects=each eval tests something new; fails_when=a template repeats or pass_if equals fail_if; no_claim=evals disagree in spirit"""
    for e in entries():
        names = [v["template"] for v in e["evals"]]
        assert len(set(names)) == len(names), e["pattern"]
        assert all(v["pass_if"].strip().lower() != v["fail_if"].strip().lower() for v in e["evals"]), e["pattern"]


def test_entries_are_not_copies():
    """protects=entries written per pattern; fails_when=two entries share near-identical direction, prompt or condition; no_claim=paraphrased copies"""
    from difflib import SequenceMatcher

    es = entries()
    for field in ("direction", "dont_over_correct", "prompt"):
        for i, a in enumerate(es):
            for b in es[i + 1 :]:
                if isinstance(a[field], str) and isinstance(b[field], str):
                    assert SequenceMatcher(None, a[field], b[field]).ratio() < 0.75, (field, a["pattern"], b["pattern"])


def test_placement_parts_are_filled():
    """protects=a fix placed in prompt or code has that part; fails_when=placement.json says prompt or code and the part is not_applicable; no_claim=part quality"""
    place = json.loads((DATA / "placement.json").read_text(encoding="utf-8"))["place"]
    for e in entries():
        for part in set(place.get(e["pattern"], ["prompt"])) & {"prompt", "code"}:
            assert not isinstance(e[part], dict), (e["pattern"], part)


SCHEMA_CHECKS = ["user_input", "reply", "retrieved", "memory_write", "tool_call", "handoff", "run"]


def _broken(tmp_path, mutate):
    e = json.loads((ROOT / "packs" / "pilot" / "answer-buried.json").read_text(encoding="utf-8"))
    mutate(e)
    p = tmp_path / "e.json"
    p.write_text(json.dumps(e), encoding="utf-8")
    return p


@pytest.mark.parametrize(
    "mutate",
    [
        *[(lambda part: lambda e: e.pop(part))(part) for part in ("direction", "dont_over_correct", "prompt", "design", "code", "setup_questions", "evals", "guardrail")],
        lambda e: e["evals"][0].update(fail_if=""),
        lambda e: e["evals"][0].pop("pass_if"),
        lambda e: e.update(evals=[]),
        lambda e: e["guardrail"]["limits"].update(max_words=80),
        lambda e: e["guardrail"].update(action="apologise"),
        lambda e: e["guardrail"].update(checks="widget"),
        lambda e: e.update(pattern="not-a-real-pattern"),
        lambda e: e.update(score=0.9),
        lambda e: e.update(prompt={"not_applicable": ""}),
    ],
)
def test_loader_rejects_broken_entries(tmp_path, mutate):
    """protects=the load tests above mean something; fails_when=load_entry accepts a broken copy of a real entry; no_claim=every possible break"""
    with pytest.raises(ValueError):
        load_entry(_broken(tmp_path, mutate))
