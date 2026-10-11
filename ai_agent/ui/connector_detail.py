"""One connector on its own page: what it is, prompts to try, what it serves and on what terms.

Opened from a card on the Connectors page. The switch here and the card's
switch are one setting shown twice, so each follows the other. A click on an
example prompt hands it to the chat box through `prompt_chosen`.
"""

from typing import Any

from qgis.PyQt.QtCore import QObject, Qt, pyqtSignal
from qgis.PyQt.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ai_agent.i18n import tr, tr_data
from ai_agent.ui import controls, icons, style
from ai_agent.ui import settings_fields as fields

BACK = tr("‹ All connectors")
TRY = tr("Try asking")
TO_CHAT = tr("to chat ↵")
ABOUT = tr("How it works")
ENABLED = tr("Connected")
DISABLED = tr("Switched off")
INSIDE = tr("What's inside")
INFORMATION = tr("Information")
KEY_LABEL = tr("Account or key")
KEY_VALUE = tr("Not needed: open data")
LICENCE = tr("Licence")
SERVERS = tr("Servers")
CAPTIONS = {
    "xyz": tr("Map tiles, up to zoom {0}"),
    "wms": tr("Map image (WMS)"),
    "wfs": tr("Vector features (WFS)"),
    "vector": tr("Vector layers, downloaded"),
    "imagery": tr("Scenes and rasters, read from the cloud"),
    "pointer": tr("Through the agent's own tools"),
}
# Country codes mark national services; the rest wear a drawn glyph.
GLYPHS = {"openstreetmap": "geocoding", "geoboundaries": "geocoding"}
MONOGRAM = 34
LARGE_MONOGRAM = 44
MONOGRAM_RADIUS = 8
MONOGRAM_SCALE = 0.85
GLYPH = 17
HEADER_GAP = 14
EXAMPLE_GAP = 6
EXAMPLE_RADIUS = 6
EXAMPLE_MARGINS = (12, 8, 12, 8)
STATUS_DOT = 6
ROW_PADDING = (0, 9, 0, 9)
INFO_LABEL_WIDTH = 150
INFO_PADDING = (0, 8, 0, 8)


def caption(item: dict[str, Any]) -> str:
    text = CAPTIONS.get(str(item["kind"]), "")
    return text.format(item["zmax"]) if "{0}" in text else text


def monogram(row: dict[str, Any], palette: Any, size: int = MONOGRAM) -> QLabel:
    label = QLabel()
    label.setFixedSize(size, size)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setStyleSheet(
        f"QLabel {{ background: {style.css_color(style.card(palette))};"
        f"color: {style.css_color(style.accent_ink(palette))}; border-radius: {MONOGRAM_RADIUS}px; }}"
    )
    code = str(row.get("monogram") or "")
    icon = None if code else icons.drawn(GLYPHS.get(str(row["id"]), "connectors"), style.accent(palette), GLYPH)
    if icon is not None:
        label.setPixmap(icon.pixmap(GLYPH, GLYPH))
    else:
        style.scale_font(label, MONOGRAM_SCALE * size / MONOGRAM, bold=True)
        label.setText(code or str(row["id"])[:2].upper())
    return label


