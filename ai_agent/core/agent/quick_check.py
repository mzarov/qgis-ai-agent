"""The cheap check after Apply: a batch whose every step confirms itself by one read skips the model.

The full check is a model run of several requests, each carrying the whole
prompt and tool schemas; for a rename or a new bookmark it cost more than the
work itself. Each tool knows the one read that proves its own step
(`BaseTool.confirm_applied`). A failed step, a tool that cannot judge its
result, a step that does not read back, or a check that raises — any of them
sends the batch to the model as before.
"""

from typing import Any

from qgis.core import Qgis, QgsMessageLog

from ai_agent.qgis_tools.registry import get_tool_by_name

LOG_TAG = "AI Agent"


def confirmed_by_reading(results: list[Any]) -> bool:
    """True when every applied step read back as done, so the model's check can be skipped."""
    if not results:
        return False
    for result in results:
        if not result.ok or _verdict(result) is not True:
            return False
    QgsMessageLog.logMessage(
        f"Checked {len(results)} applied step(s) by reading; no model check needed.", LOG_TAG, Qgis.MessageLevel.Info
    )
    return True


def _verdict(result: Any) -> bool | None:
    tool = get_tool_by_name(result.call.name)
    if tool is None:
        return None
    try:
        verdict = tool.confirm_applied(dict(result.call.arguments), dict(result.payload))
    except Exception as err:
        QgsMessageLog.logMessage(
            f"Reading back {result.call.name} failed ({type(err).__name__}); the model checks instead.",
            LOG_TAG,
            Qgis.MessageLevel.Warning,
        )
        return None
    if verdict is False:
        QgsMessageLog.logMessage(
            f"{result.call.name} did not read back as applied; the model checks instead.",
            LOG_TAG,
            Qgis.MessageLevel.Warning,
        )
    return verdict
