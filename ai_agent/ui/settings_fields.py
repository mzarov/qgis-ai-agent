from typing import Any

from qgis.PyQt.QtCore import QEvent, QRectF, QSize, Qt, pyqtSignal
from qgis.PyQt.QtGui import QIcon, QPainter
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

from ai_agent.ui import controls, style

# The handoff's type scale against the 13 px body: notes and captions 12, a page title 18.
HINT_SCALE = 12 / 13
CAPTION_SCALE = 12 / 13
TITLE_SCALE = 18 / 13
SEPARATOR_NAME = "settingsSeparator"
SEARCH_PROPERTY = "settingsSearch"
STEPPER_NAME = "settingsStepper"
STEPPER_HEIGHT = 30
STEPPER_VALUE_WIDTH = 64
STEPPER_PADDING = 16
WIDE_GAP = 6
DISABLED_OPACITY = 0.45
INPUT_RADIUS = 6
INPUT_PADDING = "5px 10px"
INPUT_MIN_HEIGHT = 18
FIELD_SPACING = 2
PAGE_MARGINS = (28, 22, 28, 28)
PAGE_SPACING = 0
LEAD_GAP = 4
# Between the page's title block and each section: the handoff's 22 px column gap.
SECTION_GAP = 22
SECTION_TO_CARD = 2
NAV_WIDTH = 216
NAV_MARGINS = (8, 12, 8, 12)
NAV_SPACING = 2
NAV_RADIUS = 6
NAV_PADDING = "0px 8px"
NAV_HEIGHT = 30
NAV_ICON = 16
FLAT_ROW_PADDING = (0, 11, 0, 11)
FIRST_SECTION_GAP = 0
ROW_MIN_HEIGHT = 40
ROW_GAP = 20
CONTROL_WIDTH = 300
SWITCH_WIDTH = 30
SWITCH_HEIGHT = 18
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
        """The handoff's toggle: an accent track with a light knob when on, a sunken outlined one when off."""
        palette = self._palette
        on = self.isChecked()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.isEnabled():
            painter.setOpacity(DISABLED_OPACITY)
        track = QRectF(0.5, 0.5, SWITCH_WIDTH - 1, SWITCH_HEIGHT - 1)
        painter.setPen(style.accent(palette) if on else style.border_strong(palette))
        painter.setBrush(style.accent(palette) if on else style.sunken(palette))
        painter.drawRoundedRect(track, track.height() / 2, track.height() / 2)
        knob = SWITCH_HEIGHT - 2 * SWITCH_KNOB_MARGIN
        x = SWITCH_WIDTH - knob - SWITCH_KNOB_MARGIN if on else SWITCH_KNOB_MARGIN
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(style.on_accent(palette) if on else style.faint(palette))
        painter.drawEllipse(QRectF(x, SWITCH_KNOB_MARGIN, knob, knob))
        painter.end()


