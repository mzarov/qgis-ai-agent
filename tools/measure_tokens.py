"""Estimate what one scripted agent task costs in prompt tokens.

The script replays a fixed task (a graduated statistics map from one shapefile,
followed by the verification run) through the real request builder, so every
prompt, skill body and tool schema is the one the plugin would send. Model
turns and tool results are canned. Numbers are character counts divided by
four: good for comparing two versions of the plugin, not for billing.

Two figures matter:
- sent: every input token of every request;
- uncached: the part of each request that differs from the previous one. A
  provider with prefix caching (Anthropic breakpoints, OpenAI, DeepSeek) only
  bills the cached rest at a fraction of the price, so this is what a stable
  prefix saves.

Run: python3 tools/measure_tokens.py
"""

import json
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tests  # noqa: E402,F401  installs the qgis stub when QGIS is absent
from ai_agent.core.agent import request as request_module  # noqa: E402
from ai_agent.core.agent.loop import PRELOADED_SKILLS  # noqa: E402
from ai_agent.core.agent.prompts import (  # noqa: E402
    build_verification_prompt,
    render_queued_steps,
    render_task_plan,
)
from ai_agent.core.agent.skills import extend_loaded  # noqa: E402
from ai_agent.core.agent.transcript import ToolResult, Transcript  # noqa: E402
from ai_agent.core.llm import anthropic  # noqa: E402
from ai_agent.core.llm.transport import PROTOCOL_NATIVE, ModelTurn, ToolCall  # noqa: E402
from ai_agent.qgis_tools.registry import summarize_tool_call  # noqa: E402

CHARS_PER_TOKEN = 4
CACHED_PRICE = 0.1
OVERRIDES = {
    "url_override": "https://api.anthropic.com/v1",
    "model_override": "claude-x",
    "key_override": "k",
    "auth_type_override": "bearer",
    "dialect_override": "anthropic",
    "verify_override": True,
}
CONTEXT_BEFORE = (
    "Project CRS: EPSG:3857.\nActive layer: districts.\n"
    "Layers: districts (polygon, EPSG:4326, 87 features), OpenStreetMap (raster, EPSG:3857)."
)
CONTEXT_AFTER = CONTEXT_BEFORE.replace("Layers: ", "Layers: districts_density (polygon, EPSG:4326, 87 features), ")
REQUEST = "Make a statistics map: population density by district from districts.shp, graduated colours."
FIELDS = [
    {"name": name, "type": kind}
    for name, kind in [
        ("OBJECTID", "Integer64"),
        ("NAME", "String"),
        ("NAME_EN", "String"),
        ("OKATO", "String"),
        ("POP2020", "Integer64"),
        ("AREA_KM2", "Real"),
        ("ADMIN_LVL", "Integer"),
        ("PARENT", "String"),
    ]
]
DESCRIBE = {
    "name": "districts",
    "kind": "vector",
    "geometry": "polygon",
    "crs": "EPSG:4326",
    "crs_is_geographic": True,
    "feature_count": 87,
    "fields": FIELDS,
    "extent": [37.3, 55.5, 37.9, 55.9],
    "source": "/data/districts.shp",
    "is_valid": True,
    "subset_filter": "",
    "sample": [{field["name"]: f"value {index}" for field in FIELDS} for index in range(5)],
}
STATS = {"expression": "POP2020", "count": 87, "min": 1203, "max": 251340, "mean": 48211.4, "sum": 4194392}
SEARCH = {
    "matches": [
        {"id": f"native:alg{index}", "name": f"Algorithm number {index}", "group": "Vector table"}
        for index in range(15)
    ]
}
DESCRIBE_ALG = {
    "id": "native:fieldcalculator",
    "parameters": [
        {"name": f"PARAM_{index}", "type": "string", "description": "A parameter with a long description " * 3}
        for index in range(10)
    ],
}


CALL_IDS = iter(range(1, 10_000))


def call(tool: str, **arguments: Any) -> ToolCall:
    return ToolCall(id=f"call_{next(CALL_IDS)}", name=tool, arguments=arguments)


QUEUED = {"status": "queued"}
APPLYING_RUN = [
    [
        (call("update_plan", steps=["read data", "compute density", "classify", "label"]), {"ok": True}),
        (call("load_skill", names=["style", "processing"]), "SKILL"),
        (call("describe_layer", layer_name="districts"), DESCRIBE),
    ],
    [(call("query_layer", layer_name="districts", aggregate="stats", expression="POP2020"), STATS)],
    [(call("search_processing", query="field calculator"), SEARCH)],
    [(call("describe_processing", algorithm_id="native:fieldcalculator"), DESCRIBE_ALG)],
    [
        (
            call(
                "run_processing",
                algorithm_id="native:fieldcalculator",
                parameters={"INPUT": "districts", "FIELD_NAME": "density", "FORMULA": '"POP2020" / "AREA_KM2"'},
                output_name="districts_density",
            ),
            QUEUED,
        ),
        (call("update_plan", steps=["read data", "compute density", "classify", "label"], done=2), {"ok": True}),
    ],
    [(call("apply_now", reason="the density layer must exist before classification"), "APPLY")],
    [(call("describe_layer", layer_name="districts_density"), DESCRIBE)],
    [(call("query_layer", layer_name="districts_density", aggregate="stats", expression="density"), STATS)],
    [
        (
            call("set_graduated", layer_name="districts_density", field="density", classes=5, ramp="Viridis"),
            QUEUED,
        )
    ],
    [
        (call("set_labels", layer_name="districts_density", field="NAME"), QUEUED),
        (call("update_plan", steps=["read data", "compute density", "classify", "label"], done=4), {"ok": True}),
    ],
]
VERIFICATION_RUN = [
    [
        (call("load_skill", names=["style"]), "SKILL"),
        (call("describe_style", layer_name="districts_density"), DESCRIBE),
    ],
    [(call("render_map", layer_name="districts_density"), {"ok": True, "width": 800})],
    [(call("reorder_layers", order=["districts_density", "OpenStreetMap"]), QUEUED)],
]
FINAL_TEXT = "I propose a graduated density map in five classes with district names as labels. " * 4


