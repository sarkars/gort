# Pilot count (plan step 7)

Proposed entries, not measured.

50 pack entries in `packs/pilot/`, one per pattern in the [issue 7](https://github.com/sarkars/gort/issues/7) table, all `status: proposed`, `agent_types: ["conversational"]`, every `limits` blank. Each entry was written from its pattern page and its `evals.json` rubric only. `tests/test_pilot.py` recomputes every number below from the files and fails if one differs.

## Guardrails

| Count | n |
|---|---|
| guardrail rule | 40 |
| guardrail judge | 10 |
| guardrail not_applicable | 0 |
| checks reply | 35 |
| checks run | 5 |
| checks user_input | 3 |
| checks tool_call | 3 |
| checks handoff | 2 |
| checks memory_write | 2 |
| checks retrieved | 0 |

## Evals

| Count | n |
|---|---|
| evals | 173 |
| evals simulated_user | 38 |
| evals over_correct | 52 |

Every entry has at least one `over_correct` eval whose `fail_if` names a reply much longer than needed (owner decision 8: the fix stays close to the unfixed length; the length limit itself is set at step 10, not here).

## Parts marked not_applicable

| Count | n |
|---|---|
| not_applicable prompt | 3 |
| not_applicable design | 0 |
| not_applicable code | 0 |
| not_applicable setup_questions | 0 |
| not_applicable evals | 0 |
| not_applicable guardrail | 0 |

The three prompts: `lost-drafts-and-failed-sends` (send state lives in the client and server), `prompt-edits-by-non-engineers-break-other-behavior` and `tone-changes-shipped-with-no-regression-test` (change and release process). The fix is not reply wording.

## Schema changes

None. `pack-schema.json` is unchanged from main; both `examples/packs/` entries still load.

For the owner's review: `chat-widget-hard-to-find-or-intrusive` guards at check point `run` because the schema has no widget check point. Pages with no T2 Guardrails section took their guardrail from the page's Detection signals: `impatient-idle-nudges` (rule, `run`) and two earlier entries (judge).

## Name check

`tests/data/pilot-denylist.json` holds the capitalized multi-word names from each page's "What it looks like" section (built from the content repo on 2026-10-31, 24 names). No entry contains one. Owner review is the final check.
