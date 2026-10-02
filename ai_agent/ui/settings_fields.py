from typing import Any

from qgis.PyQt.QtCore import QRectF, QSize, Qt
from qgis.PyQt.QtGui import QFont, QPainter
from qgis.PyQt.QtWidgets import (
    QCheckBox,
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

HINT_SCALE = 0.88
SECTION_SCALE = 0.8
TITLE_SCALE = 1.45
GROUP_SCALE = 1.25
CARD_NAME = "settingsCard"
SEPARATOR_NAME = "settingsSeparator"
INPUT_RADIUS = 6
INPUT_PADDING = "6px 10px"
INPUT_MIN_HEIGHT = 20
FIELD_SPACING = 2
PAGE_MARGINS = (32, 24, 32, 24)
PAGE_SPACING = 0
LEAD_GAP = 4
SECTION_GAP = 22
SECTION_TO_CARD = 8
GROUP_GAP = 22
NAV_WIDTH = 210
NAV_MARGINS = (12, 14, 12, 14)
NAV_SPACING = 2
NAV_RADIUS = 7
NAV_PADDING = "7px 10px"
NAV_ICON = 16
ROW_PADDING = (16, 12, 16, 12)
ROW_MIN_HEIGHT = 56
ROW_GAP = 16
CONTROL_WIDTH = 300
SWITCH_WIDTH = 38
SWITCH_HEIGHT = 22
SWITCH_KNOB_MARGIN = 3
BUTTON_RADIUS = 6


class Switch(QCheckBox):
    def __init__(self, palette: Any):
        super().__init__()
        self._palette = palette
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def sizeHint(self) -> QSize:
        return QSize(SWITCH_WIDTH, SWITCH_HEIGHT)

    def hitButton(self, _pos: Any) -> bool:
        return True

    def paintEvent(self, _event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._track_colour())
        painter.drawRoundedRect(QRectF(0, 0, SWITCH_WIDTH, SWITCH_HEIGHT), SWITCH_HEIGHT / 2, SWITCH_HEIGHT / 2)
        knob = SWITCH_HEIGHT - 2 * SWITCH_KNOB_MARGIN
        x = SWITCH_WIDTH - knob - SWITCH_KNOB_MARGIN if self.isChecked() else SWITCH_KNOB_MARGIN
        painter.setBrush(self._palette.highlightedText().color())
        painter.drawEllipse(QRectF(x, SWITCH_KNOB_MARGIN, knob, knob))
        painter.end()

    def _track_colour(self) -> Any:
        if not self.isEnabled():
            return style.card(self._palette)
        return style.accent(self._palette) if self.isChecked() else style.hairline(self._palette)


def switch(palette: Any) -> Switch:
    return Switch(palette)


def card(palette: Any) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName(CARD_NAME)
    frame.setStyleSheet(
        f"QFrame#{CARD_NAME} {{ background: {style.css_color(style.panel(palette))};"
        f"border: {style.HAIRLINE}px solid {style.css_color(style.hairline(palette))};"
        f"border-radius: {style.CARD_RADIUS}px; }}"
    )
    column = QVBoxLayout(frame)
    column.setContentsMargins(0, 0, 0, 0)
    column.setSpacing(0)
    return frame, column


def card_rows(palette: Any, rows: list[QWidget]) -> QFrame:
    """One card holding `rows`, a hairline between neighbours and none after the last."""
    frame, column = card(palette)
    add_rows(column, palette, rows)
    return frame


def sidebar() -> tuple[QWidget, QVBoxLayout]:
    holder = QWidget()
    holder.setFixedWidth(NAV_WIDTH)
    column = QVBoxLayout(holder)
    column.setContentsMargins(*NAV_MARGINS)
    column.setSpacing(NAV_SPACING)
    return holder, column


def sidebar_button(title: str, palette: Any, icon: Any = None) -> QPushButton:
    button = QPushButton(title)
    button.setCheckable(True)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    if icon is not None:
        button.setIcon(icon)
        button.setIconSize(QSize(NAV_ICON, NAV_ICON))
    button.setStyleSheet(
        "QPushButton {"
        f"background: transparent; color: {style.css_color(style.muted(palette))};"
        f"border: {style.HAIRLINE}px solid transparent; border-radius: {NAV_RADIUS}px;"
        f"padding: {NAV_PADDING}; text-align: left; }}"
        "QPushButton:hover:!checked {"
        f"background: {style.css_color(style.card(palette))};"
        f"color: {style.css_color(style.text(palette))}; }}"
        "QPushButton:checked {"
        f"background: {style.css_color(style.panel(palette))};"
        f"border-color: {style.css_color(style.hairline(palette))};"
        f"color: {style.css_color(style.text(palette))}; font-weight: 600; }}"
    )
    return button


def vertical_separator(palette: Any) -> QFrame:
    line = QFrame()
    line.setObjectName(SEPARATOR_NAME)
    line.setFixedWidth(style.HAIRLINE)
    line.setStyleSheet(f"QFrame#{SEPARATOR_NAME} {{ background: {style.css_color(style.hairline(palette))}; }}")
    return line


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


def page_header(column: QVBoxLayout, title: str, lead: str, palette: Any) -> None:
    """The page's own title and one muted sentence under it."""
    heading = QLabel(title)
    font = heading.font()
    font.setBold(True)
    font.setPointSizeF(max(1.0, font.pointSizeF() * TITLE_SCALE))
    heading.setFont(font)
    heading.setStyleSheet(f"color: {style.css_color(style.text(palette))};")
    column.addWidget(heading)
    if lead:
        column.addSpacing(LEAD_GAP)
        column.addWidget(hint(lead, palette))


def section(column: QVBoxLayout, title: str, palette: Any) -> None:
    """A small upper-case caption that opens a group of cards."""
    column.addSpacing(SECTION_GAP)
    label = QLabel(title.upper())
    font = label.font()
    font.setBold(True)
    font.setPointSizeF(max(1.0, font.pointSizeF() * SECTION_SCALE))
    font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 106)
    label.setFont(font)
    label.setStyleSheet(f"color: {style.css_color(style.muted(palette))};")
    column.addWidget(label)
    column.addSpacing(SECTION_TO_CARD)


