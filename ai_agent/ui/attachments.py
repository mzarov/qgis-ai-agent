"""Attachments in the composer: the file pickers behind +, and the pictures waiting to be sent.

Data files never stop here — the orchestrator adds them as layers at once and
mentions them in the request. Only pictures wait, as chips above the text,
until the next request takes them.
"""

import os
from typing import Any

from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QPixmap
from qgis.PyQt.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QToolButton, QWidget

from ai_agent.i18n import tr
from ai_agent.ui import controls, style

DATA = "data"
PICTURE = "picture"
DATA_FILTER = tr("GIS data (*.gpkg *.shp *.geojson *.json *.kml *.gml *.gpx *.csv *.tab *.tif *.tiff *.asc *.vrt)")
PICTURE_FILTER = tr("Pictures (*.png *.jpg *.jpeg *.webp *.gif *.bmp)")
DATA_TITLE = tr("Add data to the project")
PICTURE_TITLE = tr("Attach a picture for the model")
REMOVE = tr("Remove")
# The same chip as the active layer's: 22 px, a 4 px corner, small muted text.
CHIP_RADIUS = 4
CHIP_HEIGHT = 22
THUMB = 16
ICON = 12
CLOSE_RADIUS = 3
TEXT_SCALE = 12 / 13
NAME_WIDTH = 160
CHIP_GAP = 6


def choose_files(parent: QWidget, kind: str) -> list[str]:
    """Ask for files of one kind; an empty list when the dialog was cancelled."""
    title, wanted = (PICTURE_TITLE, PICTURE_FILTER) if kind == PICTURE else (DATA_TITLE, DATA_FILTER)
    paths, _chosen = QFileDialog.getOpenFileNames(parent, title, "", wanted)
    return [path for path in paths if path]


def local_files(mime: Any) -> list[str]:
    """Local file paths from a drag, or nothing when it carries anything else."""
    if not mime.hasUrls():
        return []
    urls = mime.urls()
    if not urls or not all(url.isLocalFile() for url in urls):
        return []
    return [url.toLocalFile() for url in urls]


def chip_close(tooltip: str, palette: Any) -> QToolButton:
    """The × at the end of a chip, this one's or the active layer's."""
    return controls.icon_button(
        "close", "×", tooltip, style.faint(palette), palette, CHIP_HEIGHT - 4, ICON, CLOSE_RADIUS
    )


class AttachmentChip(controls.RoundedFrame):
    removed = pyqtSignal(str)

    def __init__(self, path: str, palette: Any, parent: QWidget | None = None):
        super().__init__(CHIP_RADIUS, parent)
        self.path = path
        self.setFixedHeight(CHIP_HEIGHT)
        self.set_look(style.card(palette).name(), style.hairline(palette).name())
        line = QHBoxLayout(self)
        line.setContentsMargins(3, 0, 2, 0)
        line.setSpacing(5)
        thumb = QLabel()
        thumb.setFixedSize(THUMB, THUMB)
        picture = QPixmap(path)
        if not picture.isNull():
            thumb.setPixmap(
                picture.scaled(
                    THUMB, THUMB, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
                )
            )
        line.addWidget(thumb)
        name = controls.ElidedLabel(os.path.basename(path), mode=Qt.TextElideMode.ElideMiddle)
        style.scale_font(name, TEXT_SCALE)
        # An eliding label claims no width of its own: give it the name's, up to a cap.
        name.setFixedWidth(min(NAME_WIDTH, name.fontMetrics().horizontalAdvance(name.text()) + 2))
        style.ink(name, style.muted(palette))
        line.addWidget(name)
        close = chip_close(REMOVE, palette)
        close.clicked.connect(lambda: self.removed.emit(self.path))
        line.addWidget(close)


class AttachmentChips(QWidget):
    """The pictures waiting for the next request; hidden while there are none."""

    changed = pyqtSignal()

    def __init__(self, palette: Any, parent: QWidget | None = None):
        super().__init__(parent)
        self._palette = palette
        self._chips: list[AttachmentChip] = []
        self._line = QHBoxLayout(self)
        self._line.setContentsMargins(0, 0, 0, 2)
        self._line.setSpacing(CHIP_GAP)
        self._line.addStretch(1)
        self.setVisible(False)

    @property
    def paths(self) -> list[str]:
        return [chip.path for chip in self._chips]

    def add(self, path: str) -> None:
        if path in self.paths:
            return
        chip = AttachmentChip(path, self._palette)
        chip.removed.connect(self.remove)
        self._chips.append(chip)
        self._line.insertWidget(len(self._chips) - 1, chip)
        self.setVisible(True)
        self.changed.emit()

    def remove(self, path: str) -> None:
        for chip in [chip for chip in self._chips if chip.path == path]:
            self._chips.remove(chip)
            self._line.removeWidget(chip)
            chip.hide()
            # Deleted later: the chip's own button is still inside its clicked signal.
            chip.deleteLater()
        self.setVisible(bool(self._chips))
        self.changed.emit()

    def take(self) -> list[str]:
        paths = self.paths
        for path in paths:
            self.remove(path)
        return paths
