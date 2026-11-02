"""Live guardrails (plan step 10). Nothing here is measured: no hit rate, no accuracy, no false-alarm rate.

A guardrail checks one check point and returns a Hit or None. The runner adds the time budget, the fail
policy on a timeout or error, log-only mode and redaction, and writes every verdict as a Step record
(kind "guardrail") with its Guard tags. Lists, limits and time budgets are blank until the team sets them.

`run` is a plain dict the team keeps per conversation. Keys the built-in guardrails read:
id, data_source, today (YYYY-MM-DD), steps ([{kind, label, ok}], kinds as in record-schema.json),
message_ids, slots, prompt_version, model_version, eval_run_id.
"""

import functools
import inspect
import json
import re
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone

CHECK_POINTS = ("user_input", "reply", "retrieved", "memory_write", "tool_call", "handoff", "run")
ORDER = ("block", "handoff", "ask_user", "retry", "fix", "log", "ok")  # most severe first
HOLDS = ("block", "handoff", "ask_user")  # @p.guard does not run the tool on these

SETTINGS = {
    "filler_openers": [],  # praise or announcement openers to drop; the team sets the list
    "saved_phrases": [],  # words that claim something was saved; the team sets the list
    "not_saved_note": "Correction: that was not saved.",
}


@dataclass
class Hit:
    evidence: str
    fixed: object = None  # the fixed value, used when the action is "fix"


@dataclass
class Guardrail:
    name: str
    checks: str
    fn: object  # fn(value, run, settings) -> Hit | None
    action: str
    pattern: str | None = None
    kind: str = "rule"
    mode: str = "end"  # reply only: "chunk" runs on each streamed sentence, "end" on the whole reply
    on_error: str | None = None  # "pass" or "hold"; None: hold for irreversible tool calls, else pass
    budget: float | None = None  # seconds; None means no time budget until the team sets one


@dataclass
class Verdict:
    guardrail: str
    verdict: str  # hit, pass, timeout, error
    action: str  # what the guardrail asks for
    effective: str  # what happens: "log" in log-only mode
    evidence: str


@dataclass
class Result:
    value: object
    action: str
    verdicts: list


class Held(Exception):
    """Raised by @p.guard when a tool call is blocked, handed off or needs the user. The tool did not run."""

    def __init__(self, result):
        super().__init__(f"tool call held: {result.action}")
        self.result = result


# --- redaction -------------------------------------------------------------------------------

_CARD = re.compile(r"\b(?:\d[ -]?){12,18}\d\b")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PHONE = re.compile(r"\+?\d[\d ().-]{7,}\d")


def luhn(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch) * (2 if i % 2 else 1)
        total += d - 9 if d > 9 else d
    return total % 10 == 0


def mask_cards(text: str) -> str:
    def sub(m):
        digits = re.sub(r"\D", "", m.group())
        return "[card]" if 13 <= len(digits) <= 19 and luhn(digits) else m.group()

    return _CARD.sub(sub, text)


def redact(text: str) -> str:
    """Mask emails, card numbers and phone numbers. English formats only; other personal data needs the team's list."""
    # ponytail: regex masks, not a PII model; add the team's own patterns before logging free text
    return _PHONE.sub("[phone]", mask_cards(_EMAIL.sub("[email]", text)))


# --- built-in rule guardrails, one per check point, from the pilot pack entries -------------------


def _card(msg, run, s):
    fixed = mask_cards(msg["text"])
    if fixed != msg["text"]:
        return Hit(msg["text"], {**msg, "text": fixed})


def _resent(msg, run, s):
    if msg.get("id") is not None and msg["id"] in run.get("message_ids", ()):
        return Hit(f"client message ID {msg['id']} is already stored")


def _filler(unit, run, s):
    first = unit["sentence"].strip().lower()
    if unit["index"] == 0 and any(first.startswith(p.lower()) for p in s["filler_openers"]):
        return Hit(unit["sentence"].strip(), {**unit, "sentence": ""})


def _saved(reply, run, s):
    claims = [p for p in s["saved_phrases"] if p.lower() in reply.lower()]
    wrote = any(st.get("kind") == "memory_write" and st.get("ok") for st in run.get("steps", ()))
    if claims and not wrote:
        sep = "" if reply[-1:].isspace() else " "
        return Hit(f"says {claims[0]!r} with no successful write", reply + sep + s["not_saved_note"])


def _stale(docs, run, s):
    today = run.get("today") or date.today().isoformat()
    stale = [d for d in docs if d.get("refresh_by") and d["refresh_by"] < today]
    if stale:
        ids = ", ".join(str(d.get("id")) for d in stale)
        return Hit(f"past refresh date: {ids}", [d for d in docs if d not in stale])


def _unapproved(write, run, s):
    if write.get("kind") == "summary" and not write.get("approved"):
        return Hit("summary saved for later with no approval event")


