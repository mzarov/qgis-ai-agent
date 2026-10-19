from collections.abc import Sequence

from ai_agent.core.llm.turns import ToolCall
from ai_agent.core.settings import get_auto_apply
from ai_agent.qgis_tools.base import SAFETY_DESTRUCTIVE
from ai_agent.qgis_tools.registry import get_tool_by_name


def applies_itself(calls: Sequence[ToolCall]) -> bool:
    if not calls or not get_auto_apply():
        return False
    return all(_harmless(call) for call in calls)


def _harmless(call: ToolCall) -> bool:
    tool = get_tool_by_name(call.name)
    if tool is None:
        return False
    try:
        return tool.safety_for(call.arguments) != SAFETY_DESTRUCTIVE
    except Exception:
        return False
