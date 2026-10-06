from typing import Any

from ai_agent.i18n import tr
from ai_agent.qgis_tools.base import EGRESS_METADATA, SAFETY_READ, BaseTool
from ai_agent.qgis_tools.charts.spec import KINDS, attach, chart


class ShowChartTool(BaseTool):
    name = "show_chart"
    description = (
        "Draw a chart in the chat from numbers you already have: bar, line, pie, scatter or "
        "histogram. For numbers that still sit in a layer, chart_layer computes and draws in one step."
    )
    skill = "charts"
    safety = SAFETY_READ
    egress = EGRESS_METADATA
    external_effect = False
    network_access = False
    constraints = ["One y scale: never mix measures of different units in one chart", "At most 4 series"]
    examples = ["Plot these yearly totals as a line", "Compare the two scenarios as bars"]
    params_schema = [
        {"name": "kind", "type": "string", "description": "Chart type", "enum": list(KINDS)},
        {"name": "title", "type": "string", "description": "What the chart shows, with the unit"},
        {
            "name": "labels",
            "type": "array",
            "items": {"type": "string"},
            "description": "Category names or x values, one per value; not used for scatter",
            "required": False,
        },
        {
            "name": "series",
            "type": "array",
            "items": {"type": "object"},
            "description": ('Series: [{"name": "2020", "values": [3, 5, 2]}]; scatter adds "x": [..] to each series'),
        },
        {"name": "x_label", "type": "string", "description": "Horizontal axis title", "required": False},
        {"name": "y_label", "type": "string", "description": "Vertical axis title", "required": False},
        {
            "name": "unit",
            "type": "string",
            "description": "Unit of the values, e.g. 'people', 'km²'",
            "required": False,
        },
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        _spec(params)
        return params

    def summarize_call(self, params: dict[str, Any]) -> str:
        return tr("Drawing a chart: {0}.").format(str(params.get("title") or "").strip())

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        spec = _spec(params)
        return attach({"shown": "chart", "title": spec["title"], "categories": len(spec["labels"])}, spec)


def _spec(params: dict[str, Any]) -> dict[str, Any]:
    labels = params.get("labels") or []
    series = params.get("series") or []
    if not isinstance(labels, list) or not isinstance(series, list):
        raise ValueError("labels and series are lists.")
    return chart(
        str(params.get("kind") or ""),
        str(params.get("title") or ""),
        [str(label) for label in labels],
        series,
        str(params.get("x_label") or ""),
        str(params.get("y_label") or ""),
        str(params.get("unit") or ""),
    )