def _stale_slot(call, run, s):
    slots = run.get("slots", {})
    diff = [k for k, v in call["args"].items() if k in slots and slots[k] != v]
    if diff:
        return Hit(f"{call['tool']}: {', '.join(diff)} differs from the current value")


def _limit(call, run, s):
    over = [k for k, cap in (call.get("limit") or {}).items()
            if cap is not None and k in call["args"] and call["args"][k] > cap]
    if over:
        return Hit(f"{call['tool']}: {', '.join(over)} over the team's limit")


def _person(value, run, s):
    steps = run.get("steps", [])
    for i, st in enumerate(steps):
        if st.get("kind") == "user_message" and st.get("label") == "human":
            bot_turns = 0
            for later in steps[i + 1:]:
                if later.get("kind") == "handoff":
                    break
                bot_turns += later.get("kind") == "bot_reply"
            else:
                if bot_turns >= 2:  # "within two bot turns", from the pattern
                    return Hit(f"request for a person at step {i}, no transfer after {bot_turns} bot turns")


def _untested(value, run, s):
    if (run.get("prompt_version") or run.get("model_version")) and not run.get("eval_run_id"):
        return Hit("prompt or model version with no linked eval run ID")


BUILT_IN = [
    Guardrail("card-number", "user_input", _card, "fix", "sensitive-data-collected-in-chat"),
    Guardrail("resent-message", "user_input", _resent, "block", "lost-drafts-and-failed-sends"),
    Guardrail("filler-opener", "reply", _filler, "fix", "filler-and-padding", mode="chunk"),
    Guardrail("saved-without-write", "reply", _saved, "fix", "no-warning-of-context-loss"),
    Guardrail("stale-source", "retrieved", _stale, "fix", "confident-wrong-answer-with-no-way-to-check"),
    Guardrail("unapproved-summary", "memory_write", _unapproved, "block", "fresh-session-amnesia"),
    Guardrail("stale-slot", "tool_call", _stale_slot, "block", "corrections-not-applied"),
    Guardrail("over-limit", "tool_call", _limit, "handoff"),
    Guardrail("person-not-reached", "handoff", _person, "handoff", "talk-to-a-human-ignored-or-looped"),
    Guardrail("untested-version", "run", _untested, "log", "tone-changes-shipped-with-no-regression-test"),
]


# --- runner ----------------------------------------------------------------------------------


def _timed(g, value, run, settings, budget):
    """(hit, verdict). A timed-out check keeps running in its thread; Python cannot stop it."""
    box = {}

    def target():
        try:
            box["hit"] = g.fn(value, run, settings)
        except Exception as e:  # noqa: BLE001 - any guardrail error goes to the fail policy
            box["error"] = e

    t = threading.Thread(target=target, daemon=True)
    t.start()
    t.join(budget)
    if t.is_alive():
        return None, "timeout"
    if "error" in box:
        return None, "error"
    return box["hit"], "hit" if box["hit"] else "pass"


def _text(v):
    return v["sentence"] if isinstance(v, dict) and "sentence" in v else v if isinstance(v, str) else ""


def _sentences(text):
    return len([s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s])


def clearly_longer(before: str, after: str) -> bool:
    """A fix adds a clause, not a paragraph (owner, 2026-10-31): more than one new sentence or a new paragraph."""
    return _sentences(after) > _sentences(before) + 1 or after.count("\n\n") > before.count("\n\n")


_SENTENCE = re.compile(r"(.*?[.!?\n])(\s+)", re.DOTALL)


