"""Build src/gortguard/data/patterns.json and evals.json from a local checkout of sarkars/agent-failure-modes.

Usage: python tools/import_library.py <path-to-agent-failure-modes>
"""

import json
import re
import sys
from pathlib import Path

HMI = Path("agents/by-capability/human-machine-interface")
OUT = Path(__file__).resolve().parent.parent / "src/gortguard/data/patterns.json"
EVALS = OUT.with_name("evals.json")


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _refs(text: str) -> list[str]:
    return sorted(set(re.findall(r"\bR\d+\b", text)), key=lambda r: int(r[1:]))


def test_file_evals(text: str) -> dict:
    """Rubric rows and numbered cases from a tests/<id>.md file."""
    rubric = [
        dict(zip(("line", "rule", "pass", "fail"), _cells(ln)))
        for ln in text.splitlines() if re.match(r"\| R\d+ \|", ln)
    ]
    parts = re.split(r"^## (?:Conversations|Scenarios)\s*$", text, flags=re.MULTILINE)
    section = parts[1].split("\n## ")[0] if len(parts) > 1 else ""
    cases = []
    for ln in section.splitlines():
        if m := re.match(r"\d+\. \*\*(.+?)\*\*\s*(.*)", ln):
            title = re.sub(r"\s*\(R[\d, R]+\)", "", m[1]).rstrip(".")
            cases.append({
                "title": title,
                "rubric": _refs(ln),
                "steps": [["Scenario", m[2]]] if m[2] else [],
                "counter": bool(re.search(r"do nothing special|over-correct", title, re.IGNORECASE)),
            })
        elif cases and (m := re.match(r"\s+([A-Z][\w ]*?):\s*(.+)", ln)):
            cases[-1]["steps"].append([m[1], m[2].strip()])
    return {"source": "test file", "rubric": rubric, "cases": cases}


def page_evals(text: str) -> dict:
    """Fallback: the scenario designs in a page's "How to test it" table."""
    sec = re.search(r"^## 6\..*?(?=^## 7\.)", text, re.MULTILINE | re.DOTALL)
    cases = []
    for ln in (sec[0] if sec else "").splitlines():
        c = _cells(ln)
        if ln.startswith("|") and c[0].isdigit() and len(c) >= 3:
            cases.append({
                "title": c[1],
                "rubric": [],
                "steps": [["Scenario", c[1]], ["Pass if", " | ".join(c[2:])]],
                "counter": bool(re.search(r"over-correct", ln, re.IGNORECASE)),
            })
    return {"source": "page design", "rubric": [], "cases": cases}


def main(repo: str) -> None:
    root = Path(repo) / HMI
    taxonomy = (root / "roadmap/specs/failure-taxonomy-v1.md").read_text(encoding="utf-8")
    patterns, evals, family = [], {}, None
    for line in taxonomy.splitlines():
        if m := re.match(r"Family folder: `([^`]+)`", line):
            family = m[1]
        elif family and (m := re.match(r"\| `([^`]+)` \| ([^|]+) \|", line)):
            pid, name = m[1], m[2].strip()
            page = root / "goals" / family / "failures" / f"{pid}.md"
            text = page.read_text(encoding="utf-8")
            rule = re.search(r"^\*\*Starter rule:\*\* (.+)$", text, re.MULTILINE)
            patterns.append({
                "id": pid,
                "name": name,
                "family": family,
                "starter_rule": rule[1].strip() if rule else "",
                "page": f"{HMI.as_posix()}/goals/{family}/failures/{pid}.md",
            })
            tests = root / "tests" / f"{pid}.md"
            ev = test_file_evals(tests.read_text(encoding="utf-8")) if tests.exists() else page_evals(text)
            oc = re.search(r"^\*\*Don't over-correct\.?\*\*\.?\s*(.+)$", text, re.MULTILINE)
            ev["over_correct"] = oc[1].strip() if oc else ""
            if ev["cases"]:
                evals[pid] = ev
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(patterns, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    EVALS.write_text(json.dumps(evals, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(patterns)} patterns in {len({p['family'] for p in patterns})} families -> {OUT}")
    print(f"{sum(len(e['cases']) for e in evals.values())} eval cases for {len(evals)} patterns -> {EVALS}")


if __name__ == "__main__":
    main(sys.argv[1])
