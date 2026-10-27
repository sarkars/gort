"""Presets, bundles and the compiled policy block. Data comes from the failure-patterns library."""

import difflib
import json
import re
from enum import Enum
from importlib.resources import files

_DATA = files("gortguard") / "data"
PATTERNS = json.loads((_DATA / "patterns.json").read_text(encoding="utf-8"))
_CFG = json.loads((_DATA / "bundles.json").read_text(encoding="utf-8"))
BUNDLES = _CFG["bundles"]
PRESETS = _CFG["presets"]
LATER = _CFG["later"]["families"]
BY_ID = {p["id"]: p for p in PATTERNS}
_PLACE = json.loads((_DATA / "placement.json").read_text(encoding="utf-8"))["place"]
EVALS = json.loads((_DATA / "evals.json").read_text(encoding="utf-8"))
for _p in PATTERNS:
    _p["place"] = _PLACE.get(_p["id"], ["prompt"])

PLACES = {
    "code": "Code checks in your agent's server (guardrails)",
    "ui": "Chat widget",
    "process": "Tests and reviews your team runs",
}

PRECEDENCE = (
    "Precedence: your own business rules come first, then safety, then the style lines below. "
    "If a line below conflicts with your own rules, follow your rules."
)


def _const(name: str) -> str:
    return name.upper().replace("-", "_")


Preset = Enum("Preset", {_const(k): k for k in PRESETS}, type=str)
Bundle = Enum("Bundle", {_const(k): k for k in BUNDLES}, type=str)

_ALIASES = {a: name for name, b in BUNDLES.items() for a in b["aliases"]}


def resolve_bundle(name: str) -> str:
    """Return the bundle for a name or alias; raise ValueError with suggestions if unknown."""
    name = str(getattr(name, "value", name)).strip().lower()
    if name in BUNDLES:
        return name
    if name in _ALIASES:
        return _ALIASES[name]
    close = difflib.get_close_matches(name, [*BUNDLES, *_ALIASES], n=3)
    hint = f" Did you mean: {', '.join(close)}?" if close else ""
    raise ValueError(f"Unknown bundle '{name}'.{hint} Run `gort bundles` for the list.")


def resolve_preset(name: str) -> str:
    name = str(getattr(name, "value", name)).strip().lower()
    if name in PRESETS:
        return name
    close = difflib.get_close_matches(name, PRESETS, n=3)
    hint = f" Did you mean: {', '.join(close)}?" if close else ""
    raise ValueError(f"Unknown preset '{name}'.{hint} Run `gort bundles` for the list.")


def bundle_patterns(bundle: str) -> list[dict]:
    fams = BUNDLES[resolve_bundle(bundle)]["families"]
    return [p for p in PATTERNS if p["family"] in fams]


def bundle_of(family: str) -> str | None:
    return next((n for n, b in BUNDLES.items() if family in b["families"]), None)


def search(words: str) -> tuple[list[str], list[dict]]:
    """Bundles whose name, alias or description match any word, then patterns matching every word."""
    terms = words.lower().split()
    bundles = [
        n for n, b in BUNDLES.items()
        if any(t in " ".join([n, *b["aliases"], b["about"]]).lower() for t in terms)
    ]
    patterns = [
        p for p in PATTERNS
        if bundle_of(p["family"])
        and all(t in f"{p['id']} {p['name']} {p['starter_rule']}".lower() for t in terms)
    ]
    for p in patterns:  # a pattern hit also surfaces its bundle
        if (b := bundle_of(p["family"])) not in bundles:
            bundles.append(b)
    return bundles, patterns


def _rule(text: str) -> str:
    return re.sub(r"^Rule \d+:\s*", "", text).strip()


DEPTHS = ("lite", "deep")
_FAMILIES = {p["family"] for p in PATTERNS}


def _focus(name: str):
    """One --focus value as (kind, test). Values of one kind are OR'd; different kinds are AND'd."""
    name = str(name).strip().lower()
    if name in ("over-correct", "over-correction", "counter"):
        return "counter", lambda p, c: c["counter"]
    if name in PLACES or name == "prompt":
        return "place", lambda p, c: name in p["place"]
    if name in _FAMILIES:
        return "topic", lambda p, c: p["family"] == name
    if name in BY_ID:
        return "topic", lambda p, c: p["id"] == name
    if name in BUNDLES or name in _ALIASES:
        fams = set(BUNDLES[resolve_bundle(name)]["families"])
        return "topic", lambda p, c: p["family"] in fams
    known = ["over-correct", "prompt", *PLACES, *BUNDLES, *_ALIASES, *_FAMILIES, *BY_ID]
    close = difflib.get_close_matches(name, known, n=3)
    hint = f" Did you mean: {', '.join(close)}?" if close else ""
    raise ValueError(
        f"Unknown focus '{name}'.{hint} Use a bundle, family, place (prompt, code, ui, process), "
        "Pattern ID or over-correct."
    )


