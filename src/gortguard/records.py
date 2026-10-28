"""Record format (plan step 6): Run, Step and Finding, and two small converters.

Chat event schema v0.1 events and OpenTelemetry GenAI / OpenInference spans become one Run and its Steps.
Every record carries all eleven tag families; a family nothing fills is "unknown". The full importer is step 18.
"""

import json
from importlib.resources import files

from gortguard.agentformat import read_json_or_yaml
from gortguard.packformat import validate

SCHEMA = json.loads((files("gortguard") / "data" / "record-schema.json").read_text(encoding="utf-8"))
TAGS_SCHEMA = json.loads((files("gortguard") / "data" / "tags-schema.json").read_text(encoding="utf-8"))
FAMILIES = SCHEMA["$defs"]["tags"]["required"]

# chat event schema v0.1 event_type -> step kind (message is split by speaker)
CHAT_KINDS = {"handoff": "handoff", "error": "error", "lookup": "tool_call", "action": "tool_call",
              "payment": "tool_call", "verification": "tool_call"}
# OpenTelemetry GenAI gen_ai.operation.name -> step kind
OTEL_KINDS = {"chat": "model_call", "generate_content": "model_call", "text_completion": "model_call",
              "plan": "plan", "execute_tool": "tool_call", "retrieval": "retrieval", "search_memory": "memory_read",
              "create_memory": "memory_write", "update_memory": "memory_write", "delete_memory": "memory_write",
              "invoke_agent": "handoff"}
# OpenInference openinference.span.kind -> step kind
OI_KINDS = {"LLM": "model_call", "TOOL": "tool_call", "RETRIEVER": "retrieval", "GUARDRAIL": "guardrail",
            "AGENT": "handoff", "CHAIN": "plan"}


def tags(**filled) -> dict:
    """All eleven families; the ones given keep only their known values, the rest are "unknown"."""
    out = {}
    for fam in FAMILIES:
        known = {k: v for k, v in filled.get(fam, {}).items() if v not in (None, "", [])}
        out[fam] = known or "unknown"
    return out


def check(record: dict) -> list[str]:
    """Errors for one run, step or finding record."""
    kind = record.get("record") if isinstance(record, dict) else None
    if kind not in ("run", "step", "finding"):
        return ["$.record: must be run, step or finding"]
    return validate(record, {"$ref": f"#/$defs/{kind}"}, root=SCHEMA)


def load_tags(path) -> list:
    """Load a tags.yaml registry. Raise ValueError listing every problem."""
    reg = read_json_or_yaml(path)
    errors = validate(reg, TAGS_SCHEMA, root=TAGS_SCHEMA)
    if errors:
        raise ValueError(f"{path}:\n  " + "\n  ".join(errors))
    return reg


def _run(run_id, agent_type, source, started, channel, data_source):
    return {"record": "run", "id": run_id, "agent_type": agent_type, "source": source, "started": started,
            "tags": tags(system={"agent_type": agent_type, "channel": channel},
                         time={"day": started[:10]}, confidence={"data_source": data_source})}


def from_chat_events(events: list, agent_type="conversational", data_source="simulated") -> list:
    """Chat event schema v0.1 events of one conversation -> [run, step, ...]."""
    first = events[0]
    run_id = first["conversation_id"]
    records = [_run(run_id, agent_type, "chat_events", first["timestamp"], first["channel"], data_source)]
    for ev in events:
        etype = ev["event_type"]
        if etype == "message":
            kind = "user_message" if ev["speaker"] == "user" else "bot_reply"
        elif etype == "request_end" and ev.get("request.state") == "timed_out":
            kind = "timeout"
        else:
            kind = CHAT_KINDS.get(etype, "session_event")
        attrs = {k: v for k, v in ev.items() if "." in k}
        step = {"record": "step", "id": ev["event_id"], "run_id": run_id, "index": ev["turn_index"], "kind": kind,
                "timestamp": ev["timestamp"], "attributes": attrs,
                "tags": tags(system={"agent_type": agent_type, "channel": ev["channel"], "step_kind": kind,
                                     "intent": ev.get("user_label.intent"), "entry_point": ev.get("context.entry_point")},
                             time={"day": ev["timestamp"][:10]},
                             confidence={"data_source": data_source},
                             audience={"signed_in": ev.get("context.signed_in")})}
        if "text" in ev:
            step["text"] = ev["text"]
        records.append(step)
    return records


def from_spans(spans: list, agent=None, agent_type="action", data_source="simulated") -> list:
    """Spans of one trace, as {span_id, parent_span_id, start_time, attributes} dicts, -> [run, step, ...].

    Reads OpenTelemetry GenAI attributes first, then OpenInference. `agent` is a loaded agent.yaml; its tool risk tags fill Guard.
    """
    risk = {t["name"]: t["risk"] for t in (agent or {}).get("tools", [])}
    first = spans[0]
    a0 = first["attributes"]
    run_id = a0.get("gen_ai.conversation.id") or a0.get("session.id") or first["trace_id"]
    source = "otel_genai" if any("gen_ai.operation.name" in s["attributes"] for s in spans) else "openinference"
    records = [_run(run_id, agent_type, source, first["start_time"], "unknown", data_source)]
    for i, span in enumerate(spans, 1):
        a = span["attributes"]
        kind = OTEL_KINDS.get(a.get("gen_ai.operation.name")) or OI_KINDS.get(a.get("openinference.span.kind"), "unknown")
        if "error.type" in a:
            kind = "timeout" if a["error.type"] == "timeout" else "error"
        tool = a.get("gen_ai.tool.name") or a.get("tool.name")
        step = {"record": "step", "id": span["span_id"], "run_id": run_id, "index": i, "kind": kind,
                "timestamp": span["start_time"], "attributes": a,
                "tags": tags(system={"agent_type": agent_type, "step_kind": kind, "tool": tool,
                                     "agent": a.get("gen_ai.agent.name") or a.get("agent.name"),
                                     "agent_version": a.get("gen_ai.agent.version"),
                                     "model": a.get("gen_ai.request.model") or a.get("llm.model_name"),
                                     "retrieval_index": a.get("gen_ai.data_source.id")},
                             guard={"risk": risk.get(tool)},
                             time={"day": span["start_time"][:10]},
                             confidence={"data_source": data_source})}
        if span.get("parent_span_id"):
            step["parent_id"] = span["parent_span_id"]
        records.append(step)
    return records
