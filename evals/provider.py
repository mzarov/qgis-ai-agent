import json
import os
import urllib.request
from pathlib import Path
from typing import Any

FIXTURE = Path(__file__).with_name("fixture.json")
MAX_READ_ROUNDS = 3
TIMEOUT_S = 300
DESCRIBE_LAYER = "describe_layer"
FIELD_VALUES = "get_field_values"
DESCRIBE_ALGORITHM = "describe_processing"


def call_api(prompt: str, options: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    config = (options or {}).get("config") or {}
    messages = json.loads(prompt)
    tools = json.loads(Path(config["tools"]).read_text(encoding="utf-8"))
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    calls: list[dict[str, Any]] = []
    usage = {"prompt": 0, "completion": 0, "total": 0}
    text = ""
    for _ in range(MAX_READ_ROUNDS + 1):
        try:
            answer = chat(config, messages, tools)
        except (OSError, ValueError) as error:
            return {"error": f"The model request failed: {error}", "tokenUsage": usage}
        add_usage(usage, answer.get("usage") or {})
        message = ((answer.get("choices") or [{}])[0]).get("message") or {}
        turn = list(message.get("tool_calls") or [])
        text = message.get("content") or ""
        calls += turn
        results = [answered(call, data) for call in turn]
        if not turn or any(result is None for result in results):
            break
        messages.append({"role": "assistant", "content": text or None, "tool_calls": turn})
        for call, result in zip(turn, results, strict=True):
            messages.append({"role": "tool", "tool_call_id": call.get("id"), "content": json.dumps(result)})
    return {"output": {"content": text, "tool_calls": calls}, "tokenUsage": usage}


def chat(config: dict[str, Any], messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
    body = {
        "model": config["model"],
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto",
        "temperature": config.get("temperature", 0),
        "max_tokens": config.get("max_tokens", 4096),
    }
    headers = {"Content-Type": "application/json"}
    key = os.environ.get(config.get("key_variable") or "", "")
    if key:
        headers["Authorization"] = f"{config.get('auth') or 'Bearer'} {key}"
    url = str(config["url"]).rstrip("/") + "/chat/completions"
    request = urllib.request.Request(url, json.dumps(body).encode("utf-8"), headers, method="POST")
    with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:  # nosec B310
        return json.loads(response.read().decode("utf-8"))


def answered(call: dict[str, Any], data: dict[str, Any]) -> Any:
    function = call.get("function") or {}
    try:
        arguments = json.loads(function.get("arguments") or "{}")
    except ValueError:
        return None
    if not isinstance(arguments, dict):
        return None
    name = function.get("name")
    if name == DESCRIBE_LAYER:
        return data[DESCRIBE_LAYER].get(arguments.get("layer_name"))
    if name == FIELD_VALUES:
        return data[FIELD_VALUES].get(f"{arguments.get('layer_name')}/{arguments.get('field_name')}")
    if name == DESCRIBE_ALGORITHM:
        return data[DESCRIBE_ALGORITHM].get(arguments.get("algorithm_id"))
    return None


def add_usage(total: dict[str, int], usage: dict[str, Any]) -> None:
    total["prompt"] += int(usage.get("prompt_tokens") or 0)
    total["completion"] += int(usage.get("completion_tokens") or 0)
    total["total"] += int(usage.get("total_tokens") or 0)
