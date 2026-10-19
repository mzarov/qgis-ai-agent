import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import tests  # noqa: E402,F401  installs the qgis stub when QGIS is absent
from ai_agent.core.agent import request as request_module  # noqa: E402
from ai_agent.core.agent.loop import PRELOADED_SKILLS  # noqa: E402
from ai_agent.core.agent.prompts import LOAD_SKILL_TOOL  # noqa: E402
from ai_agent.core.agent.skills import load_skill  # noqa: E402
from ai_agent.core.agent.transcript import ToolResult, Transcript  # noqa: E402
from ai_agent.core.context import project as project_context  # noqa: E402
from ai_agent.core.llm.live import fold_live  # noqa: E402
from ai_agent.core.llm.reasoning import wire_messages  # noqa: E402
from ai_agent.core.llm.turns import PROTOCOL_NATIVE, ModelTurn, ToolCall  # noqa: E402

FIXTURE_PATH = Path(__file__).with_name("fixture.json")
OVERRIDES = {
    "url_override": "http://eval.invalid/v1",
    "model_override": "eval",
    "key_override": "",
    "auth_type_override": "bearer",
    "dialect_override": "openai",
    "verify_override": True,
}
DESCRIBE_LAYER = "describe_layer"
FIELD_VALUES = "get_field_values"
FIELD_SEPARATOR = "/"
DESCRIBE_ALGORITHM = "describe_processing"
ALGORITHM_SEPARATOR = ":"
NO_MEASUREMENTS = "none"
MEASUREMENTS = "Measurements:"
LOCAL_UTM = "EPSG:32637"


def without_ellipsoid(context: str) -> str:
    line = project_context.UNMEASURED + project_context.METRIC_FALLBACK.format(LOCAL_UTM)
    return "\n".join(line if item.startswith(MEASUREMENTS) else item for item in context.splitlines())


def fixture() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def build(
    skill: str = "",
    request: str = "",
    reads: list[Any] | None = None,
    history: list[dict[str, str]] | None = None,
    locale: str = "en",
    measurements: str = "",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    data = fixture()
    if measurements == NO_MEASUREMENTS:
        data["project_context"] = without_ellipsoid(data["project_context"])
    loaded = list(PRELOADED_SKILLS)
    transcript = Transcript()
    transcript.add_user(request)
    calls = iter(range(1, 1000))
    if skill and skill not in loaded:
        call = ToolCall(id=f"call_{next(calls)}", name=LOAD_SKILL_TOOL, arguments={"names": [skill]})
        result, _ = load_skill(call, loaded)
        _add_step(transcript, call, result)
    for read in reads or []:
        tool, arguments, payload = _read(read, data)
        call = ToolCall(id=f"call_{next(calls)}", name=tool, arguments=arguments)
        _add_step(transcript, call, ToolResult(call=call, payload=payload))
    saved = request_module.get_project_context, request_module._project_notes, request_module.locale_code
    request_module.get_project_context = lambda: data["project_context"]
    request_module._project_notes = lambda: ""
    request_module.locale_code = lambda: locale
    try:
        step = request_module.build_step_request(transcript, loaded, list(history or []), dict(OVERRIDES))
    finally:
        request_module.get_project_context, request_module._project_notes, request_module.locale_code = saved
    messages = wire_messages(fold_live(step.messages), OVERRIDES["url_override"], False)
    return messages, step.tool_schemas


def tool_schemas(skill: str = "") -> list[dict[str, Any]]:
    return build(skill=skill, request="-")[1]


def _add_step(transcript: Transcript, call: ToolCall, result: ToolResult) -> None:
    transcript.add_turn(ModelTurn(text="", tool_calls=[call], protocol=PROTOCOL_NATIVE))
    transcript.add_results([result], PROTOCOL_NATIVE)


def _read(read: Any, data: dict[str, Any]) -> tuple[str, dict[str, Any], dict[str, Any]]:
    if isinstance(read, str):
        if ALGORITHM_SEPARATOR in read:
            return DESCRIBE_ALGORITHM, {"algorithm_id": read}, data[DESCRIBE_ALGORITHM][read]
        if FIELD_SEPARATOR in read:
            layer, field = read.split(FIELD_SEPARATOR, 1)
            payload = data[FIELD_VALUES][read]
            return FIELD_VALUES, {"layer_name": layer, "field_name": field}, payload
        return DESCRIBE_LAYER, {"layer_name": read}, data[DESCRIBE_LAYER][read]
    tool = str(read["tool"])
    arguments = dict(read.get("args") or {})
    payload = read.get("result")
    if payload is None:
        raise ValueError(f"The read {tool} {arguments} has no result and none is in the fixture")
    return tool, arguments, dict(payload)
