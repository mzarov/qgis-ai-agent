from typing import Any

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ai_agent.ui import style

HINT_SCALE = 0.86
GROUP_SCALE = 1.12
CARD_NAME = "settingsCard"
PANE_NAME = "settingsPane"
SEPARATOR_NAME = "settingsSeparator"
INPUT_RADIUS = 6
INPUT_PADDING = "6px 10px"
INPUT_MIN_HEIGHT = 18
CARD_MARGINS = (14, 12, 14, 13)
CARD_SPACING = 11
FIELD_SPACING = 3
PAGE_MARGINS = (24, 20, 24, 22)
PAGE_SPACING = 6
GROUP_GAP = 18
NAV_WIDTH = 172
NAV_MARGINS = (0, 6, 10, 6)
NAV_SPACING = 2
NAV_RADIUS = 7
NAV_PADDING = "8px 12px"
ROW_VPAD = 6
ROW_GAP = 24
CONTROL_WIDTH = 320


def card(palette: Any) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName(CARD_NAME)
    frame.setStyleSheet(
        f"QFrame#{CARD_NAME} {{ background: {style.css_color(style.panel(palette))};"
        f"border: {style.HAIRLINE}px solid {style.css_color(style.hairline(palette))};"
        f"border-radius: {style.CARD_RADIUS}px; }}"
    )
    column = QVBoxLayout(frame)
    column.setContentsMargins(*CARD_MARGINS)
    column.setSpacing(CARD_SPACING)
    return frame, column


def pane(palette: Any) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName(PANE_NAME)
    frame.setStyleSheet(
        f"QFrame#{PANE_NAME} {{ background: {style.css_color(style.panel(palette))};"
        f"border: {style.HAIRLINE}px solid {style.css_color(style.hairline(palette))};"
        f"border-radius: {style.CARD_RADIUS}px; }}"
    )
    column = QVBoxLayout(frame)
    column.setContentsMargins(0, 0, 0, 0)
    column.setSpacing(0)
    return frame, column


def sidebar() -> tuple[QWidget, QVBoxLayout]:
    holder = QWidget()
    holder.setFixedWidth(NAV_WIDTH)
    column = QVBoxLayout(holder)
    column.setContentsMargins(*NAV_MARGINS)
    column.setSpacing(NAV_SPACING)
    return holder, column


def sidebar_button(title: str, palette: Any) -> QPushButton:
    button = QPushButton(title)
    button.setCheckable(True)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setStyleSheet(
        "QPushButton {"
        f"background: transparent; color: {style.css_color(style.muted(palette))};"
        f"border: {style.HAIRLINE}px solid transparent; border-radius: {NAV_RADIUS}px;"
        f"padding: {NAV_PADDING}; text-align: left; }}"
        f"QPushButton:hover {{ background: {style.css_color(style.card(palette))}; }}"
        "QPushButton:checked {"
        f"background: {style.css_color(style.panel(palette))};"
        f"color: {style.css_color(style.text(palette))}; font-weight: 600; }}"
    )
    return button


def pages() -> QStackedWidget:
    return QStackedWidget()


def page() -> tuple[QWidget, QVBoxLayout]:
    holder = QWidget()
    column = QVBoxLayout(holder)
    column.setContentsMargins(*PAGE_MARGINS)
    column.setSpacing(PAGE_SPACING)
    return holder, column


def group(title: str, palette: Any) -> QLabel:
    label = QLabel(title)
    font = label.font()
    font.setBold(True)
    font.setPointSizeF(max(1.0, font.pointSizeF() * GROUP_SCALE))
    label.setFont(font)
    label.setStyleSheet(f"color: {style.css_color(style.text(palette))};")
    return label


