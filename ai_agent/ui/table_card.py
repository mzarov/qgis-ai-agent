import csv
import io
from typing import Any

from qgis.PyQt.QtCore import QPointF, QRectF, Qt
from qgis.PyQt.QtGui import QFontMetrics, QGuiApplication, QPainter, QPen
from qgis.PyQt.QtWidgets import QApplication, QScrollBar, QSizePolicy, QToolTip, QWidget

from ai_agent.i18n import tr
from ai_agent.ui import controls, style

ROW_PADDING = 8
CELL_PADDING = 8
TITLE_GAP = 6
MIN_COLUMN = 48
# Text measured to the pixel can still elide by a rounding hair; a little slack prevents it.
ELIDE_SLACK = 3
NUMERIC_CHARS = set("0123456789.,-+ eE%")
COPY_ROWS = tr("Copy rows as CSV")
SHOWN_OF = tr("{0} of {1} rows")


class TableCard(QWidget):
    def __init__(self, spec: dict[str, Any]):
        super().__init__()
        self.spec = spec
        self.columns = [str(column) for column in spec.get("columns") or []]
        self.rows = [[str(cell) for cell in row] for row in spec.get("rows") or []]
        self.total = int(spec.get("total") or len(self.rows))
        self._cells: list[tuple[QRectF, str]] = []
        self._bar = QScrollBar(Qt.Orientation.Horizontal, self)
        self._bar.valueChanged.connect(lambda _value: self.update())
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._fit_bar()

    def plain_text(self) -> str:
        return str(self.spec.get("title") or "")

    def footer(self) -> str:
        return SHOWN_OF.format(len(self.rows), self.total) if self.total > len(self.rows) else ""

    def _row_height(self) -> int:
        return QFontMetrics(self.font()).height() + ROW_PADDING

    def _title_height(self) -> int:
        return QFontMetrics(self._bold()).height() + TITLE_GAP

    def _rows_bottom(self) -> int:
        return self._title_height() + self._row_height() * (len(self.rows) + 1)

    def _bar_room(self) -> int:
        return self._bar.sizeHint().height() if self._bar.maximum() > 0 else 0

    def _height(self) -> int:
        footer = self._row_height() if self.footer() else 0
        return self._rows_bottom() + self._bar_room() + footer + 2

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        self._fit_bar()

    def _fit_bar(self) -> None:
        width = self.width()
        overflow = round(sum(self.column_widths(width)) - width)
        self._bar.setRange(0, max(0, overflow))
        self._bar.setPageStep(width)
        self._bar.setGeometry(0, self._rows_bottom() + 1, width, self._bar.sizeHint().height())
        self._bar.setVisible(overflow > 0)
        self.setFixedHeight(self._height())

    def _bold(self) -> Any:
        font = self.font()
        font.setBold(True)
        return font

    def column_widths(self, width: float) -> list[float]:
        metrics = QFontMetrics(self.font())
        wanted = []
        for index, column in enumerate(self.columns):
            cells = [column] + [row[index] for row in self.rows if index < len(row)]
            widest = max(metrics.horizontalAdvance(cell) for cell in cells)
            wanted.append(max(MIN_COLUMN, widest + 2 * CELL_PADDING + ELIDE_SLACK))
        total = sum(wanted) or 1.0
        if total <= width:
            return wanted
        return [max(MIN_COLUMN, value * width / total) for value in wanted]

    def paintEvent(self, _event: Any) -> None:
        self._cells = []
        painter = QPainter(self)
        palette = self.palette()
        width = float(self.width())
        painter.setFont(self._bold())
        painter.setPen(style.text(palette))
        title = QFontMetrics(self._bold()).elidedText(self.plain_text(), Qt.TextElideMode.ElideRight, int(width))
        painter.drawText(QRectF(0, 0, width, self._title_height()), 0, title)
        widths = self.column_widths(width)
        left = -float(self._bar.value())
        right = left + sum(widths)
        top = float(self._title_height())
        row_height = self._row_height()
        painter.setFont(self._small_bold())
        self._row(painter, self.columns, widths, top, row_height, style.muted(palette))
        painter.setFont(self.font())
        for index, row in enumerate(self.rows):
            y = top + row_height * (index + 1)
            painter.setPen(QPen(style.hairline(palette), 1))
            painter.drawLine(QPointF(left, y), QPointF(right, y))
            self._row(painter, row, widths, y, row_height, style.text(palette))
        y = top + row_height * (len(self.rows) + 1)
        painter.setPen(QPen(style.hairline(palette), 1))
        painter.drawLine(QPointF(left, y), QPointF(right, y))
        if self.footer():
            painter.setFont(self._small())
            painter.setPen(style.faint(palette))
            footer = QRectF(CELL_PADDING, y + self._bar_room(), width, row_height)
            painter.drawText(footer, Qt.AlignmentFlag.AlignVCenter, self.footer())
        painter.end()

    def _row(self, painter: QPainter, cells: list[str], widths: list[float], y: float, height: int, ink: Any) -> None:
        metrics = QFontMetrics(painter.font())
        x = -float(self._bar.value())
        painter.setPen(ink)
        for index, width in enumerate(widths):
            text = cells[index] if index < len(cells) else ""
            room = int(width - 2 * CELL_PADDING)
            shown = metrics.elidedText(text, Qt.TextElideMode.ElideRight, max(1, room))
            numeric = self._numeric(index)
            align = Qt.AlignmentFlag.AlignRight if numeric else Qt.AlignmentFlag.AlignLeft
            box = QRectF(x + CELL_PADDING, y, max(1.0, width - 2 * CELL_PADDING), height)
            painter.drawText(box, align | Qt.AlignmentFlag.AlignVCenter, shown)
            if shown != text:
                self._cells.append((QRectF(x, y, width, height), text))
            x += width

    def _numeric(self, column: int) -> bool:
        cells = [row[column] for row in self.rows if column < len(row) and row[column]]
        return bool(cells) and all(set(cell) <= NUMERIC_CHARS for cell in cells)

    def _small(self) -> Any:
        font = self.font()
        font.setPointSizeF(max(1.0, font.pointSizeF() * controls.SMALL_SCALE))
        return font

    def _small_bold(self) -> Any:
        font = self._small()
        font.setBold(True)
        return font

    def mouseMoveEvent(self, event: Any) -> None:
        position = event.position() if hasattr(event, "position") else QPointF(event.pos())
        full = next((text for box, text in self._cells if box.contains(position)), "")
        if full:
            QToolTip.showText(
                event.globalPosition().toPoint() if hasattr(event, "globalPosition") else event.globalPos(),
                controls.plain_tip(full),
                self,
            )
        else:
            QToolTip.hideText()

    def wheelEvent(self, event: Any) -> None:
        delta = event.angleDelta()
        if self._bar.maximum() > 0 and abs(delta.x()) > abs(delta.y()):
            QApplication.sendEvent(self._bar, event)
        else:
            event.ignore()

    def contextMenuEvent(self, event: Any) -> None:
        popup = controls.menu(self, self.palette())
        popup.addAction(COPY_ROWS, lambda: QGuiApplication.clipboard().setText(self.csv()))
        popup.exec(event.globalPos())
        popup.deleteLater()

    def csv(self) -> str:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(self.columns)
        writer.writerows(self.rows)
        return buffer.getvalue()