class Guards:
    def __init__(self, pattern_ids, enforce=(), budgets=None, on_error=None, log_path=None,
                 keep_raw=False, retention_days=None, settings=None):
        if keep_raw and not retention_days:
            raise ValueError("keep_raw needs retention_days: raw text is kept only for a set period.")
        self.guardrails = [g for g in BUILT_IN if g.pattern is None or g.pattern in pattern_ids]
        self.enforce = set(enforce)  # every guardrail starts in log-only mode
        self.budgets = dict(budgets or {})
        self.on_error = dict(on_error or {})
        self.log_path, self.keep_raw, self.retention_days = log_path, keep_raw, retention_days
        self.settings = {**SETTINGS, **(settings or {})}
        self.log: list[dict] = []

    def add_guardrail(self, g: Guardrail):
        if g.checks not in CHECK_POINTS:
            raise ValueError(f"Unknown check point '{g.checks}'. Use one of: {', '.join(CHECK_POINTS)}.")
        self.guardrails.append(g)

    def _run(self, checks, value, run, mode=None, risk=None) -> Result:
        verdicts, action = [], "ok"
        for g in self.guardrails:
            if g.checks != checks or (mode and g.mode != mode):
                continue
            t0 = time.perf_counter()
            hit, verdict = _timed(g, value, run, self.settings, self.budgets.get(g.name, g.budget))
            ms = round((time.perf_counter() - t0) * 1000, 3)
            if verdict in ("timeout", "error"):
                policy = self.on_error.get(g.name, g.on_error) or ("hold" if risk == "irreversible" else "pass")
                want, evidence = ("block" if policy == "hold" else "log"), f"{verdict}; policy {policy}"
            elif hit:
                want, evidence = g.action, hit.evidence
            else:
                want, evidence = "ok", ""
            eff = want if want == "ok" or g.name in self.enforce else "log"
            if eff == "fix" and hit.fixed is not None:
                if checks == "reply" and clearly_longer(_text(value), _text(hit.fixed)):
                    eff, evidence = "retry", evidence + "; fix rejected: reply clearly longer than unfixed"
                else:
                    value = hit.fixed
            self._write(g, run, verdict, want, eff, evidence, ms)
            verdicts.append(Verdict(g.name, verdict, want, eff, redact(evidence)))
            action = min(action, eff, key=ORDER.index)
        return Result(value, action, verdicts)

    def _write(self, g, run, verdict, want, eff, evidence, ms):
        # late import: records -> packformat -> pack -> guard
        from gortguard.records import tags

        ts = datetime.now(timezone.utc).isoformat()
        attrs = {"gort.redacted": True}
        if self.keep_raw and evidence:
            attrs.update({"gort.raw_evidence": evidence, "gort.retention_days": self.retention_days})
        step = {"record": "step", "id": str(uuid.uuid4()), "run_id": str(run.get("id") or "unknown"),
                "index": len(self.log), "kind": "guardrail", "timestamp": ts, "attributes": attrs,
                "tags": tags(what_failed={"pattern": g.pattern},
                             guard={"guardrail": g.name, "check_point": g.checks, "kind": g.kind,
                                    "verdict": verdict, "action": want, "effective_action": eff,
                                    "mode": "enforce" if g.name in self.enforce else "log_only", "ms": ms},
                             time={"day": ts[:10]}, confidence={"data_source": run.get("data_source")})}
        if evidence:
            step["text"] = redact(evidence)
        self.log.append(step)
        if self.log_path:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(step) + "\n")

    # --- check points ---

    def check_user_input(self, message, run) -> Result:
        """message: text or {"text", "id"}. Returns the (possibly masked) message as a dict."""
        msg = {"text": message} if isinstance(message, str) else message
        return self._run("user_input", msg, run)

    def stream_reply(self, chunks, run):
        """Yield checked reply text sentence by sentence; returns the Result (StopIteration.value).

        Chunk guardrails run on each complete sentence before it is sent. End guardrails run on the whole
        reply and can only append a correction, since the text is already sent.
        """
        buf, sent, verdicts, action, index = "", "", [], "ok", 0

        def unit(sentence):
            nonlocal index, action
            r = self._run("reply", {"sentence": sentence, "index": index}, run, mode="chunk")
            index += 1
            verdicts.extend(r.verdicts)
            action = min(action, r.action, key=ORDER.index)
            return r.value["sentence"]

        for chunk in chunks:
            buf += chunk
            while m := _SENTENCE.match(buf):
                out = unit(m.group(1) + m.group(2))
                buf = buf[m.end():]
                sent += out
                if out:
                    yield out
        if buf:
            out = unit(buf)
            sent += out
            if out:
                yield out
        r = self._run("reply", sent, run, mode="end")
        verdicts.extend(r.verdicts)
        action = min(action, r.action, key=ORDER.index)
        if r.value != sent and r.value.startswith(sent):
            yield r.value[len(sent):]
        return Result(r.value if r.value.startswith(sent) else sent, action, verdicts)

    def check_reply(self, reply: str, run) -> Result:
        gen, parts = self.stream_reply([reply], run), []
        while True:
            try:
                parts.append(next(gen))
            except StopIteration as stop:
                return Result("".join(parts), stop.value.action, stop.value.verdicts)

    def check_retrieved(self, docs: list, run) -> Result:
        """docs: [{"id", "text", "refresh_by"}]. Returns the documents to keep."""
        return self._run("retrieved", docs, run)

    def check_memory_write(self, write: dict, run) -> Result:
        return self._run("memory_write", write, run)

    def check_tool_call(self, call: dict, run) -> Result:
        """call: {"tool", "args", "risk", "limit"}."""
        return self._run("tool_call", call, run, risk=call.get("risk"))

    def check_handoff(self, run) -> Result:
        return self._run("handoff", run, run)

    def check_run(self, run) -> Result:
        return self._run("run", run, run)

    def guard(self, tool, risk=None, limit=None):
        """Decorator: tool guardrails run before the call. On block, handoff or ask_user it raises Held."""

        def wrap(fn):
            sig = inspect.signature(fn)

            @functools.wraps(fn)
            def call(*args, run=None, **kwargs):
                run = {} if run is None else run
                bound = sig.bind(*args, **kwargs)
                bound.apply_defaults()
                res = self.check_tool_call({"tool": tool, "args": dict(bound.arguments), "risk": risk,
                                            "limit": limit}, run)
                if res.action in HOLDS:
                    raise Held(res)
                return fn(*bound.args, **bound.kwargs)

            return call

        return wrap
