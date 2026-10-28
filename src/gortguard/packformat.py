"""Pack entry format (plan step 4): load a pack entry and check it against pack-schema.json."""

import json
import re
from importlib.resources import files

from gortguard.pack import BY_ID

SCHEMA = json.loads((files("gortguard") / "data" / "pack-schema.json").read_text(encoding="utf-8"))
_TYPES = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None)}


def validate(value, schema=SCHEMA, path="$", root=SCHEMA) -> list[str]:
    """Return errors for `value`. Covers the JSON Schema keywords pack-schema.json uses, no more."""
    # ponytail: subset validator (no new dependency); swap for `jsonschema` if the schema outgrows it
    if "$ref" in schema:
        return validate(value, root["$defs"][schema["$ref"].rsplit("/", 1)[1]], path, root)
    if "anyOf" in schema:
        tries = [validate(value, s, path, root) for s in schema["anyOf"]]
        return [] if any(not t for t in tries) else min(tries, key=len)
    if "enum" in schema and value not in schema["enum"]:
        return [f"{path}: {value!r} is not one of {schema['enum']}"]
    t = schema.get("type")
    if t and not isinstance(value, _TYPES[t]):
        return [f"{path}: expected {t}"]
    errors = []
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            errors.append(f"{path}: empty")
        if "pattern" in schema and not re.match(schema["pattern"], value):
            errors.append(f"{path}: {value!r} does not match {schema['pattern']}")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            errors.append(f"{path}: needs at least {schema['minItems']} item(s)")
        for i, item in enumerate(value):
            errors += validate(item, schema.get("items", {}), f"{path}[{i}]", root)
    if isinstance(value, dict):
        props = schema.get("properties", {})
        errors += [f"{path}: missing {k}" for k in schema.get("required", []) if k not in value]
        for k, v in value.items():
            if k in props:
                errors += validate(v, props[k], f"{path}.{k}", root)
            elif schema.get("additionalProperties") is False:
                errors.append(f"{path}: unknown field {k}")
            elif isinstance(schema.get("additionalProperties"), dict):
                errors += validate(v, schema["additionalProperties"], f"{path}.{k}", root)
    return errors


def load_entry(path) -> dict:
    """Load one pack entry (JSON). Raise ValueError listing every problem."""
    with open(path, encoding="utf-8") as f:
        entry = json.load(f)
    errors = validate(entry)
    if isinstance(entry, dict) and entry.get("pattern") not in BY_ID:
        errors.append(f"$.pattern: {entry.get('pattern')!r} is not a Pattern ID in the taxonomy")
    if errors:
        raise ValueError(f"{path}:\n  " + "\n  ".join(errors))
    return entry
