# GORT (Guard, Observe, Repair, Test)

Best-practice packs and checks for AI agents, built from the failure patterns at
[sarkars/agent-failure-modes](https://github.com/sarkars/agent-failure-modes).

**Status: in design.** Only presets, bundles and the policy builder exist (plan step 2a). No guardrail or detector exists or has been measured yet.

## Pick bundles, build the policy block

```bash
gort bundles                      # presets and bundles, with aliases
gort search "transfer"            # find the bundle for a topic
gort show handoff                 # patterns in one bundle
gort build --preset support-bot --exclude cold-transfer   # writes gort-policy.md (prompt) and gort-checklist.md (code, chat widget, process)
# also writes gort-evals.jsonl: eval cases from the library tests for the same patterns (not yet run)
```

```python
from gortguard.pack import pack, Preset, Bundle
p = pack(Preset.SUPPORT_BOT, bundles=[Bundle.MONEY], exclude=["cold-transfer"])
system_prompt = my_template.replace("{{gort_policy}}", p.policy())
```

Pattern data comes from the library: `python tools/import_library.py <path-to-agent-failure-modes>` rewrites `src/gortguard/data/patterns.json`.
Not published to PyPI.

## Develop

```bash
pip install -e ".[dev]"
ruff check .
pytest -q
```

Licence: MIT.