class Stepper(QFrame):
    """A whole number between a minus and a plus, moving by a fixed step within its range."""

    valueChanged = pyqtSignal(int)

    def __init__(self, palette: Any, value: int, low: int, high: int, step: int, suffix: str = ""):
        super().__init__()
        # Set before anything can restyle the frame: a style change calls changeEvent mid-construction.
        self._shown: QWidget | None = None
        self._low, self._high, self._step = low, high, step
        self._value = max(low, min(high, value))
        self.setObjectName(STEPPER_NAME)
        border = style.css_color(style.border_strong(palette))
        self.setStyleSheet(
            f"QFrame#{STEPPER_NAME} {{ background: {style.css_color(style.field(palette))};"
            f"border: {style.HAIRLINE}px solid {border}; border-radius: {INPUT_RADIUS}px; }}"
        )
        line = QHBoxLayout(self)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(0)
        self.minus = self._button("−", -step, palette)
        line.addWidget(self.minus)
        # The number and its unit apart: "120 s" is a setting, not a timing, and stays one word per label.
        shown = QWidget()
        middle = QHBoxLayout(shown)
        middle.setContentsMargins(0, 0, 0, 0)
        middle.setSpacing(0)
        middle.addStretch(1)
        self._number = QLabel()
        style.ink(self._number, style.text(palette))
        middle.addWidget(self._number)
        self._unit = QLabel(suffix)
        style.ink(self._unit, style.text(palette))
        middle.addWidget(self._unit)
        self._unit.setVisible(bool(suffix))
        middle.addStretch(1)
        self._shown = shown
        line.addWidget(shown)
        self.plus = self._button("+", step, palette)
        line.addWidget(self.plus)
        self.setFixedHeight(STEPPER_HEIGHT)
        self._fit()
        self._show()

    def value(self) -> int:
        return self._value

    def setValue(self, value: int) -> None:
        clamped = max(self._low, min(self._high, int(value)))
        if clamped != self._value:
            self._value = clamped
            self._show()
            self.valueChanged.emit(clamped)

    def changeEvent(self, event: Any) -> None:
        # The font it shows in is known only once the window's own reaches it: measure again then.
        if event.type() in (QEvent.Type.FontChange, QEvent.Type.StyleChange, QEvent.Type.Polish):
            self._fit()
        super().changeEvent(event)

    def _fit(self) -> None:
        """Room for the longest value it can show, so the box never changes width as the value does."""
        if self._shown is None:
            return
        metrics = self._number.fontMetrics()
        widest = metrics.horizontalAdvance(f"{self._high}{self._unit.text()}") + STEPPER_PADDING
        self._shown.setFixedWidth(max(STEPPER_VALUE_WIDTH, widest))

    def _button(self, text: str, delta: int, palette: Any) -> QPushButton:
        button = QPushButton(text)
        button.setFixedSize(STEPPER_HEIGHT, STEPPER_HEIGHT - 2)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setStyleSheet(
            f"QPushButton {{ background: transparent; border: {style.HAIRLINE}px solid transparent;"
            f"color: {style.css_color(style.muted(palette))}; }}"
            f"QPushButton:hover {{ color: {style.css_color(style.text(palette))}; }}"
            f"QPushButton:disabled {{ color: {style.css_color(style.faint(palette))}; }}"
        )
        button.clicked.connect(lambda _checked=False: self.setValue(self._value + delta))
        return button

    def _show(self) -> None:
        self._number.setText(str(self._value))
        self.minus.setEnabled(self._value > self._low)
        self.plus.setEnabled(self._value < self._high)


def switch(palette: Any) -> Switch:
    return Switch(palette)


def card_rows(palette: Any, rows: list[QWidget]) -> QWidget:
    """Rows on the page itself, a hairline between neighbours: the flat Claude Code settings look."""
    holder = QWidget()
    column = QVBoxLayout(holder)
    column.setContentsMargins(0, 0, 0, 0)
    column.setSpacing(0)
    add_rows(column, palette, rows)
    return holder


def sidebar() -> tuple[QWidget, QVBoxLayout]:
    holder = QWidget()
    holder.setFixedWidth(NAV_WIDTH)
    column = QVBoxLayout(holder)
    column.setContentsMargins(*NAV_MARGINS)
    column.setSpacing(NAV_SPACING)
    return holder, column


