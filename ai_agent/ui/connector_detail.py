"""One connector on its own page: what it is, prompts to try, what it serves and on what terms.

Opened from a card on the Connectors page. The switch here and the card's
switch are one setting shown twice, so each follows the other. A click on an
example prompt hands it to the chat box through `prompt_chosen`.
"""

from typing import Any

from qgis.PyQt.QtCore import QObject, Qt, pyqtSignal
from qgis.PyQt.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ai_agent.i18n import tr, tr_data, tr_n
from ai_agent.ui import controls, icons, style
from ai_agent.ui import settings_fields as fields

BACK = tr("‹ All connectors")
TRY = tr("Try asking")
TRY_NOTE = tr("A click puts the request into the chat box.")
ABOUT = tr("About")
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
ROW_PADDING = (0, 9, 0, 9)
INFO_LABEL_WIDTH = 150


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
        self.switch.toggled.connect(card_switch.setChecked)
        card_switch.toggled.connect(self.switch.setChecked)
        self.examples: list[QPushButton] = []
        if row["examples"]:
            fields.section(column, TRY, palette, TRY_NOTE)
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
        title = fields.heading(str(row["title"]), palette)
        title.setWordWrap(True)
        text.addWidget(title)
        count = tr_n("%n dataset(s)", int(row["count"]))
        text.addWidget(controls.small(f"{tr_data(str(row['summary']))} · {count}", palette))
        line.addLayout(text, 1)
        self.switch = fields.switch(palette)
        line.addWidget(self.switch, 0, Qt.AlignmentFlag.AlignVCenter)
        return line

    def _example(self, text: str, palette: Any) -> QPushButton:
        button = QPushButton(text)
        button.setStyleSheet(fields.plain_button(palette) + "QPushButton { text-align: left; }")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(lambda _checked=False, chosen=text: self.prompt_chosen.emit(chosen))
        self.examples.append(button)
        return button

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
        holder = QWidget()
        grid = QGridLayout(holder)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(HEADER_GAP)
        grid.setVerticalSpacing(EXAMPLE_GAP * 2)
        facts = (
            (KEY_LABEL, KEY_VALUE),
            (LICENCE, tr_data(str(row["licence"]))),
            (SERVERS, ", ".join(row["hosts"])),
        )
        for index, (label, value) in enumerate(facts):
            name = controls.small(label, palette)
            name.setFixedWidth(INFO_LABEL_WIDTH)
            grid.addWidget(name, index, 0, Qt.AlignmentFlag.AlignTop)
            shown = QLabel(value)
            shown.setWordWrap(True)
            shown.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            style.ink(shown, style.text(palette))
            grid.addWidget(shown, index, 1)
        grid.setColumnStretch(1, 1)
        return holder


def _link_style(palette: Any) -> str:
    """Muted text flush with the page edge, brightening on hover: a padded button sat indented from the title."""
    return (
        f"QPushButton {{ background: transparent; border: none; padding: 4px 0px;"
        f"color: {style.css_color(style.muted(palette))}; }}"
        f"QPushButton:hover {{ color: {style.css_color(style.text(palette))}; }}"
    )
