# Record format (plan step 6)

GORT writes three kinds of record. Stage 1 guardrails write them; Stage 2 reads them.

| Record | What it is | Schema |
|---|---|---|
| Run | One conversation or one agent trace | `src/gortguard/data/record-schema.json#/$defs/run` |
| Step | One event or span inside a run | `#/$defs/step` |
| Finding | One failure pattern seen on one step, with its evidence | `#/$defs/finding` |

Every record carries all eleven tag families: `what_failed`, `system`, `guard`, `business`, `impact`, `risk`, `time`, `volume`, `fix`, `confidence`, `audience`. A family that nothing could fill is the string `"unknown"`. It is never dropped, so a count of `unknown` shows what the source data does not say.

A team's own tags go in `tags.yaml` (format: `src/gortguard/data/tags-schema.json`, example: `examples/tags.yaml`). The loader and the four tag sources run in plan step 19. This step only fixes the format.

`gortguard.records` has two small converters, `from_chat_events` and `from_spans`. They are enough for the step 6 check. The full importer is plan step 18.

## Pinned sources

The mapping below was read from these commits on 2026-10-28. If a source changes, re-read it and update this table in the same pull request as the code.

- OpenTelemetry GenAI semantic conventions: `open-telemetry/semantic-conventions-genai` at commit `3fe84604a581b3d50dd5b4bd29383b462d2a5018` (files `gen-ai-spans.md`, `gen-ai-agent-spans.md`). Most of these attributes are marked Development there, so expect changes.
- OpenInference semantic conventions: `Arize-ai/openinference`, `spec/semantic_conventions.md` at commit `1832ad061b2395318ad961218ac7fe43be85b75a`.
- Chat event schema v0.1: [conversation-event-schema-v0.1.md](https://github.com/sarkars/agent-failure-modes/blob/main/agents/by-capability/human-machine-interface/roadmap/specs/conversation-event-schema-v0.1.md) in the content repository. It is a proposed draft.

## Step kinds

| Step `kind` | Chat event schema v0.1 | OTel `gen_ai.operation.name` | OpenInference `openinference.span.kind` |
|---|---|---|---|
| `user_message` | `message` with `speaker` = `user` | (no kind) | (no kind) |
| `bot_reply` | `message` with any other speaker | (no kind) | (no kind) |
| `model_call` | (no kind) | `chat`, `generate_content`, `text_completion` | `LLM` |
| `plan` | (no kind) | `plan` | `CHAIN` |
| `tool_call` | `lookup`, `action`, `payment`, `verification` | `execute_tool` | `TOOL` |
| `retrieval` | (no kind) | `retrieval` | `RETRIEVER` |
| `memory_read` | (no kind) | `search_memory` | (no kind) |
| `memory_write` | (no kind) | `create_memory`, `update_memory`, `delete_memory` | (no kind) |
| `guardrail` | (no kind) | (no kind) | `GUARDRAIL` |
| `handoff` | `handoff` | `invoke_agent` | `AGENT` |
| `error` | `error` | any span with `error.type` other than `timeout` | (see `error.type`) |
| `timeout` | `request_end` with `request.state` = `timed_out` | any span with `error.type` = `timeout` | (see `error.type`) |
| `session_event` | every other event type | (no kind) | (no kind) |
| `unknown` | (none) | any other value | `EMBEDDING`, `RERANKER`, `EVALUATOR`, `PROMPT`, `DECISION` |

`error.type` overrides the operation kind: a tool call that timed out is recorded as `timeout`, and the original operation stays in `attributes`.

### Gaps

- OpenInference has no memory span kind. Memory reads and writes from an OpenInference source come through as `unknown` or as `TOOL`.
- OpenTelemetry GenAI has no guardrail operation. A guardrail check from an OTel source comes through as `unknown`.
- Neither has a kind for a handoff to a person. `handoff` from `invoke_agent` or `AGENT` means a handoff to another agent. Only the chat event schema `handoff` event means a person.
- Neither span format has user or bot messages as their own spans. Messages sit inside a `model_call` step's attributes.

## Run and step fields

| GORT field | Chat event schema v0.1 | OpenTelemetry GenAI | OpenInference |
|---|---|---|---|
| `run.id` | `conversation_id` | `gen_ai.conversation.id`, else the trace id | `session.id`, else the trace id |
| `run.source` | `chat_events` | `otel_genai` | `openinference` |
| `run.started` | first event `timestamp` | first span start time | first span start time |
| `step.id` | `event_id` | span id | span id |
| `step.parent_id` | (none) | parent span id | parent span id |
| `step.index` | `turn_index` | order in the trace | order in the trace |
| `step.text` | `text` | (not read) | (not read) |
| `step.attributes` | every dotted field (`request.state`, `context.signed_in` and so on) | all span attributes | all span attributes |

## Tags the converters fill

| Family / key | Chat event schema v0.1 | OpenTelemetry GenAI | OpenInference |
|---|---|---|---|
| `system.agent_type` | caller sets it | caller sets it | caller sets it |
| `system.channel` | `channel` | (unknown) | (unknown) |
| `system.step_kind` | step kind | step kind | step kind |
| `system.intent` | `user_label.intent` | (none) | (none) |
| `system.entry_point` | `context.entry_point` | (none) | (none) |
| `system.tool` | (none) | `gen_ai.tool.name` | `tool.name` |
| `system.agent` | (none) | `gen_ai.agent.name` | `agent.name` |
| `system.agent_version` | (none) | `gen_ai.agent.version` | (none) |
| `system.model` | (none) | `gen_ai.request.model` | `llm.model_name` |
| `system.retrieval_index` | (none) | `gen_ai.data_source.id` | (none) |
| `guard.risk` | (none) | the tool's `risk` in `agent.yaml` | the tool's `risk` in `agent.yaml` |
| `time.day` | date of `timestamp` | date of span start | date of span start |
| `confidence.data_source` | caller sets it (`simulated` for the examples) | caller sets it | caller sets it |
| `audience.signed_in` | `context.signed_in` | (none) | (none) |

The other families (`what_failed`, `business`, `impact`, `risk`, `volume`, `fix`) stay `unknown` in raw runs. Detectors (step 8 onward) and `tags.yaml` fill them.

## Check

`tests/test_records.py` converts one synthetic chat run (`examples/runs/chat-run.json`) and one synthetic tool run (`examples/runs/tool-run.json`). Every record passes the schema, and every one of the eleven families is present or `unknown`. Both runs are made up for the test; they are not customer data.
