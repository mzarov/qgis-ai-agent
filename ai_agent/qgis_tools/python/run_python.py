from typing import Any

from ai_agent.i18n import tr
from ai_agent.qgis_tools.base import SAFETY_DESTRUCTIVE, BaseTool
from ai_agent.qgis_tools.python.sandbox import MAX_LINES, run_snippet

MAX_CODE_CHARS = 6000
SUMMARY_CHARS = 90


class RunPythonTool(BaseTool):
    name = "run_python"
    description = (
        "Run a PyQGIS snippet inside the running QGIS. The last resort for what "
        "no other tool covers — the whole QGIS API is reachable from here. "
        "The user reads the exact code and confirms it before it runs, so keep "
        "it short and readable. Use print() to report results back."
    )
    skill = "python"
    safety = SAFETY_DESTRUCTIVE
    constraints = [
        "Try the dedicated tools first — this one asks the user to read code",
        "print() what you want to see; the return value is not captured",
        f"The snippet is stopped after {MAX_LINES} executed lines",
    ]
    examples = [
        "Set a custom blend mode on the roads layer",
        "Read a property that no describe tool returns",
    ]
    params_schema = [
        {
            "name": "code",
            "type": "string",
            "description": (
                "Python source. Ready names: project (QgsProject.instance()), "
                "iface, processing, and the Qgs* / Qt classes."
            ),
            "required": True,
        },
        {
            "name": "intent",
            "type": "string",
            "description": "One line for the user: what this snippet does and why",
            "required": True,
        },
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        code = _checked_code(params.get("code"))
        if not str(params.get("intent") or "").strip():
            raise ValueError("intent is required: the user has to read what this snippet is for.")
        prepared = dict(params)
        prepared["code"] = code
        return prepared

    def summarize_call(self, params: dict[str, Any]) -> str:
        intent = str(params.get("intent") or "").strip()
        if not intent:
            intent = str(params.get("code") or "").strip().replace("\n", " ")[:SUMMARY_CHARS]
        return tr("Running Python: {0}").format(intent)

    def detail_call(self, params: dict[str, Any]) -> str:
        return str(params.get("code") or "").strip()

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        code = _checked_code(params.get("code"))
        result = run_snippet(code)
        result["intent"] = str(params.get("intent") or "").strip()
        return result


def _checked_code(raw: Any) -> str:
    code = str(raw or "").strip()
    if not code:
        raise ValueError("code is empty — there is nothing to run.")
    if len(code) > MAX_CODE_CHARS:
        raise ValueError(
            f"The snippet is {len(code)} characters, over the limit of {MAX_CODE_CHARS}. "
            "Split it into steps the user can actually read."
        )
    try:
        compile(code, "<agent snippet>", "exec")
    except SyntaxError as broken:
        raise ValueError(f"The snippet does not parse: {broken.msg} (line {broken.lineno}).") from None
    return code