class ConnectorDetail(QObject):
    back = pyqtSignal()
    prompt_chosen = pyqtSignal(str)

    def __init__(self, row: dict[str, Any], card_switch: Any, palette: Any):
        super().__init__()
        self.identifier = str(row["id"])
        holder, column = fields.page()
        back = QPushButton(BACK)
        back.setStyleSheet(_link_style(palette))
        back.setCursor(Qt.CursorShape.PointingHandCursor)
        back.clicked.connect(self.back.emit)
        column.addWidget(back, 0, Qt.AlignmentFlag.AlignLeft)
        column.addSpacing(HEADER_GAP)
        column.addLayout(self._header(row, palette))
        self.switch.setChecked(card_switch.isChecked())
        self._show_state(self.switch.isChecked(), palette)
        self.switch.toggled.connect(card_switch.setChecked)
        card_switch.toggled.connect(self.switch.setChecked)
        self.examples: list[QWidget] = []
        if row["examples"]:
            fields.section(column, TRY, palette)
            column.addSpacing(EXAMPLE_GAP)
            for text in row["examples"]:
                column.addWidget(self._example(tr_data(text), palette))
                column.addSpacing(EXAMPLE_GAP)
        fields.section(column, ABOUT, palette)
        about = QLabel(tr_data(str(row["description"])))
        about.setWordWrap(True)
        style.ink(about, style.text(palette))
        column.addWidget(about)
        fields.section(column, INSIDE, palette)
        column.addWidget(fields.card_rows(palette, [self._item(item, palette) for item in row["items"]]))
        fields.section(column, INFORMATION, palette)
        column.addWidget(self._information(row, palette))
        column.addStretch(1)
        self.widget = holder

    def _header(self, row: dict[str, Any], palette: Any) -> QHBoxLayout:
        line = QHBoxLayout()
        line.setSpacing(HEADER_GAP)
        line.addWidget(monogram(row, palette, LARGE_MONOGRAM), 0, Qt.AlignmentFlag.AlignTop)
        text = QVBoxLayout()
        text.setSpacing(2)
        text.addWidget(fields.page_title(str(row["title"]), palette))
        state = QHBoxLayout()
        state.setSpacing(6)
        self._dot = controls.PaintedDot(STATUS_DOT)
        state.addWidget(self._dot, 0, Qt.AlignmentFlag.AlignVCenter)
        self._state = controls.small("", palette)
        self._state.setWordWrap(False)
        state.addWidget(self._state)
        summary = controls.small(f"· {tr_data(str(row['summary']))}", palette)
        state.addWidget(summary, 1)
        text.addLayout(state)
        line.addLayout(text, 1)
        self.switch = fields.switch(palette)
        self.switch.toggled.connect(lambda on: self._show_state(on, palette))
        line.addWidget(self.switch, 0, Qt.AlignmentFlag.AlignVCenter)
        return line

    def _show_state(self, enabled: bool, palette: Any) -> None:
        colour = style.success(palette) if enabled else style.border_strong(palette)
        self._dot.set_colour(colour.name())
        self._state.setText(ENABLED if enabled else DISABLED)
        style.ink(self._state, style.success(palette) if enabled else style.faint(palette))

    def _example(self, text: str, palette: Any) -> QWidget:
        """A request to try: the words, and on the right where a click sends them."""
        row = controls.HoverFrame(EXAMPLE_RADIUS, palette)
        row.set_look(style.surface(palette).name(), style.hairline(palette).name())
        line = QHBoxLayout(row)
        line.setContentsMargins(*EXAMPLE_MARGINS)
        line.setSpacing(10)
        words = QLabel(text)
        words.setWordWrap(True)
        style.ink(words, style.text(palette))
        line.addWidget(words, 1)
        hint = controls.small(TO_CHAT, palette)
        hint.setWordWrap(False)
        style.ink(hint, style.faint(palette))
        line.addWidget(hint, 0, Qt.AlignmentFlag.AlignVCenter)
        row.clicked.connect(lambda chosen=text: self.prompt_chosen.emit(chosen))
        self.examples.append(row)
        return row

    @staticmethod
    def _item(item: dict[str, Any], palette: Any) -> QWidget:
        holder = QWidget()
        column = QVBoxLayout(holder)
        column.setContentsMargins(*ROW_PADDING)
        column.setSpacing(2)
        name = QLabel(tr_data(str(item["title"])))
        name.setWordWrap(True)
        style.ink(name, style.text(palette))
        column.addWidget(name)
        column.addWidget(controls.small(caption(item), palette))
        return holder

    @staticmethod
    def _information(row: dict[str, Any], palette: Any) -> QWidget:
        """Key and value pairs, a hairline under each, as the handoff's table of facts."""
        facts = (
            (KEY_LABEL, KEY_VALUE),
            (LICENCE, tr_data(str(row["licence"]))),
            (SERVERS, ", ".join(row["hosts"])),
        )
        rows = []
        for label, value in facts:
            holder = QWidget()
            line = QHBoxLayout(holder)
            line.setContentsMargins(*INFO_PADDING)
            line.setSpacing(HEADER_GAP)
            name = controls.small(label, palette)
            name.setFixedWidth(INFO_LABEL_WIDTH)
            style.ink(name, style.faint(palette))
            line.addWidget(name, 0, Qt.AlignmentFlag.AlignTop)
            shown = QLabel(value)
            shown.setWordWrap(True)
            shown.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            style.ink(shown, style.text(palette))
            line.addWidget(shown, 1)
            rows.append(holder)
        return fields.card_rows(palette, rows)


def _link_style(palette: Any) -> str:
    """Muted text flush with the page edge, brightening on hover: a padded button sat indented from the title."""
    return (
        f"QPushButton {{ background: transparent; border: none; padding: 4px 0px;"
        f"color: {style.css_color(style.muted(palette))}; }}"
        f"QPushButton:hover {{ color: {style.css_color(style.text(palette))}; }}"
    )
