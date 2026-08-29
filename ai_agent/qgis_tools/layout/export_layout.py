import os
from typing import Any

from qgis.core import QgsLayoutExporter

from ai_agent.i18n import tr
from ai_agent.qgis_tools.base import SAFETY_WRITE, BaseTool
from ai_agent.qgis_tools.layout.pages import find_layout

PDF = ".pdf"
PNG = ".png"
SUPPORTED = (PDF, PNG)


class ExportLayoutTool(BaseTool):
    name = "export_layout"
    description = (
        "Export a print layout to a file on disk: PDF or PNG, chosen by the "
        "path extension. This is how the finished map leaves QGIS."
    )
    skill = "layout"
    safety = SAFETY_WRITE
    constraints = [
        "The layout must exist",
        "The target folder must exist; the extension must be .pdf or .png",
    ]
    examples = ["Save the layout as /maps/city.pdf", "Export the sheet to PNG"]
    params_schema = [
        {
            "name": "layout_name",
            "type": "string",
            "description": "Layout name exactly as in list_layouts",
            "required": True,
        },
        {
            "name": "path",
            "type": "string",
            "description": "Target file path ending in .pdf or .png",
            "required": True,
        },
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        find_layout(params.get("layout_name") or "")
        path = _checked_path(params.get("path") or "")
        prepared = dict(params)
        prepared["path"] = path
        return prepared

    def summarize_call(self, params: dict[str, Any]) -> str:
        name = (params.get("layout_name") or "").strip()
        path = (params.get("path") or "").strip()
        return tr("Exporting layout '{0}' to {1}.").format(name, path)

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        layout = find_layout(params.get("layout_name") or "")
        path = _checked_path(params.get("path") or "")
        exporter = QgsLayoutExporter(layout)
        if path.lower().endswith(PDF):
            code = exporter.exportToPdf(path, QgsLayoutExporter.PdfExportSettings())
        else:
            code = exporter.exportToImage(path, QgsLayoutExporter.ImageExportSettings())
        if code != QgsLayoutExporter.ExportResult.Success:
            raise ValueError(f"QGIS could not export the layout to {path} (code {code}).")
        return {"layout": layout.name(), "path": path}


def _checked_path(raw: str) -> str:
    path = raw.strip()
    if not path.lower().endswith(SUPPORTED):
        raise ValueError(f"The path must end in {' or '.join(SUPPORTED)}, got '{path}'.")
    folder = os.path.dirname(path) or "."
    if not os.path.isdir(folder):
        raise ValueError(f"The folder '{folder}' does not exist — create it or pick another path.")
    return path