def row(title: str, widget: QWidget, note: str, palette: Any) -> QWidget:
    holder = QWidget()
    line = QHBoxLayout(holder)
    line.setContentsMargins(0, ROW_VPAD, 0, ROW_VPAD)
    line.setSpacing(ROW_GAP)
    line.addWidget(_caption(title, note, palette), 1)
    widget.setStyleSheet(input_style(palette))
    widget.setFixedWidth(CONTROL_WIDTH)
    line.addWidget(widget, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    return holder


def switch_row(title: str, checkbox: QWidget, note: str, palette: Any) -> QWidget:
    holder = QWidget()
    line = QHBoxLayout(holder)
    line.setContentsMargins(0, ROW_VPAD, 0, ROW_VPAD)
    line.setSpacing(ROW_GAP)
    line.addWidget(_caption(title, note, palette), 1)
    line.addWidget(checkbox, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    return holder


def add_rows(column: QVBoxLayout, palette: Any, rows: list[QWidget]) -> None:
    for index, item in enumerate(rows):
        if index:
            column.addWidget(separator(palette))
        column.addWidget(item)


def separator(palette: Any) -> QFrame:
    line = QFrame()
    line.setObjectName(SEPARATOR_NAME)
    line.setFixedHeight(style.HAIRLINE)
    line.setStyleSheet(f"QFrame#{SEPARATOR_NAME} {{ background: {style.css_color(style.hairline(palette))}; }}")
    return line


def _caption(title: str, note: str, palette: Any) -> QWidget:
    box = QWidget()
    column = QVBoxLayout(box)
    column.setContentsMargins(0, 0, 0, 0)
    column.setSpacing(FIELD_SPACING)
    label = QLabel(title)
    label.setWordWrap(True)
    column.addWidget(label)
    if note:
        column.addWidget(hint(note, palette))
    return box


def status(palette: Any) -> QLabel:
    label = QLabel("")
    label.setWordWrap(True)
    label.setVisible(False)
    font = label.font()
    font.setPointSizeF(max(1.0, font.pointSizeF() * HINT_SCALE))
    label.setFont(font)
    label.setStyleSheet(f"color: {style.css_color(style.muted(palette))};")
    return label


def paint_status(label: QLabel, text: str, colour: Any) -> None:
    label.setText(text)
    label.setStyleSheet(f"color: {style.css_color(colour)};")
    label.setVisible(bool(text))


def parsed_budget(raw: str, default: int) -> int:
    try:
        return max(0, int(raw.strip()))
    except (TypeError, ValueError):
        return default


def select(combo: QComboBox, value: str) -> None:
    index = combo.findText(value or "")
    if index >= 0:
        combo.setCurrentIndex(index)


def input_style(palette: Any) -> str:
    border = style.css_color(style.hairline(palette))
    return (
        "QLineEdit, QComboBox {"
        f"background: {style.css_color(style.surface(palette))};"
        f"color: {style.css_color(style.text(palette))};"
        f"border: {style.HAIRLINE}px solid {border};"
        f"border-radius: {INPUT_RADIUS}px; padding: {INPUT_PADDING};"
        f"min-height: {INPUT_MIN_HEIGHT}px; }}"
        "QLineEdit:focus, QComboBox:focus {"
        f"border: {style.HAIRLINE}px solid {style.css_color(style.accent(palette))}; }}"
        "QComboBox::drop-down { border: none; width: 24px; }"
        "QComboBox QAbstractItemView {"
        f"background: {style.css_color(style.panel(palette))};"
        f"color: {style.css_color(style.text(palette))};"
        f"border: {style.HAIRLINE}px solid {border};"
        f"selection-background-color: {style.css_color(style.accent(palette))}; }}"
    )


def accent_button(palette: Any) -> str:
    fill = style.css_color(style.accent(palette))
    return (
        f"QPushButton {{ background: {fill};"
        f"color: {style.css_color(palette.highlightedText().color())};"
        f"border: {style.HAIRLINE}px solid {fill}; border-radius: 6px;"
        "padding: 5px 16px; font-weight: 600; }"
        f"QPushButton:hover {{ background: {style.css_color(style.accent(palette).lighter(112))}; }}"
    )


def plain_button(palette: Any) -> str:
    border = style.css_color(style.hairline(palette))
    return (
        f"QPushButton {{ background: transparent; color: {style.css_color(style.text(palette))};"
        f"border: {style.HAIRLINE}px solid {border}; border-radius: 6px; padding: 5px 14px; }}"
        f"QPushButton:hover {{ background: {style.css_color(style.card(palette))}; }}"
        "QPushButton:disabled { color: palette(mid); }"
    )


def hint(text: str, palette: Any) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    font = label.font()
    font.setPointSizeF(max(1.0, font.pointSizeF() * HINT_SCALE))
    label.setFont(font)
    label.setStyleSheet(f"color: {style.css_color(style.muted(palette))};")
    return label
