# GORT (Guard, Observe, Repair, Test)

Best-practice packs and checks for AI agents, built from the failure patterns at
[sarkars/agent-failure-modes](https://github.com/sarkars/agent-failure-modes).

**Status: in design.** Presets, bundles, the policy builder and the core guardrail runner exist (plan step 10). No guardrail or detector has been measured yet.

## Pick bundles, build the policy block

```bash
gort bundles                      # presets and bundles, with aliases
gort search "transfer"            # find the bundle for a topic
gort show handoff                 # patterns in one bundle
gort build --preset support-bot --exclude cold-transfer   # writes gort-policy.md (prompt) and gort-checklist.md (code, chat widget, process)
# also writes gort-evals.jsonl: eval cases from the library tests for the same patterns (not yet run)
gort build --preset support-bot --depth deep             # lite (default): 1 case + 1 over-correction case per pattern; deep: every case
gort build --preset support-bot --focus handoff,over-correct   # one type: bundle, family, place (prompt, code, ui, process), Pattern ID or over-correct
```

```python
from gortguard.pack import pack, Preset, Bundle
p = pack(Preset.SUPPORT_BOT, bundles=[Bundle.MONEY], exclude=["cold-transfer"])
system_prompt = my_template.replace("{{gort_policy}}", p.policy())
```

Pattern data comes from the library: `python tools/import_library.py <path-to-agent-failure-modes>` rewrites `src/gortguard/data/patterns.json`.
Pack entries (one failure, seven parts) follow `src/gortguard/data/pack-schema.json`; `gortguard.packformat.load_entry(path)` checks one. Two hand-written examples are in `examples/packs/`. Limits are always blank, and entries carry no framework mapping.
Run, Step and Finding records follow `src/gortguard/data/record-schema.json`; [docs/record-format.md](docs/record-format.md) maps them to OpenTelemetry GenAI, OpenInference and the chat event schema v0.1. `gortguard.records.check(record)` checks one.

## Guardrails

```python
p = pack(Preset.SUPPORT_BOT, enforce=["card-number"], log_path="gort.jsonl",
         settings={"filler_openers": [...], "saved_phrases": [...]})   # lists are blank until your team sets them
text = p.prompt(budget=None, rank=None)       # lines over the budget go to p.not_in_prompt
pairs = p.conflicts(my_prompt)                # (your sentence, pack sentence) pairs to decide
r = p.check_user_input(message, run)          # also: check_reply, stream_reply, check_retrieved,
                                              # check_memory_write, check_tool_call, check_handoff, check_run

@p.guard("refund", risk="irreversible", limit={"amount": None})   # raises gortguard.guard.Held on block or handoff
def refund(order_id, amount): ...
```

Guardrails start in log-only mode; `enforce` names the ones allowed to act. Each verdict is written as a
`guardrail` Step with Guard tags, with emails, card and phone numbers masked. Raw text is kept only with
`keep_raw=True` and a `retention_days`. A check that times out or fails goes through, except before an
irreversible tool call, where it holds; `on_error` changes this per guardrail. Time budgets are blank until set.
A reply fix that makes the reply clearly longer than the unfixed one is rejected and the result is `retry`.

Not published to PyPI.

## Develop

```bash
pip install -e ".[dev]"
ruff check .
pytest -q
```

Licence: MIT.
