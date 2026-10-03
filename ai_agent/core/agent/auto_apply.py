"""Auto mode: which prepared batches apply themselves instead of waiting for the button.

Everything validated may apply at once — project edits, downloads, web reads —
except a batch holding a destructive step: deleting features, overwriting
files, `run_python`. Those always wait for the user, and the destructive
confirmation still follows the button.
"""

from typing import Any

from ai_agent.core.settings import get_auto_apply
from ai_agent.qgis_tools.base import SAFETY_DESTRUCTIVE
from ai_agent.qgis_tools.registry import get_tool_by_name


def applies_itself(calls: list[Any]) -> bool:
    """True when auto mode is on and no call in the batch is destructive (or unknown)."""
    if not calls or not get_auto_apply():
        return False
    return all(_harmless(call) for call in calls)


def _harmless(call: Any) -> bool:
    tool = get_tool_by_name(call.name)
    if tool is None:
        return False
    try:
        return tool.safety_for(call.arguments) != SAFETY_DESTRUCTIVE
    except Exception:
        return False
