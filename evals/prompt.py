import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import context as agent_request  # noqa: E402


def build(context: dict[str, Any]) -> str:
    variables = context.get("vars") or {}
    messages, _ = agent_request.build(
        skill=str(variables.get("skill") or ""),
        request=str(variables.get("request") or ""),
        reads=reads(variables.get("reads")),
        history=list((variables.get("history") or {}).get("messages") or []),
        locale=str(variables.get("locale") or "en"),
        measurements=str(variables.get("measurements") or ""),
    )
    return json.dumps(messages, ensure_ascii=False)


def reads(value: Any) -> list[Any]:
    # Never a bare list in a case: promptfoo turns a list in vars into one test per item.
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, dict):
        return list(value.get("steps") or [])
    return []
