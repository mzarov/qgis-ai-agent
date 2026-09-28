from typing import Any

from qgis.core import QgsLayoutExporter
from qgis.PyQt.QtCore import QSize

from ai_agent.i18n import tr
from ai_agent.qgis_tools.base import EGRESS_IMAGE, RESULT_IMAGE_KEY, SAFETY_READ, BaseTool
from ai_agent.qgis_tools.common.images import encoded_png
from ai_agent.qgis_tools.layout.pages import current_page_mm, find_layout

DEFAULT_WIDTH = 900
MIN_WIDTH = 300
MAX_WIDTH = 1600
FIRST_PAGE = 0
LOOK_NOTE = (
    "The rendered layout page is attached as an image. Look at it: check that "
    "nothing overlaps, nothing sticks out of the page and the composition reads "
    "well before calling the layout done."
)


class RenderLayoutTool(BaseTool):
    name = "render_layout"
    description = (
        "Render the first page of a print layout to an image and attach it, so "
        "the composition can be judged by eye. Requires a model with vision. "
        "Call it after building or changing a layout."
    )
    skill = "layout"
    safety = SAFETY_READ
    external_effect = False
    network_access = False
    egress = EGRESS_IMAGE
    constraints = ["The layout must exist (see list_layouts)"]
    examples = ["Show me the layout", "Check that the legend does not cover the map"]
    params_schema = [
        {
            "name": "layout_name",
            "type": "string",
            "description": "Layout name exactly as in list_layouts",
            "required": True,
        },
        {
            "name": "width",
            "type": "integer",
            "description": f"Image width in pixels, {MIN_WIDTH}-{MAX_WIDTH} (default {DEFAULT_WIDTH})",
            "required": False,
        },
    ]

    def summarize_call(self, params: dict[str, Any]) -> str:
        name = (params.get("layout_name") or "").strip()
        return tr("Rendering layout '{0}' to an image.").format(name)

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        layout = find_layout(params.get("layout_name") or "")
        width = _clamped_width(params.get("width"))
        page_width, page_height = current_page_mm(layout)
        height = max(1, int(width * page_height / max(page_width, 1.0)))
        image = QgsLayoutExporter(layout).renderPageToImage(FIRST_PAGE, QSize(width, height))
        if image is None or image.isNull():
            raise ValueError(f"QGIS could not render layout '{layout.name()}'.")
        return {
            "name": layout.name(),
            "width": int(image.width()),
            "height": int(image.height()),
            "note": LOOK_NOTE,
            RESULT_IMAGE_KEY: encoded_png(image),
        }


def _clamped_width(raw: Any) -> int:
    try:
        wanted = int(raw) if raw is not None else DEFAULT_WIDTH
    except (TypeError, ValueError):
        wanted = DEFAULT_WIDTH
    return max(MIN_WIDTH, min(MAX_WIDTH, wanted))
