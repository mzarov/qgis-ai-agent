from typing import Any

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QFont
from qgis.PyQt.QtWidgets import QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from ai_agent.core.about import plugin_version, qgis_version
from ai_agent.i18n import tr
from ai_agent.ui import controls, icons, settings_advanced, style
from ai_agent.ui import settings_fields as fields
from ai_agent.ui.settings_search import SettingsSearch
from ai_agent.ui.skills_settings import usable_count

CONNECTION, PRIVACY, SKILLS, GEOCODING, ADVANCED, CONNECTORS, PERSONALISATION = range(7)
GROUPS = (
    (tr("Model"), (CONNECTION, PRIVACY, ADVANCED)),
    (tr("Customize"), (PERSONALISATION, SKILLS)),
    (tr("Data"), (CONNECTORS, GEOCODING)),
)
CAPTION_MARGINS = (8, 10, 8, 4)
CAPTION_SCALE = 11 / 13
CAPTION_SPACING = 0.4
VERSION_SCALE = 11.5 / 13
VERSION_MARGINS = (8, 4, 8, 0)
COUNT_SCALE = 11 / 13
DOT_SIZE = 7
DOT_NAME = "pageDirty"
NAV_NAME = "settingsNav"
CONTENT_NAME = "settingsContent"
ROW_MARGIN = 40


def build_body(owner: Any, palette: Any) -> tuple[QHBoxLayout, QVBoxLayout]:
    body = QHBoxLayout()
    body.setContentsMargins(0, 0, 0, 0)
    body.setSpacing(0)
    owner.pages = fields.pages()
    nav, nav_column = fields.sidebar()
    nav.setObjectName(NAV_NAME)
    style.fill(nav, style.sidebar(palette))
    pages = (
        (tr("Connection"), "connection", owner._build_connection(palette)),
        (tr("Privacy"), "privacy", settings_advanced.build_privacy(owner, palette)),
        (tr("Skills"), "skills", None),
        (tr("Geocoding"), "geocoding", None),
        (tr("Advanced"), "advanced", settings_advanced.build_advanced(owner, palette)),
        (tr("Connectors"), "connectors", None),
        (tr("Personalisation"), "personalisation", None),
    )
    owner.search = SettingsSearch(palette)
    owner.search.opened.connect(lambda index, row: _open_result(owner, index, row))
    nav_column.addWidget(owner.search)
    owner._nav_buttons = []
    owner._unbuilt_pages = {}
    areas = []
    for index, (title, role, page) in enumerate(pages):
        area = scrollable(page)
        areas.append((title, area))
        owner.pages.addWidget(area)
        if page is None:
            owner._unbuilt_pages[index] = area
        glyphs = (
            icons.drawn(role, style.muted(palette), fields.NAV_ICON),
            icons.drawn(role, style.accent(palette), fields.NAV_ICON),
        )
        button = fields.sidebar_button(title, palette, glyphs)
        button.clicked.connect(lambda _checked=False, at=index: show_page(owner, at))
        _add_marks(button, palette, usable_count() if index == SKILLS else 0)
        owner._nav_buttons.append(button)
    page_list: list[QWidget] = []
    for caption, members in GROUPS:
        label = _caption(caption, palette)
        nav_column.addWidget(label)
        page_list.append(label)
        for index in members:
            nav_column.addWidget(owner._nav_buttons[index])
            page_list.append(owner._nav_buttons[index])
    owner.search.index(areas, page_list, lambda: build_all(owner))
    nav_column.addStretch(1)
    nav_column.addWidget(_version(palette))
    content = QWidget()
    content.setObjectName(CONTENT_NAME)
    style.fill(content, style.content(palette))
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
    ensure_page(owner, index)
    owner.pages.setCurrentIndex(index)
    for at, button in enumerate(owner._nav_buttons):
        button.setChecked(at == index)


def ensure_page(owner: Any, index: int) -> None:
    area = owner._unbuilt_pages.pop(index, None)
    if area is not None:
        _hold(area, owner.build_page(index))


def build_all(owner: Any) -> None:
    for index in list(owner._unbuilt_pages):
        ensure_page(owner, index)


def mark_page(owner: Any, index: int) -> None:
    owner._nav_buttons[index].findChild(controls.PaintedDot, DOT_NAME).setVisible(True)


def scrollable(page: QWidget | None) -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QScrollArea.Shape.NoFrame)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    area.setStyleSheet("QScrollArea { background: transparent; }")
    area.viewport().setAutoFillBackground(False)
    if page is not None:
        _hold(area, page)
    return area


def _hold(area: QScrollArea, page: QWidget) -> None:
    area.setWidget(page)
    page.setAutoFillBackground(False)


def _open_result(owner: Any, index: int, row: Any) -> None:
    show_page(owner, index)
    if row is None:
        return
    try:
        owner.pages.widget(index).ensureWidgetVisible(row, 0, ROW_MARGIN)
    except RuntimeError:
        return


def _caption(text: str, palette: Any) -> QLabel:
    label = QLabel(text)
    label.setContentsMargins(*CAPTION_MARGINS)
    style.scale_font(label, CAPTION_SCALE, bold=True)
    font = label.font()
    font.setCapitalization(QFont.Capitalization.AllUppercase)
    font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, CAPTION_SPACING)
    label.setFont(font)
    style.ink(label, style.faint(palette))
    return label


def _version(palette: Any) -> QLabel:
    parts = [part for part in (f"AI Agent {plugin_version()}".strip(), f"QGIS {qgis_version()}".strip()) if part]
    label = QLabel(" · ".join(parts))
    label.setContentsMargins(*VERSION_MARGINS)
    style.scale_font(label, VERSION_SCALE)
    style.ink(label, style.faint(palette))
    return label


def _add_marks(button: QPushButton, palette: Any, count: int) -> None:
    line = QHBoxLayout(button)
    line.setContentsMargins(0, 0, 10, 0)
    line.setSpacing(6)
    line.addStretch(1)
    if count:
        number = QLabel(str(count))
        style.scale_font(number, COUNT_SCALE)
        style.ink(number, style.faint(palette))
        line.addWidget(number, 0, Qt.AlignmentFlag.AlignVCenter)
    mark = controls.PaintedDot(DOT_SIZE)
    mark.set_colour(style.warning(palette).name())
    mark.setObjectName(DOT_NAME)
    mark.setVisible(False)
    line.addWidget(mark, 0, Qt.AlignmentFlag.AlignVCenter)
