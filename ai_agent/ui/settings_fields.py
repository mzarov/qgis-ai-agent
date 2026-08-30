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
SECTION_SCALE = 0.9
CARD_NAME = "settingsCard"
INPUT_RADIUS = 6
INPUT_PADDING = "5px 8px"
CARD_MARGINS = (14, 12, 14, 13)
CARD_SPACING = 11
FIELD_SPACING = 3
LABEL_SPACING = 2
PAGE_MARGINS = (20, 18, 20, 16)
PAGE_SPACING = 10
GROUP_SCALE = 1.15
NAV_WIDTH = 168
NAV_MARGINS = (10, 18, 6, 16)
NAV_SPACING = 2
NAV_RADIUS = 7
NAV_PADDING = "7px 12px"
NAV_HEADING_INSET = 12
ROW_GAP = 16
ROW_BOTTOM = 2
CONTROL_WIDTH = 240
SEPARATOR_NAME = "settingsSeparator"


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


def sidebar() -> tuple[QWidget, QVBoxLayout]:
    holder = QWidget()
    holder.setFixedWidth(NAV_WIDTH)
    column = QVBoxLayout(holder)
    column.setContentsMargins(*NAV_MARGINS)
    column.setSpacing(NAV_SPACING)
    return holder, column


def nav_heading(title: str, palette: Any) -> QLabel:
    label = QLabel(title)
    font = label.font()
    font.setPointSizeF(max(1.0, font.pointSizeF() * HINT_SCALE))
    label.setFont(font)
    label.setStyleSheet(f"color: {style.css_color(style.muted(palette))}; padding: 0 {NAV_HEADING_INSET}px;")
    return label


def pages() -> QStackedWidget:
    stack = QStackedWidget()
    return stack


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
    column = QVBoxLayout(holder)
    column.setContentsMargins(0, 0, 0, ROW_BOTTOM)
    column.setSpacing(FIELD_SPACING)

    line = QHBoxLayout()
    line.setContentsMargins(0, 0, 0, 0)
    line.setSpacing(ROW_GAP)
    caption = QLabel(title)
    caption.setWordWrap(True)
    line.addWidget(caption, 1)
    widget.setStyleSheet(input_style(palette))
    widget.setMinimumWidth(CONTROL_WIDTH)
    line.addWidget(widget, 0, Qt.AlignmentFlag.AlignRight)
    column.addLayout(line)
    if note:
        column.addWidget(hint(note, palette))
    column.addWidget(separator(palette))
    return holder


def switch_row(checkbox: QWidget, note: str, palette: Any) -> QWidget:
    holder = QWidget()
    column = QVBoxLayout(holder)
    column.setContentsMargins(0, 0, 0, ROW_BOTTOM)
    column.setSpacing(FIELD_SPACING)
    column.addWidget(checkbox)
    if note:
        column.addWidget(hint(note, palette))
    column.addWidget(separator(palette))
    return holder


def separator(palette: Any) -> QFrame:
    line = QFrame()
    line.setObjectName(SEPARATOR_NAME)
    line.setFixedHeight(style.HAIRLINE)
    line.setStyleSheet(f"QFrame#{SEPARATOR_NAME} {{ background: {style.css_color(style.hairline(palette))}; }}")
    return line


def page() -> tuple[QWidget, QVBoxLayout]:
    holder = QWidget()
    column = QVBoxLayout(holder)
    column.setContentsMargins(*PAGE_MARGINS)
    column.setSpacing(PAGE_SPACING)
    return holder, column


def section(title: str, palette: Any) -> QLabel:
    label = QLabel(title.upper())
    font = label.font()
    font.setBold(True)
    font.setPointSizeF(max(1.0, font.pointSizeF() * SECTION_SCALE))
    label.setFont(font)
    label.setStyleSheet(f"color: {style.css_color(style.muted(palette))}; letter-spacing: 1px;")
    return label


def field(title: str, widget: QWidget, note: str, palette: Any) -> QWidget:
    holder = QWidget()
    column = QVBoxLayout(holder)
    column.setContentsMargins(0, 0, 0, 0)
    column.setSpacing(FIELD_SPACING)

    column.addWidget(QLabel(title))
    widget.setStyleSheet(input_style(palette))
    column.addWidget(widget)
    if note:
        column.addSpacing(LABEL_SPACING)
        column.addWidget(hint(note, palette))
    return holder


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
        f"border-radius: {INPUT_RADIUS}px; padding: {INPUT_PADDING}; }}"
        "QLineEdit:focus, QComboBox:focus {"
        f"border: {style.HAIRLINE}px solid {style.css_color(style.accent(palette))}; }}"
        "QComboBox::drop-down { border: none; width: 22px; }"
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
