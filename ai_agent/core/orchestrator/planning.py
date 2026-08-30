from typing import Any

from ai_agent.i18n import tr
from ai_agent.qgis_tools.base import SAFETY_DESTRUCTIVE
from ai_agent.qgis_tools.registry import get_tool_by_name, summarize_tool_call

EFFECT_SNAPSHOT = tr("project snapshot available")
EFFECT_EXTERNAL = tr("writes outside the project; Undo does not restore it")
EFFECT_NETWORK = tr("contacts an external service after confirmation")
EFFECT_IRREVERSIBLE = tr("may be irreversible; extra confirmation required")


def plan_line(call: Any) -> str:
    summary = summarize_tool_call(call.name, call.arguments)
    tool = get_tool_by_name(call.name)
    if tool is None:
        return summary
    risk = tool.safety_for(call.arguments)
    if tool.has_network_access(call.arguments):
        effect = EFFECT_NETWORK
    elif tool.has_external_effect(call.arguments):
        effect = EFFECT_EXTERNAL
    elif risk == SAFETY_DESTRUCTIVE:
        effect = EFFECT_IRREVERSIBLE
    else:
        effect = EFFECT_SNAPSHOT
    return f"{summary} · {effect}"


def destructive_lines(calls: list[Any]) -> tuple[list[str], str]:
    lines = []
    details = []
    for call in calls:
        tool = get_tool_by_name(call.name)
        if tool is None or tool.safety_for(call.arguments) != SAFETY_DESTRUCTIVE:
            continue
        lines.append(summarize_tool_call(call.name, call.arguments))
        try:
            detail = tool.detail_call(call.arguments)
        except Exception:
            detail = ""
        if detail:
            details.append(detail)
    return lines, "\n\n".join(details)