class Pack:
    def __init__(self, preset=None, bundles=(), exclude=()):
        names = list(PRESETS[resolve_preset(preset)]["bundles"]) if preset else []
        names += [resolve_bundle(b) for b in bundles]
        self.bundles = list(dict.fromkeys(names))
        if not self.bundles:
            raise ValueError("Pick a preset or at least one bundle. Run `gort bundles` for the list.")
        for pid in exclude:
            if pid not in BY_ID:
                close = difflib.get_close_matches(pid, BY_ID, n=3)
                hint = f" Did you mean: {', '.join(close)}?" if close else ""
                raise ValueError(f"Unknown pattern '{pid}'.{hint}")
        fams = {f for b in self.bundles for f in BUNDLES[b]["families"]}
        self.patterns = [p for p in PATTERNS if p["family"] in fams and p["id"] not in set(exclude)]

    @property
    def prompt_patterns(self) -> list[dict]:
        return [p for p in self.patterns if "prompt" in p["place"]]

    def policy(self) -> str:
        """The policy block: precedence line, then one line per rule the model can follow."""
        merged: dict[str, list[str]] = {}
        for p in self.prompt_patterns:
            merged.setdefault(_rule(p["starter_rule"]), []).append(p["id"])
        lines = [f"- {rule} [{', '.join(ids)}]" for rule, ids in merged.items()]
        head = f"<!-- gort policy. Bundles: {', '.join(self.bundles)}. {len(merged)} lines. -->"
        return "\n".join([head, PRECEDENCE, "", *lines]) + "\n"

    def checklist(self) -> str:
        """Fixes that do not belong in the prompt, grouped by where they go."""
        out = [f"# GORT checklist: not prompt text\n\nBundles: {', '.join(self.bundles)}."]
        for place, title in PLACES.items():
            items = [p for p in self.patterns if place in p["place"]]
            if items:
                out.append(f"\n## {title}\n")
                out += [f"- [ ] {_rule(p['starter_rule'])} [{p['id']}]" for p in items]
        return "\n".join(out) + "\n"

    def evals(self, depth: str = "deep", focus=()) -> list[dict]:
        """Eval cases from the library's test files (or page designs), for this pack only.

        depth: "lite" keeps the first ordinary case and the first over-correction case per pattern;
        "deep" keeps every case. focus narrows to a type: a bundle or alias, a family, a place
        (prompt, code, ui, process), a Pattern ID, or "over-correct". "handoff,over-correct"
        means handoff cases that check for over-correction; "ui,code" means either place.
        """
        if depth not in DEPTHS:
            raise ValueError(f"Unknown depth '{depth}'. Use one of: {', '.join(DEPTHS)}.")
        keep: dict[str, list] = {}
        for f in focus:
            kind, test = _focus(f)
            keep.setdefault(kind, []).append(test)
        cases = []
        for p in self.patterns:
            ev = EVALS.get(p["id"])
            if not ev:
                continue
            picked = ev["cases"]
            if depth == "lite":
                picked = [c for c in (
                    next((c for c in picked if not c["counter"]), None),
                    next((c for c in picked if c["counter"]), None),
                ) if c]
            for c in picked:
                if not all(any(t(p, c) for t in tests) for tests in keep.values()):
                    continue
                cases.append({
                    "pattern": p["id"],
                    "name": p["name"],
                    "place": p["place"],
                    "case": c["title"],
                    "counter": c["counter"],
                    "steps": c["steps"],
                    "rubric": [r for r in ev["rubric"] if r["line"] in c["rubric"]],
                    "over_correct": ev["over_correct"],
                    "source": ev["source"],
                    "page": p["page"],
                })
        if keep and not cases:
            raise ValueError(f"No eval cases in this pack match --focus {', '.join(focus)}.")
        return cases


def pack(preset=None, bundles=(), exclude=()) -> Pack:
    return Pack(preset, bundles, exclude)
