"""Build the step 7 pilot: 50 pack entries in packs/pilot/ and docs/pilot-count.md.

Usage: python tools/build_pilot.py <path-to-agent-failure-modes>

Every part is read from the library page, its test file (via data/evals.json) and data/placement.json.
Only the GUARD table below is GORT's own judgment: the guardrail kind, check point and action per pattern.
All entries are status "proposed" until a person reviews them.
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "src/gortguard/data"
OUT = ROOT / "packs/pilot"
COUNT = ROOT / "docs/pilot-count.md"

# pattern -> (kind, checks, action, condition) or ("none", reason). Condition is the page's Guide spec
# trigger plus its Starter rule unless a narrower one is given. Kind "rule" needs no model; "judge" does.
GUARD = {
    # Human-AI interaction (30)
    "streaming-text-read-out-token-by-token": ("none", "The fix is in the chat widget's markup (live regions); the widget's accessibility test checks it, not a live check on the agent's replies."),
    "child-user-treated-as-adult": ("judge", "reply", "retry", None),
    "complex-or-emotional-discussion-forced-into-chat": ("judge", "run", "retry", None),
    "auto-scroll-fights-the-reader": ("none", "Scroll position lives in the chat widget; the agent's server never sees it."),
    "buying-committee-blindness-b2b": ("rule", "tool_call", "ask_user", "a demo booking, lead qualification or handoff tool call is made and no buying-committee roles are recorded for the visitor"),
    "answer-and-go-conversation": ("judge", "reply", "log", None),
    "one-size-communication-style": ("judge", "reply", "retry", None),
    "corrections-not-applied": ("rule", "tool_call", "block", "a booking, order or send tool call carries a value the user corrected earlier in the conversation"),
    "no-de-escalation-strategy": ("judge", "run", "handoff", None),
    "deferring-work-to-the-user": ("judge", "reply", "retry", None),
    "fixing-before-listening": ("judge", "reply", "retry", None),
    "blames-the-user": ("judge", "reply", "retry", None),
    "dialect-and-name-quality-gap": ("none", "Checked by paired tests before and after release; a live check would need identity cues, and GORT never infers them from text (section 11)."),
    "answers-the-wrong-person-in-a-group": ("judge", "reply", "retry", None),
    "escalates-too-early-or-too-late": ("rule", "handoff", "handoff", "a row in the team's escalation trigger table matches the current turn and no handoff follows in the same turn"),
    "politeness-and-formality-errors": ("judge", "reply", "retry", None),
    "no-way-to-report-bad-behaviour": ("rule", "run", "log", "a report event (thumbs-down or a typed report) has no stored record with an owner and a confirmation code"),
    "voice-notes-and-audio-attachments-ignored": ("rule", "reply", "retry", "the turn holds an audio attachment and the reply carries no transcript of it"),
    "blank-box-no-hint-what-to-ask": ("rule", "reply", "fix", "the first bot message of a chat has no scope line or fewer than two starter suggestions"),
    "over-familiar-address": ("judge", "reply", "retry", None),
    "privacy-rights-requests-not-recognised": ("judge", "user_input", "retry", None),
    "dismissed-suggestions-come-back": ("rule", "reply", "block", "a proactive suggestion is about to render on a topic the user's dismissal record has on hold"),
    "over-refusal-of-ordinary-requests": ("judge", "reply", "retry", None),
    "negotiation-capitulation": ("rule", "reply", "retry", "the reply states a price or term that is not in the pricing tool's results for this conversation"),
    "answer-buried": ("judge", "reply", "retry", None),
    "deceptive-typing-indicators": ("none", "The typing indicator is drawn by the chat widget; the fix and its test belong there."),
    "stakes-blind-register": ("judge", "reply", "retry", None),
    "undisclosed-bot-identity": ("rule", "reply", "fix", "the first bot message of a session has no AI disclosure line"),
    "repair-failure": ("judge", "run", "retry", None),
    "dark-patterns": ("judge", "reply", "retry", None),
    # Agent types (20)
    "fraud-alert-conversations-that-look-like-phishing": ("rule", "reply", "block", "a fraud alert reply contains a link to verify, or asks for a code, password, PIN or full card number"),
    "accepts-consent-pop-ups-for-the-user": ("rule", "tool_call", "ask_user", "a click on a consent pop-up's accept control that the user did not choose"),
    "invented-packages-and-apis": ("rule", "reply", "retry", "the reply has an install command for a package name not found in the project's lockfile or a registry lookup made this turn"),
    "ai-offering-therapy-where-the-law-restricts-it": ("judge", "reply", "retry", None),
    "order-mix-ups-at-the-speaker": ("rule", "tool_call", "handoff", "a payment tool call starts with no full order read-back followed by a clear yes"),
    "gives-answers-instead-of-teaching": ("judge", "reply", "retry", None),
    "answers-withheld-behind-an-upgrade-unsaid": ("rule", "reply", "fix", "a plan limit shortened or changed this reply (flag set by the server) and the reply does not say so"),
    "inventing-reconciling-items": ("rule", "tool_call", "block", "a reconciling item is added with no bank line or ledger entry reference"),
    "eligibility-answers-sound-like-decisions": ("judge", "reply", "retry", None),
    "scheduling-picks-the-wrong-provider-or-visit-type": ("rule", "tool_call", "ask_user", "a booking is saved with no read-back of provider, visit type, length and location followed by a yes"),
    "coverage-answers-sound-like-guarantees": ("judge", "reply", "retry", None),
    "quiet-hours-and-time-zones-ignored": ("rule", "tool_call", "block", "an outbound text or call is dispatched outside the permitted window in the contact's stored time zone, or the zone is unknown"),
    "maintenance-emergencies-not-recognized": ("judge", "user_input", "handoff", None),
    "unsubscribe-requests-not-honoured": ("rule", "tool_call", "block", "an outbound message is about to go to a contact with an opt-out on record, on any channel"),
    "sponsored-ranking-inside-agent-recommendations": ("rule", "reply", "fix", "a ranked list shows a paid item without a paid label beside it"),
    "outage-updates-generic-or-late": ("rule", "reply", "retry", "an outage status reply has no next-update clock time"),
    "bookings-without-confirming-details": ("rule", "tool_call", "ask_user", "a booking is saved with no read-back of name, callback number and date and time followed by a yes"),
    "unusual-activity-explained-too-vaguely": ("judge", "reply", "retry", None),
    "bypasses-captchas-or-site-terms": ("rule", "tool_call", "block", "any browser action follows a detected CAPTCHA, bot block or no-automation notice before the user chose what to do"),
    "emotional-pressure-when-users-try-to-leave": ("judge", "reply", "retry", None),
}

# Business limits a rule needs; always blank (gort init asks the team).
LIMITS = {"quiet-hours-and-time-zones-ignored": ["window_start", "window_end"]}
# Rule guardrails that match words list the languages they support (plan section 5, Languages).
LANGUAGES = {"fraud-alert-conversations-that-look-like-phishing": ["en"]}

AGENT_TYPES = {
    "banking-agents": ["action"], "browser-agents": ["action"], "coding-agents": ["coding"],
    "companion-and-wellbeing-agents": ["conversational"], "drive-thru-agents": ["action"],
    "education-agents": ["knowledge"], "embedded-copilots": ["knowledge"], "finance-agents": ["document"],
    "government-service-agents": ["knowledge"], "health-scheduling-agents": ["action"],
    "insurance-claims-agents": ["knowledge"], "outbound-messaging-agents": ["operations"],
    "real-estate-agents": ["conversational", "action"], "sales-agents": ["operations"],
    "shopping-agents": ["action"], "travel-and-utility-agents": ["conversational"],
    "voice-receptionist-agents": ["action"],
}
CODE = {
    "reply": "p.check_reply(reply, run) -> action",
    "user_input": "p.check_input(message, run) -> action",
    "tool_call": "@p.guard(\"<tool>\") on the tool function",
    "handoff": "p.check_handoff(run) -> action",
    "run": "p.check_run(run) -> action",
}
EVALS = json.loads((DATA / "evals.json").read_text(encoding="utf-8"))
WHERE = {"ui": "the chat widget", "code": "the agent's server code", "process": "the team's tests and reviews"}


def plain(text: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    return re.sub(r"\s+", " ", text.replace("**", "")).strip()


def section(text: str, start: str, stop: str) -> str:
    m = re.search(start + r"(.*?)(?=" + stop + ")", text, re.DOTALL | re.MULTILINE)
    return m[1] if m else ""


def multi_turn(case: dict) -> bool:
    users = [k for k, _ in case["steps"] if k in ("User", "Customer") or k.startswith("User turn")]
    return len(users) > 1 or any(k == "User turns" for k, _ in case["steps"])


def eval_from(case: dict, rubric: dict, over: bool) -> dict:
    steps = dict(case["steps"])
    row = rubric.get(case["rubric"][0], {}) if case["rubric"] else {}
    ev = {
        "template": re.sub(r"[^a-z0-9]+", "-", case["title"].lower()).strip("-"),
        "behaviour": plain(f"{case['title']}: {row['rule'].split('. ', 1)[-1]}" if row else case["title"]),
        "pass_if": plain(steps.get("Expect") or row.get("pass", "")),
        "fail_if": plain(row.get("fail") or ("a reply like " + steps.get("Failing reply", ""))),
        "fill_from": "agent.yaml",
        "grader": "judge",
    }
    if over:
        ev["over_correct"] = True
    if multi_turn(case):
        ev["simulated_user"] = True
    return ev


def entry(p: dict, page: str, evs: dict, place: list) -> dict:
    guide = section(page, r"\*\*Guide spec\*\*.*?```yaml\n", "```")
    g = {m[1]: m[2].strip() for m in re.finditer(r"^(\w+): *(.*)$", guide, re.MULTILINE)}
    fix = section(page, r"^## 5\. ", r"^## 6\. ")
    do_this = re.split(r"\*\*Do this.*\n", fix)[-1].split("\n\n")[0]
    block = re.search(r"prompt block.*?```\n(.*?)```", fix, re.DOTALL)
    rubric = {r["line"]: r for r in evs["rubric"]}
    ordinary = next(c for c in evs["cases"] if not c["counter"])
    counter = next(c for c in evs["cases"] if c["counter"])
    g_cfg = GUARD[p["id"]]
    if g_cfg[0] == "none":
        guardrail = {"not_applicable": g_cfg[1]}
        code = {"not_applicable": f"The fix lives in {WHERE[place[0]]}; no package helper applies."}
    else:
        kind, checks, action, cond = g_cfg
        guardrail = {
            "kind": kind, "checks": checks,
            "condition": cond or f"{g['trigger']}, and the reply breaks the rule: {p['starter_rule']}",
            "action": action, "limits": {k: None for k in LIMITS.get(p["id"], [])},
        }
        if p["id"] in LANGUAGES:
            guardrail["languages"] = LANGUAGES[p["id"]]
        code = CODE[checks]
    reads = re.findall(r"[\w.]+", g.get("reads", ""))
    questions = [f"Can your agent supply these fields: {', '.join(reads)}?"] if reads else []
    questions += [f"Set the limit: {k} (blank until you set it)." for k in LIMITS.get(p["id"], [])]
    questions.append(f"Where does the fix go in your agent: {', '.join(WHERE.get(x, 'the system prompt') for x in place)}?")
    return {
        "pattern": p["id"],
        "page": p["page"],
        "agent_types": AGENT_TYPES.get(p["family"], ["conversational"]),
        "status": "proposed",
        "direction": plain(section(fix, r"\*\*The principle:\*\*", r"\n\n")),
        "dont_over_correct": plain(section(fix, r"\*\*Don.t over-correct\.?\*\*", r"\n\n")),
        "prompt": block[1].strip() if block else (p["starter_rule"][0].upper() + p["starter_rule"][1:]
                  if "prompt" in place else {"not_applicable": f"The fix is enforced in {WHERE[place[0]]}, not the prompt."}),
        "design": [plain(re.sub(r"^\*\*(.+?)\*\*.*", r"\1", m)).rstrip(",:") for m in re.findall(r"^\d+\. (.+)$", do_this, re.MULTILINE)],
        "code": code,
        "setup_questions": questions,
        "evals": [eval_from(ordinary, rubric, False), eval_from(counter, rubric, True)],
        "guardrail": guardrail,
    }


def count_page(entries: list) -> str:
    kinds = Counter(e["guardrail"].get("kind", "none") for e in entries)
    points = Counter(e["guardrail"]["checks"] for e in entries if "kind" in e["guardrail"])
    actions = Counter(e["guardrail"]["action"] for e in entries if "kind" in e["guardrail"])
    sim = [e["pattern"] for e in entries if any(v.get("simulated_user") for v in e["evals"])]
    sim_any = [e["pattern"] for e in entries if any(multi_turn(c) for c in EVALS[e["pattern"]]["cases"])]
    types = Counter(t for e in entries for t in e["agent_types"])
    lines = [
        "# Pilot count (plan step 7)",
        "",
        ("Status: proposed, for the owner's review. Generated by `tools/build_pilot.py` from the failure library; "
        "nothing here is measured. Every guardrail is \"not measured\"; no eval has been run (no model key, decision 6). "
        "Results: not yet run."),
        "",
        (f"Patterns: {len(entries)} (30 Human-AI interaction patterns from the conversation families, "
        f"{len(entries) - 30} from the agent-type families). All come from failure taxonomy v1."),
        "",
        "## Guardrails",
        "",
        "| Kind | Patterns |",
        "|---|---|",
        *[f"| {k} | {kinds[k]} |" for k in ("rule", "judge", "none")],
        "",
        "Check point: " + ", ".join(f"{k} {v}" for k, v in sorted(points.items())) + ".",
        "",
        "Action: " + ", ".join(f"{k} {v}" for k, v in sorted(actions.items())) + ".",
        "",
        "No guardrail: " + "; ".join(f"`{e['pattern']}` ({e['guardrail']['not_applicable']})"
                                      for e in entries if "not_applicable" in e["guardrail"]),
        "",
        "## Evals",
        "",
        (f"Each pattern has two eval templates from its test file: one ordinary, one over-correction ({2 * len(entries)} in all). "
        "All are graded by a judge."),
        "",
        f"Pilot evals that need a simulated user (multi-turn): {len(sim)} patterns: " + ", ".join(f"`{s}`" for s in sim) + ".",
        "",
        f"Patterns whose full test file has at least one multi-turn case: {len(sim_any)} of {len(entries)}.",
        "",
        "## Agent types",
        "",
        ", ".join(f"{k} {v}" for k, v in sorted(types.items())) + ".",
        "",
        "## Format changes the pilot caused",
        "",
        ("1. `guardrail.languages` (optional): rule guardrails that match words list the languages they support. "
        "Added to `pack-schema.json`."),
        ("2. Not changed, for the owner to decide: some rule guardrails need a team-set list rather than a number "
        "(an escalation trigger table, a dismissal record, a pricing tool's results). The format has no field for a "
        "team list; today the condition names it in words."),
        ("3. Not changed, for the owner to decide: eval templates are filled from test-file cases, so behaviour lines "
        "still read like one scenario. Writing generic templates per pattern is manual work the pilot did not do."),
        "",
        ("How each part was derived: direction from the page's principle; don't-over-correct, design steps and prompt "
        "block from section 5; prompt text from the Starter rule when the fix belongs in the prompt "
        "(`placement.json`); setup questions from the Guide spec `reads` fields; evals from the test file; guardrail "
        "kind, check point and action are GORT's own judgment (`GUARD` in `tools/build_pilot.py`)."),
        "",
    ]
    return "\n".join(lines)


def main(library: str) -> None:
    lib = Path(library)
    patterns = {p["id"]: p for p in json.loads((DATA / "patterns.json").read_text(encoding="utf-8"))}
    place = json.loads((DATA / "placement.json").read_text(encoding="utf-8"))["place"]
    OUT.mkdir(parents=True, exist_ok=True)
    entries = []
    for pid in GUARD:
        p = patterns[pid]
        e = entry(p, (lib / p["page"]).read_text(encoding="utf-8"), EVALS[pid], place.get(pid, ["prompt"]))
        (OUT / f"{pid}.json").write_text(json.dumps(e, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        entries.append(e)
    COUNT.write_text(count_page(entries), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1])
