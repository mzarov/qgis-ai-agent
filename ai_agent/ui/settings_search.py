"""The sidebar's "Find a setting": typing swaps the page list for the rows that match.

Every row the page grammar builds carries its title and hint in a property
(`settings_fields.SEARCH_PROPERTY`); page names match too. A result opens its
page and scrolls the row into view. An empty box brings the page list back.
Pages built only on their first visit are built for the first search.
"""

from collections.abc import Callable
from typing import Any

from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtWidgets import QLabel, QLineEdit, QScrollArea, QVBoxLayout, QWidget

from ai_agent.i18n import tr
from ai_agent.ui import controls, icons, style
from ai_agent.ui import settings_fields as fields

PLACEHOLDER = tr("Find a setting")
NOTHING = tr("Nothing found")
MAX_RESULTS = 12
FIELD_HEIGHT = 28
FIELD_GAP = 8
ICON = 14
RESULT_MARGINS = (8, 4, 8, 4)
TEXT_SCALE = 12.5 / 13


class SettingsSearch(QWidget):
    """The search box and, while it holds text, the results in place of the page list."""

    opened = pyqtSignal(int, object)

    def __init__(self, palette: Any):
        super().__init__()
        self._palette = palette
        self._pages: list[tuple[str, QScrollArea]] = []
        self._hidden_while_searching: list[QWidget] = []
        self._build_pages: Callable[[], None] = lambda: None
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, FIELD_GAP)
        column.setSpacing(2)
        self.field = QLineEdit()
        self.field.setPlaceholderText(PLACEHOLDER)
        self.field.setClearButtonEnabled(True)
        self.field.setFixedHeight(FIELD_HEIGHT)
        # A click focuses it, the window's first Tab does not: a caret blinking in it on open would read as a prompt.
        self.field.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        style.scale_font(self.field, TEXT_SCALE)
        self.field.setStyleSheet(fields.input_style(palette))
        glass = icons.drawn("search", style.faint(palette), ICON)
        if glass is not None:
            self.field.addAction(glass, QLineEdit.ActionPosition.LeadingPosition)
        self.field.textChanged.connect(self._search)
        column.addWidget(self.field)
        self._results = QWidget()
        self._list = QVBoxLayout(self._results)
        self._list.setContentsMargins(0, FIELD_GAP, 0, 0)
        self._list.setSpacing(2)
        self._results.setVisible(False)
        column.addWidget(self._results)

    def index(
        self, pages: list[tuple[str, QScrollArea]], page_list: list[QWidget], build_pages: Callable[[], None]
    ) -> None:
        """The pages by title, the sidebar widgets that give way to the results, and how to build every page."""
        self._pages = pages
        self._hidden_while_searching = page_list
        self._build_pages = build_pages

    def _search(self, text: str) -> None:
        words = text.casefold().split()
        for widget in self._hidden_while_searching:
            widget.setVisible(not words)
        self._results.setVisible(bool(words))
        while self._list.count():
            item = self._list.takeAt(0)
            if item is not None and item.widget() is not None:
                item.widget().deleteLater()
        if not words:
            return
        self._build_pages()
        found = self._matches(words)
        for title, page_title, open_it in found[:MAX_RESULTS]:
            self._list.addWidget(self._result(title, page_title, open_it))
        if not found:
            empty = controls.small(NOTHING, self._palette)
            empty.setContentsMargins(8, 4, 8, 4)
            self._list.addWidget(empty)

    def _matches(self, words: list[str]) -> list[tuple[str, str, Callable[[], None]]]:
        found: list[tuple[str, str, Callable[[], None]]] = []
        for index, (page_title, area) in enumerate(self._pages):
            if all(word in page_title.casefold() for word in words):
                found.append((page_title, "", lambda at=index: self.opened.emit(at, None)))
            page = area.widget()
            if page is None:
                continue
            for row in page.findChildren(QWidget):
                text = row.property(fields.SEARCH_PROPERTY)
                if isinstance(text, str) and all(word in text.casefold() for word in words):
                    found.append((_row_title(row, text), page_title, lambda at=index, r=row: self.opened.emit(at, r)))
        return found

    def _result(self, title: str, page_title: str, open_it: Callable[[], None]) -> QWidget:
        row = controls.HoverFrame(fields.NAV_RADIUS, self._palette)
        column = QVBoxLayout(row)
        column.setContentsMargins(*RESULT_MARGINS)
        column.setSpacing(0)
        name = QLabel(title)
        name.setWordWrap(True)
        style.ink(name, style.text(self._palette))
        column.addWidget(name)
        if page_title:
            column.addWidget(controls.small(page_title, self._palette))
        row.clicked.connect(open_it)
        return row


def _row_title(row: QWidget, fallback: str) -> str:
    """The row's own title label: its first label, before the hint."""
    labels = [label for label in row.findChildren(QLabel) if label.text()]
    return labels[0].text() if labels else fallback
