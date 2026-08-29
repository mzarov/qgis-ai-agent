import unicodedata
from typing import Any

from ai_agent.i18n import tr
from ai_agent.qgis_tools.base import EGRESS_FEATURE_VALUES, SAFETY_DESTRUCTIVE, BaseTool
from ai_agent.qgis_tools.python.sandbox import MAX_LINES, run_snippet

MAX_CODE_CHARS = 6000
MAX_INTENT_CHARS = 240
SUMMARY_CHARS = 90


class RunPythonTool(BaseTool):
    name = "run_python"
    description = (
        "Run a PyQGIS snippet inside the running QGIS. The last resort for what "
        "no other tool covers — the whole QGIS API is reachable from here. "
        "Imports, files and the network are reachable too: this is not a security "
        "sandbox. The user sees the exact code in the confirmation and approves "
        "it before it runs, so keep it short and readable. Use print() to report "
        "results back."
    )
    skill = "python"
    safety = SAFETY_DESTRUCTIVE
    egress = EGRESS_FEATURE_VALUES
    constraints = [
        "Try the dedicated tools first — this one asks the user to read code",
        "print() what you want to see; the return value is not captured",
        (
            f"A best-effort current-thread trace interrupts after {MAX_LINES} "
            "Python lines; it is a runaway-work guard, not isolation"
        ),
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
            "description": (
                f"One plain-text line for the user: what this snippet does and why, up to {MAX_INTENT_CHARS} characters"
            ),
            "required": True,
        },
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        code = _checked_code(params.get("code"))
        intent = _checked_intent(params.get("intent"))
        prepared = dict(params)
        prepared["code"] = code
        prepared["intent"] = intent
        return prepared

    def summarize_call(self, params: dict[str, Any]) -> str:
        intent = _safe_intent_summary(params.get("intent"))
        if not intent:
            intent = str(params.get("code") or "").strip().replace("\n", " ")[:SUMMARY_CHARS]
        return tr("Running Python: {0}").format(intent)

    def detail_call(self, params: dict[str, Any]) -> str:
        return str(params.get("code") or "").strip()

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        code = _checked_code(params.get("code"))
        intent = _checked_intent(params.get("intent"))
        result = run_snippet(code)
        result["intent"] = intent
        return result


def _checked_intent(raw: Any) -> str:
    intent = str(raw or "").strip()
    if not intent:
        raise ValueError("intent is required: the user has to read what this snippet is for.")
    if len(intent) > MAX_INTENT_CHARS:
        raise ValueError(f"intent must not exceed {MAX_INTENT_CHARS} characters.")
    if any(unicodedata.category(character).startswith("C") for character in intent):
        raise ValueError("intent must be one plain-text line without control or formatting characters.")
    return intent


def _safe_intent_summary(raw: Any) -> str:
    intent = str(raw or "").strip()
    visible = "".join(" " if unicodedata.category(character).startswith("C") else character for character in intent)
    compact = " ".join(visible.split())
    if len(compact) > MAX_INTENT_CHARS:
        return compact[: MAX_INTENT_CHARS - 1].rstrip() + "…"
    return compact


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