def sidebar_button(title: str, palette: Any, glyphs: tuple[Any, Any] | None = None) -> QPushButton:
    """A sidebar entry: muted at rest, the chosen one lifted with a hairline, its icon in the accent."""
    button = QPushButton(title)
    button.setCheckable(True)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setFixedHeight(NAV_HEIGHT)
    if glyphs is not None and glyphs[0] is not None:
        rest, chosen = glyphs
        icon = QIcon()
        icon.addPixmap(rest.pixmap(NAV_ICON, NAV_ICON), QIcon.Mode.Normal, QIcon.State.Off)
        icon.addPixmap((chosen or rest).pixmap(NAV_ICON, NAV_ICON), QIcon.Mode.Normal, QIcon.State.On)
        button.setIcon(icon)
        button.setIconSize(QSize(NAV_ICON, NAV_ICON))
    button.setStyleSheet(
        "QPushButton {"
        f"background: transparent; color: {style.css_color(style.muted(palette))};"
        f"border: {style.HAIRLINE}px solid transparent; border-radius: {NAV_RADIUS}px;"
        f"padding: {NAV_PADDING}; text-align: left; }}"
        "QPushButton:hover:!checked {"
        f"background: {style.css_color(style.card(palette))}; }}"
        "QPushButton:checked {"
        f"background: {style.css_color(style.card(palette))};"
        f"border-color: {style.css_color(style.hairline(palette))};"
        f"color: {style.css_color(style.text(palette))}; font-weight: 500; }}"
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


def page(title: str = "", lead: str = "", palette: Any = None) -> tuple[QWidget, QVBoxLayout]:
    """A settings page: its title in 18/600 and one sentence under it, then whatever the caller adds."""
    holder = QWidget()
    column = QVBoxLayout(holder)
    column.setContentsMargins(*PAGE_MARGINS)
    column.setSpacing(PAGE_SPACING)
    if title and palette is not None:
        column.addWidget(page_title(title, palette))
        if lead:
            column.addSpacing(LEAD_GAP)
            note = QLabel(lead)
            note.setWordWrap(True)
            style.ink(note, style.muted(palette))
            column.addWidget(note)
    return holder, column


def page_title(title: str, palette: Any) -> QLabel:
    label = QLabel(title)
    label.setWordWrap(True)
    style.scale_font(label, TITLE_SCALE, bold=True)
    style.ink(label, style.text(palette))
    return label


def section(column: QVBoxLayout, title: str, palette: Any, note: str = "") -> None:
    """A small caption that opens a group of rows, with an optional muted sentence under it."""
    column.addSpacing(SECTION_GAP if column.count() else FIRST_SECTION_GAP)
    if title:
        column.addWidget(heading(title, palette))
    if note:
        column.addSpacing(LEAD_GAP)
        column.addWidget(hint(note, palette))
    column.addSpacing(SECTION_TO_CARD)


def heading(title: str, palette: Any) -> QLabel:
    """A section caption: 12/600 in the secondary ink, as the handoff's group titles."""
    label = QLabel(title)
    label.setWordWrap(True)
    style.scale_font(label, CAPTION_SCALE, bold=True)
    style.ink(label, style.muted(palette))
    return label


def row(title: str, widget: QWidget, note: str, palette: Any, tooltip: str = "") -> QWidget:
    widget.setStyleSheet(input_style(palette))
    widget.setFixedWidth(CONTROL_WIDTH)
    return _row(title, widget, note, palette, tooltip)


def switch_row(title: str, checkbox: QWidget, note: str, palette: Any, tooltip: str = "") -> QWidget:
    return _row(title, checkbox, note, palette, tooltip)


def custom_row(title: str, widget: QWidget, note: str, palette: Any, tooltip: str = "") -> QWidget:
    """A row whose control styles itself: segmented choices, chips, a field with a suffix."""
    return _row(title, widget, note, palette, tooltip)


def wide_row(title: str, widget: QWidget, note: str, palette: Any) -> QWidget:
    """A row whose control needs the full width, under its title and hint: a text area."""
    holder = QWidget()
    column = QVBoxLayout(holder)
    column.setContentsMargins(*FLAT_ROW_PADDING)
    column.setSpacing(FIELD_SPACING)
    name = QLabel(title)
    name.setWordWrap(True)
    style.ink(name, style.text(palette))
    column.addWidget(name)
    holder.setProperty(SEARCH_PROPERTY, f"{title} {note}".strip())
    holder.hint = hint(note, palette)
    column.addWidget(holder.hint)
    holder.hint.setVisible(bool(note))
    column.addSpacing(WIDE_GAP)
    column.addWidget(widget)
    return holder


def _row(title: str, widget: QWidget, note: str, palette: Any, tooltip: str) -> QWidget:
    holder = QWidget()
    holder.setMinimumHeight(ROW_MIN_HEIGHT)
    line = QHBoxLayout(holder)
    line.setContentsMargins(*FLAT_ROW_PADDING)
    line.setSpacing(ROW_GAP)
    caption = QWidget()
    text = QVBoxLayout(caption)
    text.setContentsMargins(0, 0, 0, 0)
    text.setSpacing(FIELD_SPACING)
    # Keep title and hint together, centred against a tall control, instead of spread apart.
    text.addStretch(1)
    name = QLabel(title)
    name.setWordWrap(True)
    style.ink(name, style.text(palette))
    text.addWidget(name)
    # What the sidebar's search matches: the row's title and its hint.
    holder.setProperty(SEARCH_PROPERTY, f"{title} {note}".strip())
    holder.hint = hint(note, palette)
    # Shown only once it has a parent: a parentless widget shown becomes a window of its own,
    # and thirty such windows were most of the second the settings took to open.
    text.addWidget(holder.hint)
    holder.hint.setVisible(bool(note))
    text.addStretch(1)
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
    label = hint("", palette)
    label.setVisible(False)
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
    border = style.css_color(style.border_strong(palette))
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
    """The primary button: accent while there is something to do, a quiet sunken one until then."""
    fill = style.css_color(style.accent(palette))
    return (
        f"QPushButton {{ background: {fill};"
        f"color: {style.css_color(style.on_accent(palette))};"
        f"border: {style.HAIRLINE}px solid {fill}; border-radius: {BUTTON_RADIUS}px;"
        "padding: 5px 16px; font-weight: 600; }"
        f"QPushButton:hover {{ background: {style.css_color(style.accent_hover(palette))}; }}"
        f"QPushButton:disabled {{ background: {style.css_color(style.sunken(palette))};"
        f"border-color: {style.css_color(style.hairline(palette))}; color: {style.css_color(style.faint(palette))}; }}"
    )


def danger_button(palette: Any) -> str:
    """An outlined button in the danger colour, for what cannot be undone."""
    bad = style.css_color(style.danger(palette))
    return (
        f"QPushButton {{ background: {style.css_color(style.surface(palette))}; color: {bad};"
        f"border: {style.HAIRLINE}px solid {bad}; border-radius: {BUTTON_RADIUS}px; padding: 5px 12px; }}"
        f"QPushButton:hover {{ background: {style.css_color(style.soft(palette, style.danger(palette)))}; }}"
    )


def plain_button(palette: Any) -> str:
    border = style.css_color(style.border_strong(palette))
    return (
        f"QPushButton {{ background: {style.css_color(style.panel(palette))};"
        f"color: {style.css_color(style.text(palette))};"
        f"border: {style.HAIRLINE}px solid {border}; border-radius: {BUTTON_RADIUS}px; padding: 5px 12px; }}"
        f"QPushButton:hover {{ background: {style.css_color(style.card(palette))}; }}"
        f"QPushButton:disabled {{ color: {style.css_color(style.faint(palette))}; }}"
    )


def ghost_button(palette: Any) -> str:
    return (
        f"QPushButton {{ background: transparent; color: {style.css_color(style.muted(palette))};"
        f"border: {style.HAIRLINE}px solid transparent; border-radius: {BUTTON_RADIUS}px; padding: 6px 14px; }}"
        f"QPushButton:hover {{ background: {style.css_color(style.card(palette))};"
        f"color: {style.css_color(style.text(palette))}; }}"
    )


def hint(text: str, palette: Any) -> QLabel:
    """A row's note: 12 px in the tertiary ink, wrapping."""
    label = controls.small(text, palette, HINT_SCALE)
    style.ink(label, style.faint(palette))
    return label
