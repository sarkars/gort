"""agent.yaml format (plan step 5): load an agent description and check it against agent-schema.json."""

import json
from importlib.resources import files

from gortguard.packformat import validate

SCHEMA = json.loads((files("gortguard") / "data" / "agent-schema.json").read_text(encoding="utf-8"))


def load_agent(path) -> dict:
    """Load agent.yaml. JSON syntax needs nothing; block-style YAML needs PyYAML. Raise ValueError listing every problem."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    try:
        agent = json.loads(text)
    except json.JSONDecodeError:
        try:
            import yaml
        except ImportError:
            raise ValueError(f"{path}: not JSON; write agent.yaml in JSON syntax (valid YAML) or install PyYAML") from None
        agent = yaml.safe_load(text)
    errors = validate(agent, SCHEMA, root=SCHEMA)
    if errors:
        raise ValueError(f"{path}:\n  " + "\n  ".join(errors))
    return agent
