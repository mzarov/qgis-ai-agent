from typing import Any

from qgis.core import Qgis, QgsMessageLog

from ai_agent.qgis_tools.registry import get_tool_by_name

LOG_TAG = "AI Agent"


def confirmed_by_reading(results: list[Any]) -> bool:
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
