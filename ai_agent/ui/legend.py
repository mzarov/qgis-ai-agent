"""A restyled layer's legend in the feed, after the design handoff: colour cells with what each one means.

Classes that run in order (graduated, a raster ramp) are one strip of cells,
10 px high with 2 px between them and their bounds under each in 11 px; a strip
of more cells than fit their words, and categories, are rows of a swatch and a
label. The spec comes from the style tool that changed the layer
(`qgis_tools/style/legend.py`) and never reaches the model.
"""

from typing import Any

from qgis.PyQt.QtCore import QRectF, Qt
from qgis.PyQt.QtGui import QColor, QFontMetrics, QPainter, QPen
from qgis.PyQt.QtWidgets import QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget

from ai_agent.i18n import tr_n
from ai_agent.ui import controls, style
from ai_agent.ui.chart_scale import compact

RANGES = "ranges"
CELL_HEIGHT = 10
CELL_GAP = 2
CELL_RADIUS = 2
# A cell no wider than the handoff draws it in a narrow panel: a wide panel does not stretch the scale.
MAX_CELL_WIDTH = 72
LABEL_GAP = 4
MAX_STRIP_CELLS = 7
SWATCH = 10
ROW_SPACING = 4
COLUMN_SPACING = 6
CAPTION_SCALE = 11 / 13
TITLE_SCALE = 12 / 13
BOUNDS = "{0}–{1}"


def item_label(item: dict[str, Any]) -> str:
    """A class's words: its bounds, compact (20k–35k), when it has them; else its label."""
    low, high = item.get("low"), item.get("high")
    if isinstance(low, (int, float)) and isinstance(high, (int, float)):
        return BOUNDS.format(compact(low), compact(high))
    return str(item.get("label") or "")


class LegendCard(QWidget):
    def __init__(self, spec: dict[str, Any], parent: QWidget | None = None):
        super().__init__(parent)
        palette = self.palette()
        self.spec = spec
        self.items = [item for item in spec.get("items") or [] if isinstance(item, dict)]
        self.as_strip = spec.get("kind") == RANGES and len(self.items) <= MAX_STRIP_CELLS
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(COLUMN_SPACING)
        title = controls.ElidedLabel(str(spec.get("title") or ""))
        style.scale_font(title, TITLE_SCALE)
        style.ink(title, style.muted(palette))
        column.addWidget(title)
        if self.as_strip:
            column.addWidget(LegendStrip(self.items, palette))
        else:
            for item in self.items:
                column.addWidget(_row(item, palette))
        more = int(spec.get("more") or 0)
        if more:
            column.addWidget(controls.small(tr_n("+%n more item(s)", more), palette))

    def plain_text(self) -> str:
        return str(self.spec.get("title") or "")


class LegendStrip(QWidget):
    """Ordered classes as one strip of cells, each with its bounds under it, elided to the cell."""

    def __init__(self, items: list[dict[str, Any]], palette: Any, parent: QWidget | None = None):
        super().__init__(parent)
        self.items = items
        self.labels = [item_label(item) for item in items]
        self._ink = style.faint(palette)
        self._blank = style.hairline(palette)
        # The palest class of a ramp is near the backdrop's colour: a hairline keeps its cell in sight.
        self._edge = style.hairline(palette)
        style.scale_font(self, CAPTION_SCALE)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(CELL_HEIGHT + LABEL_GAP + QFontMetrics(self.font()).height())

    def cell_width(self) -> float:
        count = max(1, len(self.items))
        return max(1.0, min(MAX_CELL_WIDTH, (self.width() - CELL_GAP * (count - 1)) / count))

    def paintEvent(self, _event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        metrics = painter.fontMetrics()
        width = self.cell_width()
        for index, (item, label) in enumerate(zip(self.items, self.labels, strict=False)):
            left = index * (width + CELL_GAP)
            painter.setPen(QPen(self._edge, style.HAIRLINE))
            painter.setBrush(_colour(item, self._blank))
            cell = QRectF(left, 0, width, CELL_HEIGHT).adjusted(0.5, 0.5, -0.5, -0.5)
            painter.drawRoundedRect(cell, CELL_RADIUS, CELL_RADIUS)
            painter.setPen(self._ink)
            shown = metrics.elidedText(label, Qt.TextElideMode.ElideRight, int(width))
            text_box = QRectF(left, CELL_HEIGHT + LABEL_GAP, width, metrics.height())
            painter.drawText(text_box, int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop), shown)
        painter.end()


def _colour(item: dict[str, Any], blank: QColor) -> QColor:
    """The class's colour; a missing or unreadable one is drawn as a blank hairline cell."""
    colour = QColor(str(item.get("color") or ""))
    return colour if colour.isValid() else blank


def _row(item: dict[str, Any], palette: Any) -> QWidget:
    row = QWidget()
    line = QHBoxLayout(row)
    line.setContentsMargins(0, 0, 0, 0)
    line.setSpacing(ROW_SPACING + 4)
    swatch = controls.PaintedSwatch(SWATCH, _colour(item, style.hairline(palette)).name(), style.hairline(palette))
    line.addWidget(swatch, 0, Qt.AlignmentFlag.AlignVCenter)
    label = controls.ElidedLabel(item_label(item))
    style.scale_font(label, CAPTION_SCALE)
    style.ink(label, style.muted(palette))
    line.addWidget(label, 1)
    return row