class Meter:
    def __init__(self) -> None:
        self.previous = ""
        self.requests = 0
        self.sent = 0
        self.uncached = 0

    def measure(self, messages: list[dict[str, Any]], schemas: list[dict[str, Any]], prefix: int) -> None:
        body = anthropic.build_body(messages, schemas, "claude-x", cache_prefix_chars=prefix)
        text = _without_cache_marks(body.get("tools", [])) + _without_cache_marks(body.get("system", ""))
        text += _without_cache_marks(body["messages"])
        common = os.path.commonprefix([self.previous, text])
        self.requests += 1
        self.sent += len(text)
        self.uncached += len(text) - len(common)
        self.previous = text


def _without_cache_marks(value: Any) -> str:
    return json.dumps(_strip(value), ensure_ascii=False)


def _strip(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _strip(item) for key, item in value.items() if key != "cache_control"}
    if isinstance(value, list):
        return [_strip(item) for item in value]
    return value


def run(
    meter: Meter, prompt: str, turns: list, history: list[dict[str, str]], skills: list[str]
) -> tuple[list[str], list[str]]:
    transcript = Transcript()
    transcript.add_user(prompt)
    loaded = list(skills)
    queued: list[ToolCall] = []
    plan: tuple[list[str], int] = ([], 0)
    context = [CONTEXT_BEFORE]
    request_module.get_project_context = lambda: context[0]
    steps = [[pair for pair in turn if not _redundant_load(pair[0], loaded)] for turn in turns]
    for turn in [turn for turn in steps if turn] + [[]]:
        request = request_module.build_step_request(
            transcript,
            loaded,
            history,
            dict(OVERRIDES),
            render_task_plan(*plan),
            render_queued_steps([summarize_tool_call(item.name, item.arguments) for item in queued]),
        )
        meter.measure(request.messages, request.tool_schemas, int(request.overrides.get(anthropic.CACHE_PREFIX_KEY, 0)))
        calls = [pair[0] for pair in turn]
        transcript.add_turn(ModelTurn(text="" if calls else FINAL_TEXT, tool_calls=calls, protocol=PROTOCOL_NATIVE))
        results = []
        for tool_call, payload in turn:
            if payload == "SKILL":
                for name in tool_call.arguments["names"]:
                    extend_loaded(loaded, name)
                payload = {"loaded": tool_call.arguments["names"], "tools": ["a_tool"] * 8}
            elif payload == "APPLY":
                payload = {"applied": [{"tool": item.name, "ok": True} for item in queued]}
                queued = []
                context[0] = CONTEXT_AFTER
            elif payload is QUEUED:
                queued.append(tool_call)
            if tool_call.name == "update_plan":
                plan = (tool_call.arguments["steps"], tool_call.arguments.get("done", 0))
            results.append(ToolResult(call=tool_call, payload=dict(payload)))
        transcript.add_results(results, PROTOCOL_NATIVE)
    return loaded, [item.name for item in queued]


def _redundant_load(tool_call: ToolCall, loaded: list[str]) -> bool:
    return tool_call.name == "load_skill" and set(tool_call.arguments.get("names", [])) <= set(loaded)


def measure() -> dict[str, float]:
    saved = request_module.get_project_context, request_module._project_notes
    request_module._project_notes = lambda: ""
    try:
        meter = Meter()
        preloaded = list(PRELOADED_SKILLS)
        loaded, applied = run(meter, REQUEST, APPLYING_RUN, [], preloaded)
        history = [{"role": "user", "content": REQUEST}, {"role": "assistant", "content": FINAL_TEXT}]
        outcomes = [{"tool": name, "ok": True} for name in applied]
        run(meter, build_verification_prompt(outcomes), VERIFICATION_RUN, history, loaded)
    finally:
        request_module.get_project_context, request_module._project_notes = saved
    sent = meter.sent / CHARS_PER_TOKEN
    uncached = meter.uncached / CHARS_PER_TOKEN
    return {
        "requests": meter.requests,
        "sent": sent,
        "uncached": uncached,
        "effective": uncached + (sent - uncached) * CACHED_PRICE,
    }


def main() -> None:
    numbers = measure()
    print(f"requests:            {numbers['requests']:.0f}")
    print(f"input tokens sent:   {numbers['sent']:,.0f}")
    print(f"uncached tokens:     {numbers['uncached']:,.0f}")
    print(f"effective (cache):   {numbers['effective']:,.0f}")


if __name__ == "__main__":
    main()
