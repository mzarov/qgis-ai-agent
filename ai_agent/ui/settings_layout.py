import configparser
import os
from typing import Any

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from ai_agent.i18n import tr
from ai_agent.ui import controls, icons, settings_advanced, style
from ai_agent.ui import settings_fields as fields

BRAND = "AI Agent"
BRAND_ICON = 15
BRAND_TILE = 26
BRAND_RADIUS = 8
BRAND_GAP = 8
DOT_SIZE = 7
DOT_NAME = "pageDirty"
NAV_NAME = "settingsNav"
CONTENT_NAME = "settingsContent"
METADATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "metadata.txt")


def build_body(owner: Any, palette: Any) -> tuple[QHBoxLayout, QVBoxLayout]:
    """The sidebar, full height, beside the content column; the caller adds its footer to that column."""
    body = QHBoxLayout()
    body.setContentsMargins(0, 0, 0, 0)
    body.setSpacing(0)
    owner.pages = fields.pages()
    nav, nav_column = fields.sidebar()
    nav.setObjectName(NAV_NAME)
    nav.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    nav.setStyleSheet(f"QWidget#{NAV_NAME} {{ background: {style.css_color(style.sidebar(palette))}; }}")
    nav_column.addWidget(_brand(palette))
    owner._nav_buttons = []
    entries = (
        (tr("Connection"), icons.connection, owner._build_connection(palette)),
        (tr("Privacy"), icons.privacy, settings_advanced.build_privacy(owner, palette)),
        (tr("Skills"), icons.skills, owner.skills.widget),
        (tr("Geocoding"), icons.geocoding, owner.geocoder.widget),
        (tr("Advanced"), icons.advanced, settings_advanced.build_advanced(owner, palette)),
    )
    for index, (title, paint, page) in enumerate(entries):
        owner.pages.addWidget(scrollable(page))
        button = fields.sidebar_button(title, palette, _drawn(paint, style.muted(palette)))
        button.clicked.connect(lambda _checked=False, at=index: show_page(owner, at))
        _add_dot(button, palette)
        nav_column.addWidget(button)
        owner._nav_buttons.append(button)
    nav_column.addStretch(1)
    version = _version()
    if version:
        label = controls.small(f"{BRAND} {version}", palette)
        label.setContentsMargins(6, 0, 0, 0)
        nav_column.addWidget(label)
    content = QWidget()
    content.setObjectName(CONTENT_NAME)
    content.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    content.setStyleSheet(f"QWidget#{CONTENT_NAME} {{ background: {style.css_color(style.content(palette))}; }}")
    right = QVBoxLayout(content)
    right.setContentsMargins(0, 0, 0, 0)
    right.setSpacing(0)
    right.addWidget(owner.pages, 1)
    body.addWidget(nav)
    body.addWidget(fields.vertical_separator(palette))
    body.addWidget(content, 1)
    show_page(owner, 0)
    return body, right


def show_page(owner: Any, index: int) -> None:
    owner.pages.setCurrentIndex(index)
    for at, button in enumerate(owner._nav_buttons):
        button.setChecked(at == index)


def mark_page(owner: Any, index: int, edited: bool) -> None:
    """Show or hide the dot that says this page holds unsaved changes."""
    button = owner._nav_buttons[index]
    button.findChild(QLabel, DOT_NAME).setVisible(edited)


def scrollable(page: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QScrollArea.Shape.NoFrame)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    area.setStyleSheet("QScrollArea { background: transparent; }")
    area.setWidget(page)
    area.viewport().setAutoFillBackground(False)
    page.setAutoFillBackground(False)
    return area


def _brand(palette: Any) -> QWidget:
    holder = QWidget()
    line = QHBoxLayout(holder)
    line.setContentsMargins(6, 4, 6, 14)
    line.setSpacing(BRAND_GAP)
    tile = QLabel()
    tile.setFixedSize(BRAND_TILE, BRAND_TILE)
    tile.setAlignment(Qt.AlignmentFlag.AlignCenter)
    tile.setStyleSheet(
        f"QLabel {{ background: {style.css_color(style.accent(palette))}; border-radius: {BRAND_RADIUS}px; }}"
    )
    icon = _drawn(icons.brand, style.on_accent(palette))
    if icon is not None:
        tile.setPixmap(icon.pixmap(BRAND_ICON, BRAND_ICON))
    line.addWidget(tile)
    name = QLabel(BRAND)
    font = name.font()
    font.setBold(True)
    name.setFont(font)
    line.addWidget(name, 1)
    return holder


def _add_dot(button: QWidget, palette: Any) -> None:
    line = QHBoxLayout(button)
    line.setContentsMargins(0, 0, 10, 0)
    line.addStretch(1)
    mark = controls.dot(style.warning(palette), DOT_SIZE)
    mark.setObjectName(DOT_NAME)
    mark.setVisible(False)
    line.addWidget(mark, 0, Qt.AlignmentFlag.AlignVCenter)


def _drawn(paint: Any, colour: Any) -> Any:
    try:
        icon = paint(colour, fields.NAV_ICON)
    except Exception:
        return None
    return None if icon.isNull() else icon


def _version() -> str:
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read(METADATA, encoding="utf-8")
        return parser.get("general", "version", fallback="").strip()
    except (configparser.Error, OSError):
        return ""
