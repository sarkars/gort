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

    def policy(self) -> str:
        """The policy block: precedence line, then one line per rule tagged with its Pattern IDs."""
        merged: dict[str, list[str]] = {}
        for p in self.patterns:
            merged.setdefault(_rule(p["starter_rule"]), []).append(p["id"])
        lines = [f"- {rule} [{', '.join(ids)}]" for rule, ids in merged.items()]
        head = f"<!-- gort policy. Bundles: {', '.join(self.bundles)}. {len(self.patterns)} patterns. -->"
        return "\n".join([head, PRECEDENCE, "", *lines]) + "\n"


def pack(preset=None, bundles=(), exclude=()) -> Pack:
    return Pack(preset, bundles, exclude)
