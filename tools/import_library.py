"""Build src/gortguard/data/patterns.json from a local checkout of sarkars/agent-failure-modes.

Usage: python tools/import_library.py <path-to-agent-failure-modes>
"""

import json
import re
import sys
from pathlib import Path

HMI = Path("agents/by-capability/human-machine-interface")
OUT = Path(__file__).resolve().parent.parent / "src/gortguard/data/patterns.json"


def main(repo: str) -> None:
    root = Path(repo) / HMI
    taxonomy = (root / "roadmap/specs/failure-taxonomy-v1.md").read_text(encoding="utf-8")
    patterns, family = [], None
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
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(patterns, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(patterns)} patterns in {len({p['family'] for p in patterns})} families -> {OUT}")


if __name__ == "__main__":
    main(sys.argv[1])
