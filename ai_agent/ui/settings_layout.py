from typing import Any

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from ai_agent.i18n import tr
from ai_agent.ui import controls, icons, settings_advanced, style
from ai_agent.ui import settings_fields as fields

CAPTION_TOP = 14
# Sidebar groups as in the Claude Code settings; the numbers are page indices.
GROUPS = ((tr("Settings"), (0, 1, 4)), (tr("Customize"), (2, 3)))
DOT_SIZE = 7
DOT_NAME = "pageDirty"
NAV_NAME = "settingsNav"
CONTENT_NAME = "settingsContent"


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
        (tr("Connection"), icons.connection, owner._build_connection(palette)),
        (tr("Privacy"), icons.privacy, settings_advanced.build_privacy(owner, palette)),
        (tr("Skills"), icons.skills, owner.skills.widget),
        (tr("Geocoding"), icons.geocoding, owner.geocoder.widget),
        (tr("Advanced"), icons.advanced, settings_advanced.build_advanced(owner, palette)),
    )
    owner._nav_buttons = []
    for index, (title, paint, page) in enumerate(pages):
        owner.pages.addWidget(scrollable(page))
        button = fields.sidebar_button(title, palette, _drawn(paint, style.muted(palette)))
        button.clicked.connect(lambda _checked=False, at=index: show_page(owner, at))
        _add_dot(button, palette)
        owner._nav_buttons.append(button)
    for caption, members in GROUPS:
        nav_column.addWidget(_caption(caption, palette))
        for index in members:
            nav_column.addWidget(owner._nav_buttons[index])
    nav_column.addStretch(1)
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


def _caption(text: str, palette: Any) -> QLabel:
    label = controls.small(text, palette)
    label.setWordWrap(False)
    label.setContentsMargins(10, CAPTION_TOP, 0, 4)
    return label


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
