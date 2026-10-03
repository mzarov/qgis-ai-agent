"""Parameter specs that many tools share, written once so every schema says the same thing."""

from typing import Any

LAYER_NAME_NOTE = "Layer name exactly as in the project"
LAYER_ID_NOTE = "Stable layer id from list_layers; required when names are duplicated"


def layer_name(description: str = LAYER_NAME_NOTE, required: bool = True) -> dict[str, Any]:
    return {"name": "layer_name", "type": "string", "description": description, "required": required}


def layer_id() -> dict[str, Any]:
    return {"name": "layer_id", "type": "string", "description": LAYER_ID_NOTE, "required": False}
