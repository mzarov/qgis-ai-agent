from typing import Any

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QFont
from qgis.PyQt.QtWidgets import QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from ai_agent.core.about import plugin_version, qgis_version
from ai_agent.i18n import tr
from ai_agent.ui import controls, icons, settings_advanced, style
from ai_agent.ui import settings_fields as fields
from ai_agent.ui.settings_search import SettingsSearch

# Sidebar groups as in the handoff; the numbers are page indices.
GROUPS = ((tr("Model"), (0, 1, 4)), (tr("Customize"), (6, 2)), (tr("Data"), (5, 3)))
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
    """The sidebar, full height, beside the content column; the caller adds its footer to that column."""
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
        (tr("Skills"), "skills", owner.skills.widget),
        (tr("Geocoding"), "geocoding", owner.geocoder.widget),
        (tr("Advanced"), "advanced", settings_advanced.build_advanced(owner, palette)),
        (tr("Connectors"), "connectors", owner.connectors.widget),
        (tr("Personalisation"), "personalisation", owner.personalisation.widget),
    )
    owner.search = SettingsSearch(palette)
    owner.search.opened.connect(lambda index, row: _open_result(owner, index, row))
    nav_column.addWidget(owner.search)
    owner._nav_buttons = []
    areas = []
    for index, (title, role, page) in enumerate(pages):
        area = scrollable(page)
        areas.append((title, area))
        owner.pages.addWidget(area)
        glyphs = (
            icons.drawn(role, style.muted(palette), fields.NAV_ICON),
            icons.drawn(role, style.accent(palette), fields.NAV_ICON),
        )
        button = fields.sidebar_button(title, palette, glyphs)
        button.clicked.connect(lambda _checked=False, at=index: show_page(owner, at))
        _add_marks(button, palette, owner.skills.count() if role == "skills" else 0)
        owner._nav_buttons.append(button)
    page_list: list[QWidget] = []
    for caption, members in GROUPS:
        label = _caption(caption, palette)
        nav_column.addWidget(label)
        page_list.append(label)
        for index in members:
            nav_column.addWidget(owner._nav_buttons[index])
            page_list.append(owner._nav_buttons[index])
    owner.search.index(areas, page_list)
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
    owner.pages.setCurrentIndex(index)
    for at, button in enumerate(owner._nav_buttons):
        button.setChecked(at == index)


def mark_page(owner: Any, index: int) -> None:
    """Show the dot that says this page holds unsaved changes."""
    owner._nav_buttons[index].findChild(controls.PaintedDot, DOT_NAME).setVisible(True)


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


def _open_result(owner: Any, index: int, row: Any) -> None:
    """A search result: its page, and the row brought into view."""
    show_page(owner, index)
    if row is None:
        return
    try:
        owner.pages.widget(index).ensureWidgetVisible(row, 0, ROW_MARGIN)
    except RuntimeError:
        # The row was rebuilt since the search ran (the skills list refreshes): the page alone is shown.
        return


def _caption(text: str, palette: Any) -> QLabel:
    """A group title in the sidebar: 11/600, upper case, the tertiary ink."""
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
    """The plugin's version and the QGIS it runs in, at the foot of the sidebar."""
    parts = [part for part in (f"AI Agent {plugin_version()}".strip(), f"QGIS {qgis_version()}".strip()) if part]
    label = QLabel(" · ".join(parts))
    label.setContentsMargins(*VERSION_MARGINS)
    style.scale_font(label, VERSION_SCALE)
    style.ink(label, style.faint(palette))
    return label


def _add_marks(button: QPushButton, palette: Any, count: int) -> None:
    """The entry's right edge: a count where the page has one, and the unsaved-changes dot."""
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
