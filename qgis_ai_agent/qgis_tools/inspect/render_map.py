import base64
from typing import Any

from qgis.core import QgsMapRendererParallelJob, QgsMapSettings
from qgis.PyQt.QtCore import QBuffer, QIODevice, QSize

from qgis_ai_agent.i18n import tr
from qgis_ai_agent.qgis_tools.base import RESULT_IMAGE_KEY, SAFETY_READ, BaseTool
from qgis_ai_agent.qgis_tools.common.layers import extent_dict, find_layer_by_name, safe_extent

DEFAULT_WIDTH = 900
MIN_WIDTH = 200
MAX_WIDTH = 1600
FALLBACK_RATIO = 0.75
MAX_IMAGE_BYTES = 4 * 1024 * 1024
IMAGE_FORMAT = "PNG"
LOOK_NOTE = "The rendered map is attached as an image. Look at it before judging colours, labels or layer visibility."


class RenderMapTool(BaseTool):
    name = "render_map"
    description = (
        "Render the current map view to an image and attach it to the reply, so "
        "the appearance can be judged by eye. Requires a model with vision. Call "
        "it after styling changes to check the visual result, or when the user "
        "asks what the map looks like."
    )
    skill = "inspect"
    safety = SAFETY_READ
    constraints = ["Needs the QGIS window; unavailable in headless runs"]
    examples = ["Show me what the map looks like now", "Check that the rivers really turned blue"]
    params_schema = [
        {
            "name": "layer_name",
            "type": "string",
            "description": "Frame this layer's extent instead of the current view",
            "required": False,
        },
        {
            "name": "width",
            "type": "integer",
            "description": f"Image width in pixels, {MIN_WIDTH}-{MAX_WIDTH} (default {DEFAULT_WIDTH})",
            "required": False,
        },
    ]

    def summarize_call(self, params: dict[str, Any]) -> str:
        layer_name = (params.get("layer_name") or "").strip()
        if not layer_name:
            return tr("Rendering the map to an image.")
        return tr("Rendering layer '{0}' to an image.").format(layer_name)

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        canvas = _require_canvas()
        settings = QgsMapSettings(canvas.mapSettings())
        layer_name = (params.get("layer_name") or "").strip()
        if layer_name:
            _frame_layer(canvas, settings, layer_name)
        width = _clamped_width(params.get("width"))
        settings.setOutputSize(QSize(width, _height_for(settings, width)))
        image = _rendered(settings)
        encoded = _encoded_png(image)
        return {
            "width": int(image.width()),
            "height": int(image.height()),
            "extent": extent_dict(settings.extent()),
            "note": LOOK_NOTE,
            RESULT_IMAGE_KEY: encoded,
        }


def _require_canvas() -> Any:
    try:
        from qgis.utils import iface

        canvas = iface.mapCanvas()
    except Exception:
        canvas = None
    if canvas is None:
        raise ValueError("The map is not available: the plugin is running without a QGIS window.")
    return canvas


def _frame_layer(canvas: Any, settings: Any, layer_name: str) -> None:
    layer = find_layer_by_name(layer_name)
    extent = safe_extent(layer)
    if extent is None or extent.isEmpty():
        raise ValueError(f"Layer '{layer.name()}' has no extent — it may be empty.")
    settings.setExtent(canvas.mapSettings().layerExtentToOutputExtent(layer, extent))


def _clamped_width(raw: Any) -> int:
    try:
        wanted = int(raw) if raw is not None else DEFAULT_WIDTH
    except (TypeError, ValueError):
        wanted = DEFAULT_WIDTH
    return max(MIN_WIDTH, min(MAX_WIDTH, wanted))


def _height_for(settings: Any, width: int) -> int:
    try:
        size = settings.outputSize()
        ratio = float(size.height()) / float(size.width())
    except Exception:
        ratio = FALLBACK_RATIO
    if not 0.1 <= ratio <= 10.0:
        ratio = FALLBACK_RATIO
    return max(1, int(width * ratio))


def _rendered(settings: Any) -> Any:
    job = QgsMapRendererParallelJob(settings)
    job.start()
    job.waitForFinished()
    return job.renderedImage()


def _encoded_png(image: Any) -> str:
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer, IMAGE_FORMAT):
        raise ValueError("QGIS could not encode the rendered map into an image.")
    data = bytes(buffer.data())
    buffer.close()
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError(
            f"The rendered image is {len(data) // 1024 // 1024} MB, over the limit of "
            f"{MAX_IMAGE_BYTES // 1024 // 1024} MB. Ask for a smaller width."
        )
    return base64.b64encode(data).decode("ascii")
