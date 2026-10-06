"""A chart in the feed, painted with QPainter: bars, lines, a donut, a histogram or a scatter.

The spec arrives as plain JSON from a read tool. Marks follow the data-viz
rules: thin bars with rounded data ends and a surface gap between them, 2 px
lines, 8 px markers ringed by the surface, recessive grid and axes, a legend
only for two series or more, and one direct label — on the largest value;
every other value is a hover away. Text always wears text colours, never the
series colour. Right click copies the picture or the numbers.
"""

import csv
import io
import math
from typing import Any

from qgis.PyQt.QtCore import QPointF, QRectF, Qt
from qgis.PyQt.QtGui import QColor, QFontMetrics, QGuiApplication, QPainter, QPainterPath, QPen
from qgis.PyQt.QtWidgets import QSizePolicy, QToolTip, QWidget

from ai_agent.i18n import tr
from ai_agent.ui import chart_scale, controls, style

CHART_HEIGHT = 240
PIE_HEIGHT = 210
ROW_HEIGHT = 22
TITLE_GAP = 8
LEGEND_HEIGHT = 20
AXIS_GAP = 6
BAR_RADIUS = 4
MARK_GAP = 2
LINE_WIDTH = 2
MARKER = 8
MARKER_LIMIT = 30
LEGEND_SWATCH = 10
DONUT_HOLE = 0.58
PIE_LEGEND_SHARE = 0.48
PIE_LEGEND_WIDTH = 240
MAX_BAR = 44
# Room between a row label and its bar; elision gets half of it as slack for rounding.
LABEL_ROOM = 14
COPY_IMAGE = tr("Copy image")
COPY_DATA = tr("Copy data as CSV")