def row(title: str, widget: QWidget, note: str, palette: Any, tooltip: str = "") -> QWidget:
    widget.setStyleSheet(input_style(palette))
    widget.setFixedWidth(CONTROL_WIDTH)
    return _row(title, widget, note, palette, tooltip)


def switch_row(title: str, checkbox: QWidget, note: str, palette: Any, tooltip: str = "") -> QWidget:
    return _row(title, checkbox, note, palette, tooltip)


def custom_row(title: str, widget: QWidget, note: str, palette: Any, tooltip: str = "") -> QWidget:
    """A row whose control styles itself: segmented choices, chips, a field with a suffix."""
    return _row(title, widget, note, palette, tooltip)


def _row(title: str, widget: QWidget, note: str, palette: Any, tooltip: str) -> QWidget:
    holder = QWidget()
    holder.setMinimumHeight(ROW_MIN_HEIGHT)
    line = QHBoxLayout(holder)
    line.setContentsMargins(*ROW_PADDING)
    line.setSpacing(ROW_GAP)
    caption = QWidget()
    text = QVBoxLayout(caption)
    text.setContentsMargins(0, 0, 0, 0)
    text.setSpacing(FIELD_SPACING)
    name = QLabel(title)
    name.setStyleSheet(f"color: {style.css_color(style.text(palette))};")
    text.addWidget(name)
    holder.hint = hint(note, palette)
    holder.hint.setVisible(bool(note))
    text.addWidget(holder.hint)
    line.addWidget(caption, 1)
    line.addWidget(widget, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    if tooltip:
        caption.setToolTip(rich_tooltip(tooltip))
    return holder


def set_row_hint(holder: QWidget, note: str) -> None:
    holder.hint.setText(note)
    holder.hint.setVisible(bool(note))


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


def rich_tooltip(note: str) -> str:
    return f"<qt>{note}</qt>"


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


BUDGET_MULTIPLIERS = {"k": 1_000, "m": 1_000_000}


def parsed_budget(raw: str) -> int | None:
    """Read a token count such as 200000, 200 000, 200k or 1.5m; None when unreadable.

    An empty field means no limit (0). Negative numbers are refused rather than
    silently read as "no limit".
    """
    text = "".join((raw or "").split()).replace("_", "").lower()
    if not text:
        return 0
    multiplier = BUDGET_MULTIPLIERS.get(text[-1], 1)
    if multiplier != 1:
        text = text[:-1]
    try:
        value = float(text.replace(",", "."))
    except ValueError:
        return None
    if value < 0 or value != value:
        return None
    return int(value * multiplier)


def select(combo: QComboBox, value: str) -> None:
    index = combo.findText(value or "")
    if index >= 0:
        combo.setCurrentIndex(index)


def input_style(palette: Any) -> str:
    border = style.css_color(style.hairline(palette))
    return (
        "QLineEdit, QComboBox {"
        f"background: {style.css_color(style.field(palette))};"
        f"color: {style.css_color(style.text(palette))};"
        f"border: {style.HAIRLINE}px solid {border};"
        f"border-radius: {INPUT_RADIUS}px; padding: {INPUT_PADDING};"
        f"min-height: {INPUT_MIN_HEIGHT}px; }}"
        "QLineEdit:focus, QComboBox:focus {"
        f"border: {style.HAIRLINE}px solid {style.css_color(style.accent(palette))}; }}"
        "QLineEdit:disabled, QComboBox:disabled {"
        f"background: {style.css_color(style.card(palette))}; color: {style.css_color(style.muted(palette))}; }}"
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
        f"color: {style.css_color(style.on_accent(palette))};"
        f"border: {style.HAIRLINE}px solid {fill}; border-radius: {BUTTON_RADIUS}px;"
        "padding: 6px 18px; font-weight: 600; }"
        f"QPushButton:hover {{ background: {style.css_color(style.accent(palette).lighter(112))}; }}"
        f"QPushButton:disabled {{ background: {style.css_color(style.card(palette))};"
        f"border-color: {style.css_color(style.hairline(palette))}; color: {style.css_color(style.muted(palette))}; }}"
    )


def plain_button(palette: Any) -> str:
    border = style.css_color(style.hairline(palette))
    return (
        f"QPushButton {{ background: {style.css_color(style.panel(palette))};"
        f"color: {style.css_color(style.text(palette))};"
        f"border: {style.HAIRLINE}px solid {border}; border-radius: {BUTTON_RADIUS}px; padding: 6px 14px; }}"
        f"QPushButton:hover {{ background: {style.css_color(style.card(palette))}; }}"
        "QPushButton:disabled { color: palette(mid); }"
    )


def ghost_button(palette: Any) -> str:
    return (
        f"QPushButton {{ background: transparent; color: {style.css_color(style.muted(palette))};"
        f"border: {style.HAIRLINE}px solid transparent; border-radius: {BUTTON_RADIUS}px; padding: 6px 14px; }}"
        f"QPushButton:hover {{ background: {style.css_color(style.card(palette))};"
        f"color: {style.css_color(style.text(palette))}; }}"
    )


def hint(text: str, palette: Any) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    font = label.font()
    font.setPointSizeF(max(1.0, font.pointSizeF() * HINT_SCALE))
    label.setFont(font)
    label.setStyleSheet(f"color: {style.css_color(style.muted(palette))};")
    return label
