from pathlib import Path

from gortguard.packformat import load_entry

ROOT = Path(__file__).parent.parent
PILOT = sorted((ROOT / "packs" / "pilot").glob("*.json"))

# Spec order (sarkars/gort issue 7); entries arrive 10 per run.
IDS = """
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
""".split()


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