class ChartCard(QWidget):
    def __init__(self, spec: dict[str, Any], parent: QWidget | None = None):
        super().__init__(parent)
        self.spec = spec
        self.kind = str(spec.get("kind") or "bar")
        self.labels = [str(label) for label in spec.get("labels") or []]
        self.series = list(spec.get("series") or [])
        self.unit = str(spec.get("unit") or "")
        self._hits: list[tuple[QRectF, str]] = []
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(self._height())

    def plain_text(self) -> str:
        return str(self.spec.get("title") or "")

    def horizontal(self) -> bool:
        return self.kind == "bar" and chart_scale.horizontal_bars(self.labels, len(self.series))

    def _height(self) -> int:
        if self.kind == "pie":
            return PIE_HEIGHT
        if self.horizontal():
            legend = LEGEND_HEIGHT if len(self.series) > 1 else 0
            return self._title_height() + legend + ROW_HEIGHT * len(self.labels) * len(self.series) + 2 * AXIS_GAP + 24
        return CHART_HEIGHT

    def _title_height(self) -> int:
        return QFontMetrics(self._title_font()).height() + TITLE_GAP

    def _title_font(self) -> Any:
        font = self.font()
        font.setBold(True)
        return font

    def _small_font(self) -> Any:
        font = self.font()
        font.setPointSizeF(max(1.0, font.pointSizeF() * controls.SMALL_SCALE))
        return font

    # Painting

    def paintEvent(self, _event: Any) -> None:
        self._hits = []
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        palette = self.palette()
        area = QRectF(self.rect())
        painter.setFont(self._title_font())
        painter.setPen(style.text(palette))
        title = QFontMetrics(self._title_font()).elidedText(
            str(self.spec.get("title") or ""), Qt.TextElideMode.ElideRight, int(area.width())
        )
        painter.drawText(QRectF(area.left(), area.top(), area.width(), self._title_height()), 0, title)
        area.setTop(area.top() + self._title_height())
        painter.setFont(self._small_font())
        if len(self.series) > 1:
            self._legend(painter, QRectF(area.left(), area.top(), area.width(), LEGEND_HEIGHT))
            area.setTop(area.top() + LEGEND_HEIGHT)
        if self.kind == "pie":
            self._pie(painter, area)
        elif self.kind == "scatter":
            self._scatter(painter, area)
        elif self.horizontal():
            self._rows(painter, area)
        else:
            self._columns(painter, area)
        painter.end()

    def _legend(self, painter: QPainter, area: QRectF) -> None:
        metrics = QFontMetrics(painter.font())
        x = area.left()
        for index, item in enumerate(self.series):
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(style.series(self.palette(), index))
            middle = area.center().y()
            painter.drawRoundedRect(QRectF(x, middle - LEGEND_SWATCH / 2, LEGEND_SWATCH, LEGEND_SWATCH), 2, 2)
            painter.setPen(style.muted(self.palette()))
            name = str(item.get("name") or "")
            painter.drawText(QPointF(x + LEGEND_SWATCH + 5, middle + metrics.ascent() / 2 - 1), name)
            x += LEGEND_SWATCH + 5 + metrics.horizontalAdvance(name) + 14

    def _value_axis(self, painter: QPainter, plot: QRectF, low: float, high: float, vertical: bool) -> Any:
        """Gridlines and tick labels; returns the value → pixel mapping."""
        ticks = chart_scale.nice_ticks(low, high)
        low, high = ticks[0], ticks[-1]
        span = (high - low) or 1.0

        def place(value: float) -> float:
            share = (value - low) / span
            return plot.bottom() - share * plot.height() if vertical else plot.left() + share * plot.width()

        metrics = QFontMetrics(painter.font())
        for tick in ticks:
            at = place(tick)
            painter.setPen(QPen(style.hairline(self.palette()), 1))
            if vertical:
                painter.drawLine(QPointF(plot.left(), at), QPointF(plot.right(), at))
                painter.setPen(style.faint(self.palette()))
                text = chart_scale.compact(tick)
                painter.drawText(
                    QPointF(plot.left() - AXIS_GAP - metrics.horizontalAdvance(text), at + metrics.ascent() / 2 - 1),
                    text,
                )
            else:
                painter.drawLine(QPointF(at, plot.top()), QPointF(at, plot.bottom()))
                painter.setPen(style.faint(self.palette()))
                text = chart_scale.compact(tick)
                painter.drawText(
                    QPointF(at - metrics.horizontalAdvance(text) / 2, plot.bottom() + metrics.ascent() + 3), text
                )
        return place

    def _columns(self, painter: QPainter, area: QRectF) -> None:
        metrics = QFontMetrics(painter.font())
        low, high = chart_scale.value_range([item["values"] for item in self.series])
        gutter = max(
            metrics.horizontalAdvance(chart_scale.compact(value)) for value in chart_scale.nice_ticks(low, high)
        )
        plot = QRectF(area.left() + gutter + AXIS_GAP, area.top() + 4, 0, 0)
        plot.setRight(area.right() - 2)
        plot.setBottom(area.bottom() - metrics.height() - AXIS_GAP)
        place = self._value_axis(painter, plot, low, high, vertical=True)
        count = max(1, len(self.labels))
        slot = plot.width() / count
        if self.kind == "line":
            self._lines(painter, plot, place, slot)
        else:
            self._bars_in_slots(painter, plot, place, slot)
        step = chart_scale.thinned(
            count, plot.width(), max(metrics.horizontalAdvance(label) for label in self.labels) + 8
        )
        painter.setPen(style.muted(self.palette()))
        for index in range(0, count, step):
            label = metrics.elidedText(self.labels[index], Qt.TextElideMode.ElideRight, int(slot * step) - 4)
            x = plot.left() + slot * (index + 0.5) - metrics.horizontalAdvance(label) / 2
            painter.drawText(QPointF(x, plot.bottom() + metrics.ascent() + AXIS_GAP), label)

    def _bars_in_slots(self, painter: QPainter, plot: QRectF, place: Any, slot: float) -> None:
        groups = len(self.series)
        gap = MARK_GAP if self.kind == "histogram" else max(MARK_GAP, slot * 0.25)
        width = min(MAX_BAR, max(1.0, (slot - gap) / groups - (MARK_GAP if groups > 1 else 0)))
        gap = slot - groups * width - (groups - 1) * MARK_GAP
        zero = place(0.0)
        peak = self._peak()
        for series_index, item in enumerate(self.series):
            for index, value in enumerate(item["values"]):
                if value is None:
                    continue
                x = plot.left() + slot * index + gap / 2 + series_index * (width + MARK_GAP)
                top, bottom = sorted((place(value), zero))
                bar = QRectF(x, top, width, max(1.0, bottom - top))
                self._bar(painter, bar, style.series(self.palette(), series_index), value >= 0, vertical=True)
                self._hits.append((bar, self._tip(index, item, value)))
                if (series_index, index) == peak:
                    self._label(painter, QPointF(bar.center().x(), bar.top() - 4), value, centred=True)

    def _rows(self, painter: QPainter, area: QRectF) -> None:
        metrics = QFontMetrics(painter.font())
        gutter = min(area.width() * 0.4, max(metrics.horizontalAdvance(label) for label in self.labels) + LABEL_ROOM)
        plot = QRectF(area.left() + gutter, area.top() + AXIS_GAP, 0, 0)
        plot.setRight(area.right() - 40)
        plot.setBottom(area.bottom() - metrics.height() - AXIS_GAP)
        low, high = chart_scale.value_range([item["values"] for item in self.series])
        place = self._value_axis(painter, plot, low, high, vertical=False)
        zero = place(0.0)
        groups = len(self.series)
        row = plot.height() / max(1, len(self.labels))
        height = max(1.0, (row - MARK_GAP * 2) / groups)
        peak = self._peak()
        for index, label in enumerate(self.labels):
            painter.setPen(style.muted(self.palette()))
            shown = metrics.elidedText(label, Qt.TextElideMode.ElideRight, int(gutter - LABEL_ROOM / 2))
            middle = plot.top() + row * (index + 0.5)
            painter.drawText(QPointF(area.left(), middle + metrics.ascent() / 2 - 1), shown)
            for series_index, item in enumerate(self.series):
                value = item["values"][index]
                if value is None:
                    continue
                y = plot.top() + row * index + MARK_GAP + series_index * height
                left, right = sorted((place(value), zero))
                bar = QRectF(left, y, max(1.0, right - left), height - MARK_GAP)
                self._bar(painter, bar, style.series(self.palette(), series_index), value >= 0, vertical=False)
                self._hits.append((bar, self._tip(index, item, value)))
                if (series_index, index) == peak:
                    self._label(painter, QPointF(bar.right() + 4, bar.center().y() + metrics.ascent() / 2 - 1), value)

    def _lines(self, painter: QPainter, plot: QRectF, place: Any, slot: float) -> None:
        peak = self._peak()
        for series_index, item in enumerate(self.series):
            colour = style.series(self.palette(), series_index)
            path = QPainterPath()
            started = False
            points = []
            for index, value in enumerate(item["values"]):
                if value is None:
                    started = False
                    continue
                point = QPointF(plot.left() + slot * (index + 0.5), place(value))
                points.append((index, value, point))
                if started:
                    path.lineTo(point)
                else:
                    path.moveTo(point)
                    started = True
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(colour, LINE_WIDTH, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawPath(path)
            for index, value, point in points:
                hit = QRectF(point.x() - slot / 2, plot.top(), slot, plot.height())
                self._hits.append((hit, self._tip(index, item, value)))
                if len(points) <= MARKER_LIMIT:
                    self._marker(painter, point, colour)
                if (series_index, index) == peak:
                    self._label(painter, QPointF(point.x(), point.y() - MARKER), value, centred=True)

    def _scatter(self, painter: QPainter, area: QRectF) -> None:
        metrics = QFontMetrics(painter.font())
        xs = [item.get("x") or [] for item in self.series]
        x_low, x_high = chart_scale.value_range(xs, stacked_from_zero=False)
        y_low, y_high = chart_scale.value_range([item["values"] for item in self.series], stacked_from_zero=False)
        gutter = max(
            metrics.horizontalAdvance(chart_scale.compact(value)) for value in chart_scale.nice_ticks(y_low, y_high)
        )
        plot = QRectF(area.left() + gutter + AXIS_GAP, area.top() + 4, 0, 0)
        plot.setRight(area.right() - 8)
        plot.setBottom(area.bottom() - metrics.height() - AXIS_GAP)
        place_y = self._value_axis(painter, plot, y_low, y_high, vertical=True)
        place_x = self._value_axis(painter, plot, x_low, x_high, vertical=False)
        for series_index, item in enumerate(self.series):
            colour = style.series(self.palette(), series_index)
            for x, y in zip(item.get("x") or [], item["values"], strict=False):
                if x is None or y is None:
                    continue
                point = QPointF(place_x(x), place_y(y))
                self._marker(painter, point, colour)
                hit = QRectF(point.x() - MARKER, point.y() - MARKER, MARKER * 2, MARKER * 2)
                self._hits.append((hit, f"{item.get('name') or ''} {chart_scale.compact(x)}, {self._shown(y)}".strip()))

    def _pie(self, painter: QPainter, area: QRectF) -> None:
        values = [max(0.0, value or 0.0) for value in self.series[0]["values"]] if self.series else []
        total = sum(values) or 1.0
        side = min(area.height() - 8, area.width() * (1 - PIE_LEGEND_SHARE))
        circle = QRectF(area.left() + 4, area.top() + (area.height() - side) / 2, side, side)
        start = 90.0
        painter.setPen(QPen(style.background(self.palette()), MARK_GAP))
        for index, value in enumerate(values):
            sweep = -360.0 * value / total
            painter.setBrush(style.series(self.palette(), index))
            painter.drawPie(circle, int(start * 16), int(sweep * 16))
            self._hits.append((self._slice_box(circle, start, sweep), self._tip(index, self.series[0], value)))
            start += sweep
        hole = side * DONUT_HOLE
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(style.background(self.palette()))
        painter.drawEllipse(circle.center(), hole / 2, hole / 2)
        metrics = QFontMetrics(painter.font())
        x = circle.right() + 16
        line = metrics.height() + 6
        top = area.top() + max(0.0, (area.height() - line * len(values)) / 2)
        for index, value in enumerate(values):
            y = top + line * index
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(style.series(self.palette(), index))
            painter.drawRoundedRect(QRectF(x, y + (line - LEGEND_SWATCH) / 2, LEGEND_SWATCH, LEGEND_SWATCH), 2, 2)
            share = f"{100 * value / total:.0f}%"
            right = min(area.right(), x + PIE_LEGEND_WIDTH)
            label = metrics.elidedText(self.labels[index], Qt.TextElideMode.ElideRight, int(right - x - 60))
            painter.setPen(style.text(self.palette()))
            painter.drawText(QPointF(x + LEGEND_SWATCH + 6, y + line / 2 + metrics.ascent() / 2 - 1), label)
            painter.setPen(style.muted(self.palette()))
            painter.drawText(
                QPointF(right - metrics.horizontalAdvance(share), y + line / 2 + metrics.ascent() / 2 - 1), share
            )

    # Marks

    def _bar(self, painter: QPainter, bar: QRectF, colour: QColor, positive: bool, vertical: bool) -> None:
        """A bar with its data end rounded and its baseline end square."""
        radius = min(BAR_RADIUS, bar.width() / 2, bar.height() / 2)
        rounded = QPainterPath()
        rounded.addRoundedRect(bar, radius, radius)
        if vertical:
            base_y = bar.bottom() - radius if positive else bar.top()
            base = QRectF(bar.left(), base_y, bar.width(), radius)
        else:
            base_x = bar.left() if positive else bar.right() - radius
            base = QRectF(base_x, bar.top(), radius, bar.height())
        square = QPainterPath()
        square.addRect(base)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(colour)
        # united(), not addRect on one path: overlapping subpaths under the odd-even rule leave a seam.
        painter.drawPath(rounded.united(square))

    def _marker(self, painter: QPainter, point: QPointF, colour: QColor) -> None:
        painter.setPen(QPen(style.background(self.palette()), MARK_GAP))
        painter.setBrush(colour)
        painter.drawEllipse(point, MARKER / 2, MARKER / 2)

    def _label(self, painter: QPainter, at: QPointF, value: float, centred: bool = False) -> None:
        text = self._shown(value)
        if centred:
            at = QPointF(at.x() - QFontMetrics(painter.font()).horizontalAdvance(text) / 2, at.y())
        painter.setPen(style.text(self.palette()))
        painter.drawText(at, text)

    def _peak(self) -> tuple[int, int] | None:
        best: tuple[float, tuple[int, int]] | None = None
        for series_index, item in enumerate(self.series):
            for index, value in enumerate(item["values"]):
                if value is not None and (best is None or value > best[0]):
                    best = (value, (series_index, index))
        return best[1] if best else None

    def _shown(self, value: float) -> str:
        return f"{chart_scale.compact(value)} {self.unit}".strip()

    def _tip(self, index: int, item: dict[str, Any], value: float) -> str:
        label = self.labels[index] if index < len(self.labels) else ""
        name = str(item.get("name") or "")
        head = f"{label} · {name}" if len(self.series) > 1 and name else label
        return f"{head}: {self._shown(value)}"

    @staticmethod
    def _slice_box(circle: QRectF, start: float, sweep: float) -> QRectF:
        middle = math.radians(start + sweep / 2)
        radius = circle.width() * 0.4
        centre = QPointF(
            circle.center().x() + radius * math.cos(middle), circle.center().y() - radius * math.sin(middle)
        )
        return QRectF(centre.x() - 14, centre.y() - 14, 28, 28)

    # Interaction

    def mouseMoveEvent(self, event: Any) -> None:
        position = event.position() if hasattr(event, "position") else QPointF(event.pos())
        tip = next((text for box, text in self._hits if box.contains(position)), "")
        if tip:
            QToolTip.showText(
                event.globalPosition().toPoint() if hasattr(event, "globalPosition") else event.globalPos(), tip, self
            )
        else:
            QToolTip.hideText()

    def contextMenuEvent(self, event: Any) -> None:
        popup = controls.menu(self, self.palette())
        popup.addAction(COPY_IMAGE, lambda: QGuiApplication.clipboard().setPixmap(self.grab()))
        popup.addAction(COPY_DATA, lambda: QGuiApplication.clipboard().setText(self.csv()))
        popup.exec(event.globalPos())

    def csv(self) -> str:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        if self.kind == "scatter":
            writer.writerow(["series", "x", "y"])
            for item in self.series:
                for x, y in zip(item.get("x") or [], item["values"], strict=False):
                    writer.writerow([item.get("name") or "", x, y])
        else:
            writer.writerow(["", *[item.get("name") or "" for item in self.series]])
            for index, label in enumerate(self.labels):
                writer.writerow([label, *[item["values"][index] for item in self.series]])
        return buffer.getvalue()
