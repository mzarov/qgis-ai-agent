from typing import Any

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QHBoxLayout, QScrollArea, QWidget

from ai_agent.i18n import tr
from ai_agent.ui import settings_advanced
from ai_agent.ui import settings_fields as fields


def build_body(owner: Any, palette: Any) -> QHBoxLayout:
    body = QHBoxLayout()
    body.setContentsMargins(0, 0, 0, 0)
    body.setSpacing(0)
    owner.pages = fields.pages()
    nav, nav_column = fields.sidebar()
    owner._nav_buttons = []
    entries = (
        (tr("Connection"), owner._build_connection(palette)),
        (tr("Privacy"), settings_advanced.build_privacy(owner, palette)),
        (tr("Skills"), owner.skills.widget),
        (tr("Geocoding"), owner.geocoder.widget),
        (tr("Advanced"), settings_advanced.build_advanced(owner, palette)),
    )
    for index, (title, page) in enumerate(entries):
        owner.pages.addWidget(scrollable(page))
        button = fields.sidebar_button(title, palette)
        button.clicked.connect(lambda _checked=False, at=index: show_page(owner, at))
        nav_column.addWidget(button)
        owner._nav_buttons.append(button)
    nav_column.addStretch(1)
    body.addWidget(nav)
    body.addWidget(fields.vertical_separator(palette))
    body.addWidget(owner.pages, 1)
    show_page(owner, 0)
    return body


def show_page(owner: Any, index: int) -> None:
    owner.pages.setCurrentIndex(index)
    for at, button in enumerate(owner._nav_buttons):
        button.setChecked(at == index)


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
