"""agent.yaml format (plan step 5): load an agent description and check it against agent-schema.json."""

import json
from importlib.resources import files

from gortguard.packformat import validate

SCHEMA = json.loads((files("gortguard") / "data" / "agent-schema.json").read_text(encoding="utf-8"))


def read_json_or_yaml(path):
    """JSON syntax needs nothing; block-style YAML needs PyYAML."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        try:
            import yaml
        except ImportError:
            raise ValueError(f"{path}: not JSON; write it in JSON syntax (valid YAML) or install PyYAML") from None
        return yaml.safe_load(text)


def load_agent(path) -> dict:
    """Load agent.yaml. Raise ValueError listing every problem."""
    agent = read_json_or_yaml(path)
    errors = validate(agent, SCHEMA, root=SCHEMA)
    if errors:
        raise ValueError(f"{path}:\n  " + "\n  ".join(errors))
    return agent
