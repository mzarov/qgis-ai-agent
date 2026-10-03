"""Files the user hands to the chat: GIS data becomes layers, pictures go to the model.

Attaching is the user's own action, like dropping a file onto the QGIS canvas,
so data files are added straight away rather than queued for Apply; the model
then hears about the new layer through the @mention put into the request.
"""

import os
from dataclasses import dataclass, field

from qgis.core import Qgis, QgsMessageLog
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QImage

from ai_agent.qgis_tools.common.images import encoded_png
from ai_agent.qgis_tools.project.tree import layer_names
from ai_agent.qgis_tools.registry import get_tool_by_name

LOG_TAG = "AI Agent"
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")
# A georeferenced picture is data: its world file or aux file says where it lies.
GEOREFERENCE_SUFFIXES = (".pgw", ".jgw", ".wld", ".tfw", ".png.aux.xml", ".jpg.aux.xml")
MAX_IMAGE_SIDE = 1568
ADD_LAYER = "add_layer"
LOAD_TABLE = "load_table"
# A delimited table goes through load_table, which turns lon/lat columns into
# points; add_layer stays the fallback for anything load_table refuses.
TABLE_SUFFIXES = (".csv", ".tsv", ".txt")
DUPLICATE_NAME = "{0} ({1})"


@dataclass
class Outcome:
    added: list[str] = field(default_factory=list)
    images: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    # Tables added without geometry because load_table refused them, with its reason.
    plain_tables: list[tuple[str, str]] = field(default_factory=list)


def is_picture(path: str) -> bool:
    """A plain picture for the model's eyes, not a raster that knows where it lies."""
    lower = path.lower()
    if not lower.endswith(IMAGE_SUFFIXES):
        return False
    stem = os.path.splitext(path)[0]
    return not any(os.path.exists(stem + suffix) or os.path.exists(path + suffix) for suffix in GEOREFERENCE_SUFFIXES)


def attach(paths: list[str]) -> Outcome:
    """Add every data file as a layer and set the pictures aside; nothing here raises."""
    outcome = Outcome()
    for path in paths:
        if not os.path.isfile(path):
            outcome.failed.append((path, "not a file"))
        elif is_picture(path):
            outcome.images.append(path)
        else:
            _add_layer(path, outcome)
    return outcome


def encode_picture(path: str) -> str:
    """The picture as base64 PNG, its longer side capped so a phone photo does not cost a fortune."""
    image = QImage(path)
    if image.isNull():
        raise ValueError("QGIS could not read the picture.")
    if max(image.width(), image.height()) > MAX_IMAGE_SIDE:
        image = image.scaled(
            MAX_IMAGE_SIDE,
            MAX_IMAGE_SIDE,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    return encoded_png(image)


def _add_layer(path: str, outcome: Outcome) -> None:
    name = _free_name(os.path.splitext(os.path.basename(path))[0] or path)
    error: Exception = ValueError("the add_layer tool is missing")
    refused = ""
    for tool_name, params in _attempts(path, name):
        tool = get_tool_by_name(tool_name)
        if tool is None:
            continue
        try:
            tool.execute(tool.prepare(params))
        except Exception as failure:
            QgsMessageLog.logMessage(f"Attaching {path} failed: {failure}", LOG_TAG, Qgis.MessageLevel.Warning)
            error = failure
            refused = refused or (str(failure) if tool_name == LOAD_TABLE else "")
            continue
        outcome.added.append(name)
        if refused:
            outcome.plain_tables.append((path, refused))
        return
    outcome.failed.append((path, str(error)))


def _attempts(path: str, name: str) -> list[tuple[str, dict[str, str]]]:
    plain = (ADD_LAYER, {"source": path, "name": name})
    if path.lower().endswith(TABLE_SUFFIXES):
        return [(LOAD_TABLE, {"path": path, "name": name}), plain]
    return [plain]


def _free_name(wanted: str) -> str:
    taken = set(layer_names())
    if wanted not in taken:
        return wanted
    number = 2
    while DUPLICATE_NAME.format(wanted, number) in taken:
        number += 1
    return DUPLICATE_NAME.format(wanted, number)
